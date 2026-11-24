#requires -Version 5.1
# Interactive scheduled-task worker: keep QQ and SnowLuma in the same Windows session.
param([Parameter(Mandatory=$true)][string]$InstallDirectory, [Parameter(Mandatory=$true)][string]$LogDirectory)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
while ($true) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $stdout = Join-Path $LogDirectory "snowluma-$stamp.out.log"
    $stderr = Join-Path $LogDirectory "snowluma-$stamp.err.log"
    $process = Start-Process -FilePath $env:ComSpec -ArgumentList '/d /s /c ""launcher.bat""' -WorkingDirectory $InstallDirectory -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    "SnowLuma exited with code $($process.ExitCode); restarting in 10 seconds." | Add-Content -LiteralPath $stderr
    Start-Sleep -Seconds 10
}
