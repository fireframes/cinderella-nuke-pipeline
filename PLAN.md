 ---                                                                                                                                                                                                                       
  Plan: Cinderella v2.0 — FastAPI Backend + Nuke Client Refactor                                                                                                                                                            
                                                                                                                                                                                                                            
  Current State                                                                                                                                                                                                           
                                                                                                                                                                                                                            
  The codebase has a working Nuke panel with all logic embedded directly:                                                                                                                                                   
  - scripts/shot_manager/shot_manager_panel.py — full UI + shot scanning + filesystem ops + Cerebro status calls                                                                                                          
  - scripts/cerebro/nuke_publisher.py — Cerebro DB connection, thumbnail generation, publish logic                                                                                                                          
  - scripts/tools/import_tools.py — render layer import, camera import                                                                                                                                                    
  - scripts/config/config_loader.py — reads a JSON config file (not env-based)                                                                                                                                              
                                                                                                                                                                                                                          
  No v2 code exists yet. The upgrade-v2-test branch is clean.                                                                                                                                                               
                                                                                                                                                                                                                            
  ---                                                                                                                                                                                                                       
  Phase 1: FastAPI Backend — pipeline-backend/                                                                                                                                                                              
                                                                                                                                                                                                                            
  1.1 app/config.py — Pydantic BaseSettings                                                                                                                                                                               
  - Replace the existing JSON config loader with env-var-driven settings                                                                                                                                                    
  - Every hardcoded path from config_loader.py and nuke_publisher.py becomes a setting                                                                                                                                      
  - SHOT_PATTERN as a configurable regex (not hardcoded ep/sq/sh literals)                                                                                                                                                  
  - Cerebro settings, template paths, thumbnail seek time, cache TTL                                                                                                                                                        
                                                                                                                                                                                                                            
  1.2 app/models/schemas.py — Pydantic models                                                                                                                                                                               
  - ShotModel — episode, sequence, shot, shot_id, render_path, comp_path                                                                                                                                                    
  - RenderLayer — name, path, version                                                                                                                                                                                       
  - StatusModel, TaskModel — for Cerebro                                                                                                                                                                                  
  - ScriptResponse — path to created .nk file                                                                                                                                                                               
                                                                                                                                                                                                                            
  1.3 app/services/shot_scanner.py                                                                                                                                                                                          
  - Extract from ShotScannerWorker.run() and ShotManagerWidget.load_from_cache() / save_to_cache()                                                                                                                          
  - Walk RENDER_PATH using SHOT_PATTERN (compiled regex, not hardcoded startswith('ep'))                                                                                                                                    
  - JSON cache with TTL from SHOT_CACHE_TTL_HOURS                                                                                                                                                                           
  - scan_shots(), get_shot(), get_render_layers() — async with asyncio.to_thread()                                                                                                                                          
                                                                                                                                                                                                                            
  1.4 app/services/thumbnail_service.py                                                                                                                                                                                     
  - Extract from make_thumbnails() in nuke_publisher.py                                                                                                                                                                     
  - Accept shot_id, resolve .mov path from comp structure                                                                                                                                                                   
  - ffmpeg via asyncio.to_thread(subprocess.run(...)) — non-blocking                                                                                                                                                      
  - Fallback seek time if video is shorter than THUMBNAIL_SEEK_TIME                                                                                                                                                         
                                                                                                                                                                                                                            
  1.5 app/services/cerebro_service.py                                                                                                                                                                                       
  - Extract from cerebro_database_connect(), _background_publish(), update_cerebro_status_to_inprogress() in the panel                                                                                                      
  - Lazy DB connection, reuse instance                                                                                                                                                                                      
  - Load credentials from CEREBRO_ACCOUNT_PATH JSON                                                                                                                                                                       
  - ImportError on pycerebro → all methods raise HTTPException(503)                                                                                                                                                         
  - Methods: get_statuses(), get_tasks(), set_status(), add_report()                                                                                                                                                        
                                                                                                                                                                                                                            
  1.6 app/services/script_service.py                                                                                                                                                                                        
  - Extract from create_script() and create_precomp() in the panel                                                                                                                                                          
  - Build directory structure, load template .nk, inject paths, write file                                                                                                                                                  
  - create_comp_script(shot), create_precomp_script(shot)                                                                                                                                                                 
                                                                                                                                                                                                                            
  1.7 app/routers/ — four router files                                                                                                                                                                                      
  - shots.py — GET /shots, GET /shots/{shot_id}, POST /shots/scan                                                                                                                                                           
  - thumbnails.py — GET /shots/{shot_id}/thumbnail                                                                                                                                                                          
  - scripts.py — POST /shots/{shot_id}/comp-script, POST /shots/{shot_id}/precomp-script                                                                                                                                  
  - cerebro.py — GET /cerebro/statuses, GET /cerebro/shots/{shot_id}/tasks, POST /cerebro/shots/{shot_id}/status, POST /cerebro/shots/{shot_id}/report                                                                      
                                                                                                                                                                                                                            
  1.8 app/main.py — FastAPI app, router registration, GET /health                                                                                                                                                           
                                                                                                                                                                                                                            
  1.9 Infra files                                                                                                                                                                                                           
  - Dockerfile — python:3.11-slim, apt ffmpeg, expose 8000                                                                                                                                                                  
  - docker-compose.yml — volumes for render/comp/cache, env_file, restart policy                                                                                                                                            
  - .env.example — all vars with comments, required vs optional marked                                                                                                                                                    
                                                                                                                                                                                                                            
  ---                                                                                                                                                                                                                       
  Phase 2: Nuke Client Layer — python/shot_manager/                                                                                                                                                                     
                                                                                                                                                                                                                            
  2.1 pipeline_client.py                                                                                                                                                                                                  
  - Thin requests-based wrapper around all API endpoints                                                                                                                                                                    
  - PipelineClient(base_url) — instantiated once, reads BASE_URL from Nuke tool config                                                                                                                                      
  - One method per endpoint, returns parsed data                                                                                                                                                                            
                                                                                                                                                                                                                            
  2.2 shot_manager_qt.py (refactored panel)                                                                                                                                                                                 
  - Remove all service logic: filesystem walks, Cerebro calls, thumbnail generation                                                                                                                                         
  - Remove ShotScannerWorker class (scan runs on backend)                                                                                                                                                                   
  - Replace background thread pattern with QThread calling pipeline_client.scan_shots() (HTTP call instead of filesystem walk)                                                                                              
  - Replace all os.path.* calls inside action methods with pipeline_client.* calls                                                                                                                                          
  - Keep 100% of the Qt/PySide2 UI code, layout, signals, dropdowns, navigation                                                                                                                                             
  - Keep all nuke.* calls (scriptOpen, scriptClear, project_directory, message, ask)                                                                                                                                        
  - import_render_layers stays as Nuke-side logic (it creates Read nodes via nuke.createNode) — but the path resolution comes from GET /shots/{shot_id}                                                                     

    2.3 Other tools — all move from scripts/ to python/, with config reads replaced by pipeline_client calls

    tools/import_tools.py → python/tools/import_tools.py
    - Node creation (nuke.createNode, fromUserText, autoplace) unchanged
    - RENDER_PATH / CACHE_PATH_* lookups replaced by pipeline_client.get_shot(shot_id)
        which returns render_path and cam_path directly

    tools/write_path.py → python/tools/write_path.py
    - Write node knob writes and format settings unchanged
    - COMP_PATH lookup replaced by pipeline_client.get_shot(shot_id).comp_path

    tools/workflow_tools.py → python/tools/workflow_tools.py
    - Moved as-is; pure Nuke UI logic, no service dependency

    tools/auto_write.py → DROPPED
    - Superseded by write_path.py; contained a hardcoded server IP

    deadline/submitter.py → python/deadline/submitter.py
    - Moved as-is; talks to Deadline via DeadlineNukeClient, no studio service dependency

    devops/sync_to_server.py — left in place, out of v2 scope
                                                                                                                                                                                                           
  ---                                                                                                                                                                                                                       
  Phase 3: Config Migration                                                                                                                                                                                                 
                                                                                                                                                                                                                            
  - The existing scripts/config/cinderella_config.json paths become .env values                                                                                                                                             
  - config_loader.py is kept as-is for backward compatibility on master; the v2 panel uses PipelineClient which reads from the backend's env                                                                                
  - The SHOT_PATTERN default matches the current ep(\d+)/sq(\d+)/sh(\d+) structure           

  Phase 4: Startup
  - dockerized backend should be started with Nuke launch                                                                                                                              
                                                                                                                                                                                                                            
  ---                                                                                                                                                                                                                       
  Build Order                                                                                                                                                                                                               
                                                                                                                                                                                                                            
  1. schemas.py — models first, no dependencies                                                                                                                                                                           
  2. config.py — settings, no dependencies                                                                                                                                                                                  
  3. shot_scanner.py — uses config + models                                                                                                                                                                               
  4. thumbnail_service.py — uses config + models                                                                                                                                                                            
  5. cerebro_service.py — uses config + models, graceful pycerebro fallback                                                                                                                                               
  6. script_service.py — uses config + models + shot_scanner                                                                                                                                                                
  7. All four routers — depend on services                                                                                                                                                                                
  8. main.py + health endpoint                                                                                                                                                                                              
  9. Dockerfile + docker-compose.yml + .env.example                                                                                                                                                                       
  10. pipeline_client.py — standalone HTTP wrapper                                                                                                                                                                          
  11. Refactored shot_manager_qt.py — depends on pipeline_client, done last                                                                                                                                               
                                                                                                                                                                                                                            
  ---                                                                                                                                                                                                                     
  Key Constraints to Enforce                                                                                                                                                                                                
                                                                                                                                                                                                                            
  - SHOT_PATTERN always compiled from config — zero hardcoded startswith('ep') or literal regex in service code                                                                                                           
  - All file paths in API responses normalized to forward slashes                                                                                                                                                           
  - pycerebro failures return 503, not 500 — all other endpoints unaffected                                                                                                                                               
  - The panel's Qt/PySide2 UI, knobs, and nuke.* API calls are never modified                                                                                                                                               
  - No new features beyond what the CLAUDE.md spec describes                                                                                                                                                                
                                                                                                  