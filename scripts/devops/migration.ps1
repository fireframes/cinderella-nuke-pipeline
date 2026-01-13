$sourceRoot = "\\192.168.99.202\prj\cinderella\render"
$destRoot = "\\192.168.99.203\prj\cinderella\render"

Write-Host "Discovering comp and light_precomp directories..." -ForegroundColor Green

$compDirs = Get-ChildItem -Path $sourceRoot -Recurse -Directory |
    Where-Object { $_.FullName -match "\\ep\d+\\sq\d+\\sh\d+\\(comp|light_precomp)$" }

Write-Host "Found $($compDirs.Count) directories" -ForegroundColor Yellow

foreach ($compDir in $compDirs) {
    $relativePath = $compDir.FullName.Substring($sourceRoot.Length + 1)
    $parentPath = Split-Path $relativePath -Parent

    # Define source and destination paths for this loop iteration
    $currentSource = $compDir.FullName
    $currentDest = Join-Path (Join-Path $destRoot $parentPath) $compDir.Name

    Write-Host "Processing: $currentSource -> $currentDest" -ForegroundColor Cyan

    # ---- START: Pre-deletion check ----

    # Only check for extra files if the destination directory already exists.
    if (Test-Path $currentDest) {
        # Get recursive file lists for source and destination
        $sourceFiles = Get-ChildItem -Path $currentSource -Recurse -File
        $destFiles = Get-ChildItem -Path $currentDest -Recurse -File

        # Compare the two lists to find files only in the destination
        $extraFiles = Compare-Object -ReferenceObject $sourceFiles -DifferenceObject $destFiles -Property Name -PassThru | Where-Object { $_.SideIndicator -eq '=>' }

        foreach ($file in $extraFiles) {
            # Specify the file or pattern to prompt for
            if ($file.Name -like "*.tmp") {
                $choice = Read-Host "DELETE '$($file.Name)' from destination? [y/n]"
                if ($choice -eq 'y') {
                    Write-Host "DELETING: $($file.FullName)" -ForegroundColor Yellow
                    Remove-Item -Path $file.FullName -Force
                }
            }
        }
    }
    # ---- END: Pre-deletion check ----


    # Robocopy will create the destination directory if it doesn't exist.
    $robocopyArgs = @(
        $currentSource,
        $currentDest,
        "/E",
        "/R:3",
        "/W:10",
        "/MT:8",
        "/LOG+:migration.log"
    )

    $result = Start-Process -FilePath "robocopy" -ArgumentList $robocopyArgs -Wait -PassThru -NoNewWindow

    if ($result.ExitCode -lt 4) {
        Write-Host "SUCCESS: $relativePath" -ForegroundColor Green
    } else {
        Write-Host "FAILED: $relativePath (Exit Code: $($result.ExitCode))" -ForegroundColor Red
    }
}

Write-Host "Migration complete. Check migration.log for details." -ForegroundColor Green