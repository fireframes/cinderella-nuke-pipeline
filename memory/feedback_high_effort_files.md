---
name: High-effort files in v2 refactor
description: User wants extra care on config/schemas, shot_scanner path parsing, and pipeline_client seam
type: feedback
---

Apply high effort (thorough design, not just quick generation) to these three areas:

1. `app/config.py` + `app/models/schemas.py` — getting data models right upfront avoids later refactoring
2. `app/services/shot_scanner.py` — path parsing must be genuinely flexible; easy to get wrong
3. `nuke_tools/shot_manager/pipeline_client.py` — clean seam between Nuke and backend; errors here affect all panel behavior

**Why:** User called these out explicitly as the highest-risk parts of the v2 implementation.

**How to apply:** For these files specifically, read the existing source code thoroughly before writing, think through edge cases, and prefer correctness over brevity.

Normal effort is fine for: Dockerfile, docker-compose.yml, .env.example (boilerplate), router files (thin service wrappers), and README (prose). High effort won't change the output meaningfully for these.
