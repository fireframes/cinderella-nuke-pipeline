
```
You are helping me refactor and extend an existing VFX pipeline tools.
We are building version 2.0 of this project.

## What This Project Is

I have a working Shot Manager panel built in Python for Nuke (a professional
compositing application by Foundry). This panel is the CORE of the project —
it is a PySide2 UI that runs inside Nuke and allows artists to:

- Browse and filter shots by episode, sequence, and shot number
- Create and open Nuke comp scripts from templates
- Create light_precomp scripts for lighting artists
- Import render layers and cameras into the current script
- Generate thumbnails for shot previews via ffmpeg
- Connect to Cerebro (production tracking DB) to read/set task statuses
- Sync recently changed files to a production server via git diff

Currently all of this logic lives directly inside the panel class (shot_manager_qt.py),
tightly coupled to Nuke's Python environment. The goal of this refactor is to:

1. Extract the business logic into a standalone FastAPI backend service
2. Keep the Nuke panel intact as a client that talks to this backend over HTTP
3. Generalize all studio-specific config so any studio can deploy this with their
   own server paths, naming conventions, and Cerebro setup
4. Containerize the backend with Docker

The Nuke panel IS the product. The FastAPI backend exists to serve it.

---

## Architecture

```
Nuke (DCC host)
└── shot_manager_qt.py  (PySide2 panel — stays, gets refactored)
    └── HTTP calls → FastAPI Backend (new)
                     ├── Shot discovery & caching
                     ├── Thumbnail generation (ffmpeg)
                     ├── Cerebro DB integration
                     └── File & script operations
```

The panel should replace all direct filesystem and Cerebro calls with
requests to http://localhost:8000 (configurable BASE_URL). All UI code,
knob logic, and Nuke-specific behavior stays in the panel unchanged.

---

## Project Structure to Generate

```
pipeline-backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── routers/
│   │   ├── shots.py
│   │   ├── thumbnails.py
│   │   ├── cerebro.py
│   │   └── scripts.py
│   ├── services/
│   │   ├── shot_scanner.py
│   │   ├── thumbnail_service.py
│   │   ├── cerebro_service.py
│   │   └── script_service.py
│   └── models/
│       └── schemas.py
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

And a refactored Nuke client:

```
nuke_tools/
└── shot_manager/
    ├── __init__.py
    ├── shot_manager_qt.py     ← refactored: UI only, HTTP calls replace service logic
    └── pipeline_client.py     ← new: thin HTTP client wrapping all API calls
```

---

## Config System (app/config.py)

Use Pydantic BaseSettings. Every value comes from environment variables.
No hardcoded paths, IPs, or studio-specific values anywhere in the codebase.

```python
class Settings(BaseSettings):
    # Server paths
    RENDER_PATH: str           # e.g. //192.168.x.x/prj/show/render
    COMP_PATH: str             # e.g. //192.168.x.x/prj/show/comp
    CACHE_PATH: str

    # Shot naming — configurable regex so studios with different
    # conventions (s01/e01/sc001, etc.) can adapt without code changes
    SHOT_PATTERN: str = r"ep(\d+)[/\\]sq(\d+)[/\\]sh(\d+)"
    SHOT_ID_FORMAT: str = "ep{ep}_sq{sq}_sh{sh}"

    # Cerebro
    CEREBRO_SERVER: str = ""
    CEREBRO_CARGADOR_ADDRESS: str = ""
    CEREBRO_CARGADOR_NATIVE_PORT: int = 7779
    CEREBRO_CARGADOR_HTTP_PORT: int = 7780
    CEREBRO_ACCOUNT_PATH: str = ""  # path to credentials JSON

    # Templates
    TEMPLATE_COMP_PATH: str = ""
    TEMPLATE_PRECOMP_PATH: str = ""

    # Thumbnail
    THUMBNAIL_SEEK_TIME: float = 0.5

    # Cache TTL
    SHOT_CACHE_TTL_HOURS: int = 1

    class Config:
        env_file = ".env"
```

---

## Services (extracted from existing panel logic)

### shot_scanner.py
Extracted from: scan_shot_dirs(), load_from_cache(), save_to_cache()

- Walk RENDER_PATH recursively
- Parse directories using SHOT_PATTERN (compiled from config, not hardcoded)
- Build shot list: {episode, sequence, shot, shot_id, render_path, comp_path}
- Cache results to JSON with TTL
- Methods:
  - scan_shots() -> List[ShotModel]
  - get_shot(shot_id) -> Optional[ShotModel]
  - get_render_layers(shot_id) -> List[str]

### thumbnail_service.py
Extracted from: make_thumbnails() in the panel

- Accept a shot_id, resolve its .mov path
- Check if .thumb/ file already exists, return it if so
- Run ffmpeg in a threadpool executor (non-blocking)
- Handle videos shorter than THUMBNAIL_SEEK_TIME — fall back to 0.1s
- Return thumbnail path or raise HTTPException on failure

### cerebro_service.py
Extracted from: cerebro_database_connect() and all db.* calls

- Lazy connection: connect on first use, reuse instance
- Load credentials from CEREBRO_ACCOUNT_PATH JSON
- Wrap all pycerebro calls in try/except
- If pycerebro is not installed, all methods raise a 503 with a clear message
  (Cerebro Python library is Windows-only in many studio setups)
- Methods:
  - get_statuses() -> List[StatusModel]
  - get_tasks(shot_url: str) -> List[TaskModel]
  - set_status(task_id: int, status_id: int) -> bool
  - add_report(task_id, message, preview_path, scene_path) -> bool

### script_service.py
Extracted from: create_script(), create_light_precomp()

- create_comp_script(shot: ShotModel) -> ScriptResponse
  - Build directory structure: comp/nk, comp/exr, comp/mov
  - Load template from TEMPLATE_COMP_PATH
  - Inject correct render/write paths into template
  - Write .nk file, return path

- create_precomp_script(shot: ShotModel) -> ScriptResponse
  - Build: light_precomp/nk, light_precomp/mov
  - Load template from TEMPLATE_PRECOMP_PATH
  - Inject Read nodes for render sources
  - Inject Write node pointing to light_precomp/mov
  - Write .nk file, return path

---

## API Endpoints

```
GET  /health                              → render path reachable, cerebro status
GET  /shots                              → list shots (filter: ?ep=01&sq=05)
GET  /shots/{shot_id}                    → shot details + render layers
POST /shots/scan                         → force rescan, invalidate cache

GET  /shots/{shot_id}/thumbnail          → return thumbnail path or generate it
POST /shots/{shot_id}/comp-script        → create comp .nk from template
POST /shots/{shot_id}/precomp-script     → create light_precomp .nk from template

GET  /cerebro/statuses                   → list all Cerebro statuses
GET  /cerebro/shots/{shot_id}/tasks      → get tasks for shot
POST /cerebro/shots/{shot_id}/status     → set task status {task_id, status_id}
POST /cerebro/shots/{shot_id}/report     → add report with attachments
```

---

## Nuke Client Layer (nuke_tools/shot_manager/pipeline_client.py)

A thin HTTP client the panel imports instead of calling services directly.

```python
import requests

class PipelineClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def get_shots(self, ep=None, sq=None): ...
    def get_shot(self, shot_id): ...
    def get_render_layers(self, shot_id): ...
    def generate_thumbnail(self, shot_id): ...
    def create_comp_script(self, shot_id): ...
    def create_precomp_script(self, shot_id): ...
    def get_cerebro_statuses(self): ...
    def set_cerebro_status(self, shot_id, task_id, status_id): ...
```

The panel instantiates PipelineClient once and calls it everywhere it previously
called filesystem or Cerebro methods directly. BASE_URL should be readable from
the Nuke tool config so a studio can point all artists at a shared server.

---

## Docker

Dockerfile:
- Base: python:3.11-slim
- Install ffmpeg via apt-get
- Copy app, install requirements
- Expose 8000
- CMD: uvicorn app.main:app --host 0.0.0.0 --port 8000

docker-compose.yml:
- Service: api
- Mount render/comp/cache paths as volumes (read-only for render, read-write for comp)
- env_file: .env
- restart: unless-stopped

.env.example:
- All variables with placeholder values and inline comments explaining each one
- Note which variables are required vs optional

---

## README.md

Generate a README that explains:
1. What this is and why it exists (Nuke Shot Manager backend)
2. How the Nuke panel and the backend relate to each other
3. Studio deployment: clone, fill .env, docker-compose up
4. How to adapt SHOT_PATTERN for a different naming convention
5. Cerebro setup notes (Windows dependency caveat)
6. How to point the Nuke panel at a shared studio server vs localhost

---

## Implementation Rules

- No hardcoded studio paths, IPs, show names, or naming conventions anywhere
- SHOT_PATTERN is always compiled from config — never a literal regex in service code
- pycerebro import failures are handled gracefully — cerebro endpoints return 503,
  all other endpoints continue working
- All file paths in API responses use forward slashes
- Async endpoints throughout; subprocess calls (ffmpeg) run in threadpool executor
- The Nuke panel UI code (PySide2, knobs, callbacks) is never touched — only the
  data/service calls are replaced with HTTP calls through PipelineClient
```