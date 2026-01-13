Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Normalize paths by removing trailing slashes for reliable comparison
$localPath  = "M:\local_prj\cinderella\tools\nuke".TrimEnd('\')
$serverPath = "\\192.168.99.203\prj\cinderella\tools\nuke".TrimEnd('\')

# Explicitly check the 'User' scope so the toggle logic works regardless of the current session
$currentPath = [Environment]::GetEnvironmentVariable("NUKE_PATH", "User")
if ($null -ne $currentPath) { $currentPath = $currentPath.TrimEnd('\') }

if ($currentPath -eq $localPath) {
    $nukePath = $serverPath
    $mode = "prod"
}
else {
    $nukePath = $localPath
    $mode = "dev"
}

# 1. Update the persistent Registry (User Scope)
[Environment]::SetEnvironmentVariable("NUKE_PATH", $nukePath, "User")
[Environment]::SetEnvironmentVariable("NUKE_MODE", $mode, "User")

# 2. Update the current terminal session (Process Scope)
$env:NUKE_PATH = $nukePath
$env:NUKE_MODE = $mode

Write-Host "--- NUKE ENVIRONMENT SWITCHED ---" -ForegroundColor Cyan
Write-Host "MODE:      $mode"
Write-Host "PATH:      $nukePath"
Write-Host "---------------------------------"
