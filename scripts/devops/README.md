# Pipeline Dev Scripts

This folder contains developer scripts for managing the Nuke pipeline:
- `switch_nuke_mode.ps1` — switch between local and server NUKE_PATH.
    'dev' - local development mode.
    'prod' - points to studio-shared Nuke tools path.
- `sync_to_server.py` — copies recently pushed Nuke scripts to production.

Run these from PowerShell or integrate with your CI/git hooks if needed.

Set aliases:
- `notepad $PROFILE` - open PS profile
- `Set-Alias -Name nukeMode -Value .\scripts\devops\switch_nuke_mode.ps1`
- `function copySync {
    python.exe .\scripts\devops\sync_to_server.py @args
}`
