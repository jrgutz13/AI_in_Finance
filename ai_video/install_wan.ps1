# Downloads Wan2GP into the chosen folder (called by install_wan.bat).
# Exit codes: 0 = ready (downloaded, or already there), 2 = not enough disk
# space, 1 = anything else went wrong.
param([string]$Dest)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # much faster downloads in Windows PowerShell

try {
    if (Test-Path (Join-Path $Dest 'scripts\install.bat')) {
        Write-Host "Wan2GP is already downloaded in $Dest"
    } else {
        $root = [System.IO.Path]::GetPathRoot($Dest)
        $drive = Get-PSDrive -Name $root.Substring(0, 1)
        $freeGB = [math]::Round($drive.Free / 1GB)
        Write-Host "Free space on ${root}: $freeGB GB"
        if ($freeGB -lt 60) {
            Write-Host "Wan2GP needs about 60 GB (app + AI models). Free up space or pick another drive."
            exit 2
        }
        if (Get-Command git -ErrorAction SilentlyContinue) {
            # a git copy lets Wan2GP's update.bat keep it up to date
            Write-Host "Downloading Wan2GP with git..."
            & git clone --depth 1 https://github.com/deepbeepmeep/Wan2GP.git $Dest
            if ($LASTEXITCODE -ne 0) { throw "git clone failed" }
        } else {
            Write-Host "Downloading Wan2GP..."
            # extract next to the destination: moving a folder between drives fails
            $parent = Split-Path $Dest -Parent
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
            $zip = Join-Path $env:TEMP 'wan2gp_download.zip'   # (files can't go in C:\ itself)
            $tmp = Join-Path $parent 'wan2gp_extract'
            Invoke-WebRequest -Uri 'https://github.com/deepbeepmeep/Wan2GP/archive/refs/heads/main.zip' -OutFile $zip -UseBasicParsing
            if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
            Expand-Archive -Path $zip -DestinationPath $tmp -Force
            $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
            Move-Item $inner.FullName $Dest
            Remove-Item $zip -Force
            Remove-Item $tmp -Recurse -Force
        }
    }
    # open the browser automatically each time Wan2GP starts
    $argsFile = Join-Path $Dest 'scripts\args.txt'
    if (-not (Test-Path $argsFile)) { Set-Content -Path $argsFile -Value '--open-browser' }
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
}
