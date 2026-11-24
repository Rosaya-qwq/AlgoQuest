#requires -Version 5.1
<#
.SYNOPSIS
Install this checkout as an automatically restarting Windows service using WinSW.
.EXAMPLE
.\deploy.ps1
.EXAMPLE
.\deploy.ps1 -ResetData -RebuildVenv -NoFollow
#>
[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')]
    [string]$ServiceName = 'algoquest',
    [string]$PythonPath,
    [switch]$ResetData,
    [switch]$RebuildVenv,
    [switch]$NoStart,
    [switch]$NoFollow,
    [switch]$Uninstall,
    [switch]$BotOnly,
    [string]$SnowLumaDir,
    [string]$SnowLumaArchive,
    [string]$SnowLumaRepo = 'SnowLuma/SnowLuma',
    [ValidateRange(1,65535)][int]$WebUiPort = 5099,
    [string]$SshTarget = 'user@SERVER_IP',
    [switch]$Plan,
    [switch]$Help
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'Continue'
$ProjectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$ServiceDirectory = Join-Path $ProjectRoot '.service'
$ServiceExe = Join-Path $ServiceDirectory "$ServiceName.exe"
$ServiceXml = Join-Path $ServiceDirectory "$ServiceName.xml"
$LogDirectory = Join-Path $ProjectRoot 'logs'
$BrowserDirectory = Join-Path $ProjectRoot '.playwright-browsers'
$SupportScript = Join-Path $ProjectRoot 'scripts\deploy_support.py'
$StepNumber = 0
$SnowTaskName = "$ServiceName-snowluma"
if (-not $SnowLumaDir) { $SnowLumaDir = Join-Path $ProjectRoot '.snowluma' }
$SnowLumaDir = [IO.Path]::GetFullPath($SnowLumaDir)
$SnowSupportScript = Join-Path $ProjectRoot 'scripts\snowluma_support.py'

if ($Help) {
    @'
Run from an Administrator PowerShell on Windows 10/11 or Windows Server (x64).
  .\deploy.ps1                              Install, start, then follow live logs
  .\deploy.ps1 -PythonPath C:\Python312\python.exe
  .\deploy.ps1 -ResetData -RebuildVenv        Reset project/data and .venv explicitly
  .\deploy.ps1 -NoFollow                    Finish without following bot logs
  .\deploy.ps1 -NoStart                     Install service without starting it now
  .\deploy.ps1 -ServiceName algoquest        Select the Windows service name
  .\deploy.ps1 -Uninstall                   Stop/remove service; retain project data/config
  .\deploy.ps1 -SnowLumaDir C:\SnowLuma      Reuse an existing SnowLuma installation
  .\deploy.ps1 -SnowLumaArchive C:\Downloads\SnowLuma-win-x64.zip
  .\deploy.ps1 -SnowLumaRepo owner/repo      Explicitly select a trusted release repository
  .\deploy.ps1 -BotOnly                     Manage only the bot service
  .\deploy.ps1 -WebUiPort 5099 -SshTarget user@server
  .\deploy.ps1 -Plan                        Show plan; do not change files or services
If Python is missing, the installer uses winget to install Python 3.12.
WinSW 2.12.0 is downloaded from its official GitHub release into .service/.
Windows service startup is independent of login; stdout/stderr logs are followed live.
SnowLuma runs as an interactive scheduled task at login so it can access QQ in the same session.
QQ must be installed; first login/configuration uses the printed SnowLuma WebUI URL.
'@ | Write-Host
    exit 0
}
if ($Uninstall -and ($ResetData -or $RebuildVenv)) { throw '-Uninstall removes only the service. Do not combine it with data/environment resets.' }
if ($Plan) {
    Write-Host "Project: $ProjectRoot"
    Write-Host "Windows service: $ServiceName (WinSW)"
    Write-Host "resetData=$ResetData rebuildVenv=$RebuildVenv uninstall=$Uninstall start=$(-not $NoStart) followLogs=$(-not $NoFollow)"
    Write-Host "SnowLuma: botOnly=$BotOnly directory=$SnowLumaDir task=$SnowTaskName"
    Write-Host 'Plan only: no files, services, packages or data changed.'
    exit 0
}
if ($env:OS -ne 'Windows_NT') { throw 'Use deploy.sh on Linux.' }
foreach ($required in @('main.py', 'pyproject.toml', '.env.example', 'scripts\deploy_support.py')) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $required) -PathType Leaf)) { throw 'Run the installer from a complete AlgoQuest checkout.' }
}
if ($ProjectRoot.StartsWith('\\')) { throw 'Windows services require a local checkout, for example D:\AlgoQuest. Copy or clone the project onto a local disk first.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Open PowerShell as Administrator, then run this script again.'
}
if (-not [Environment]::Is64BitOperatingSystem) { throw 'A 64-bit Windows system is required.' }
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$DeploymentLog = Join-Path $LogDirectory ('deploy-windows-{0}.log' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
Start-Transcript -LiteralPath $DeploymentLog | Out-Null

function Write-Step([string]$Message) {
    $script:StepNumber += 1
    Write-Host ("`n[{0}] [{1}/11] {2}" -f (Get-Date -Format 'HH:mm:ss'), $script:StepNumber, $Message) -ForegroundColor Cyan
}
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Program" }
}
function Find-Python {
    $candidates = @()
    if ($PythonPath) { $candidates += @{ Program = $PythonPath; Prefix = @() } }
    else {
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) { $candidates += @{ Program = $launcher.Source; Prefix = @('-3.12') } }
        foreach ($name in @('python.exe', 'python3.exe')) {
            $command = Get-Command $name -ErrorAction SilentlyContinue
            if ($command -and $command.Source -notlike '*\Microsoft\WindowsApps\*') {
                $candidates += @{ Program = $command.Source; Prefix = @() }
            }
        }
        foreach ($registry in @('HKLM:\SOFTWARE\Python\PythonCore\3.12\InstallPath', 'HKCU:\SOFTWARE\Python\PythonCore\3.12\InstallPath')) {
            if (Test-Path -LiteralPath $registry) {
                $properties = Get-ItemProperty -LiteralPath $registry
                if ($properties.PSObject.Properties['ExecutablePath']) {
                    $candidates += @{ Program = $properties.ExecutablePath; Prefix = @() }
                }
            }
        }
    }
    foreach ($candidate in $candidates) {
        $arguments = @($candidate.Prefix) + @('-c', 'import sys,struct; assert (3,10)<=sys.version_info<(4,0) and struct.calcsize("P")==8; print(sys.executable)')
        try {
            $result = @(& $candidate.Program @arguments 2>$null)
            if ($LASTEXITCODE -eq 0 -and $result -and (Test-Path -LiteralPath ([string]$result[-1]))) {
                return [string]$result[-1]
            }
        } catch { continue }
    }
    return $null
}
function Assert-ServiceOwner {
    $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $service) { return }
    $cim = Get-CimInstance -ClassName Win32_Service -Filter "Name='$ServiceName'"
    $expected = [IO.Path]::GetFullPath($ServiceExe)
    if ($cim.PathName.Trim('"') -ne $expected) {
        throw "Existing service '$ServiceName' uses a different executable. Use its original uninstaller or choose a different -ServiceName."
    }
    Write-Host "Stopping existing service $ServiceName before changing dependencies..."
    if ($service.Status -ne 'Stopped') {
        Stop-Service -Name $ServiceName
        $service.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(45))
    }
}
function Reset-ProjectDirectory([ValidateSet('data', '.venv')][string]$Name) {
    $target = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $Name))
    $expectedParent = [IO.Path]::GetFullPath([IO.Path]::GetDirectoryName($target))
    if ($expectedParent -ne $ProjectRoot -or $target -eq $ProjectRoot) { throw "Refusing unexpected cleanup target: $target" }
    if (Test-Path -LiteralPath $target) {
        $item = Get-Item -LiteralPath $target -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing redirected directory: $target" }
        # PowerShell 5.1 has inconsistent junction deletion behavior; reject redirected descendants.
        $links = @(Get-ChildItem -LiteralPath $target -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
        if ($links.Count) { throw "Directory contains links/junctions; clean it explicitly first: $target" }
        Get-ChildItem -LiteralPath $target -Force | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    } else { New-Item -ItemType Directory -Path $target | Out-Null }
    Write-Host "Reset $target; no backup was created."
}
function Assert-SnowTaskOwner {
    $task = Get-ScheduledTask -TaskName $SnowTaskName -ErrorAction SilentlyContinue
    if ($task) {
        if ($task.Description -ne "Managed by AlgoQuest; project=$ProjectRoot") {
            throw "Existing task '$SnowTaskName' belongs to another project. Choose another -ServiceName."
        }
        if ($task.State -eq 'Running') { Stop-ScheduledTask -TaskName $SnowTaskName }
    }
}
function Follow-BotLogs {
    $positions = @{}
    $counter = 0
    Write-Host 'Following bot stdout/stderr. Press Ctrl+C to detach; the service will keep running.' -ForegroundColor Green
    while ($true) {
        $allLogs = @(Get-ChildItem -LiteralPath $LogDirectory -File -ErrorAction SilentlyContinue)
        $files = @($allLogs | Where-Object { $_.Name -in @("$ServiceName.out.log", "$ServiceName.err.log") })
        if (-not $BotOnly) { $files += @($allLogs | Where-Object { $_.Name -like 'snowluma-*.log' } | Sort-Object Name -Descending | Select-Object -First 2) }
        foreach ($file in $files) {
            $stream = $null
            $reader = $null
            try {
                $stream = [IO.File]::Open($file.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
                $offset = if ($positions.ContainsKey($file.FullName)) { $positions[$file.FullName] } else { 0L }
                if ($stream.Length -lt $offset) { $offset = 0L }
                [void]$stream.Seek($offset, [IO.SeekOrigin]::Begin)
                $reader = New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8)
                $text = $reader.ReadToEnd()
                $positions[$file.FullName] = $stream.Position
                if ($text) { Write-Host -NoNewline $text }
            } catch [IO.IOException] { } finally {
                if ($reader) { $reader.Dispose() } elseif ($stream) { $stream.Dispose() }
            }
        }
        if (($counter % 40) -eq 0) {
            $status = (Get-Service -Name $ServiceName).Status
            Write-Host ("[{0}] Managed service: {1}; waiting for new bot output..." -f (Get-Date -Format 'HH:mm:ss'), $status) -ForegroundColor DarkGray
            if ($status -eq 'Stopped') { throw 'Service stopped; inspect its .err.log and .wrapper.log files in logs/.' }
        }
        $counter += 1
        Start-Sleep -Milliseconds 750
    }
}

try {
    Assert-ServiceOwner
    if ($Uninstall) {
        if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
            if (-not (Test-Path -LiteralPath $ServiceExe)) { throw 'The original WinSW executable is missing; restore .service/ before uninstalling.' }
            Invoke-Checked $ServiceExe @('uninstall')
        }
        foreach ($file in @($ServiceExe, $ServiceXml)) { if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force } }
        if (-not $BotOnly) {
            Assert-SnowTaskOwner
            if (Get-ScheduledTask -TaskName $SnowTaskName -ErrorAction SilentlyContinue) { Unregister-ScheduledTask -TaskName $SnowTaskName -Confirm:$false }
        }
        Write-Host 'Service removed. Project files, .env, source/, data/, Python environment and logs were retained.'
        return
    }

    Write-Step 'Find Python 3.10+ or install Python 3.12 with winget'
    $PythonExe = Find-Python
    if (-not $PythonExe) {
        if ($PythonPath) { throw 'The specified -PythonPath is not a working 64-bit Python 3.10+ interpreter.' }
        $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
        if (-not $winget) { throw 'Install 64-bit Python 3.12 from python.org, or install App Installer (winget), then rerun.' }
        Invoke-Checked $winget.Source @('install', '--id', 'Python.Python.3.12', '--exact', '--scope', 'machine', '--silent', '--accept-package-agreements', '--accept-source-agreements')
        $PythonExe = Find-Python
        if (-not $PythonExe) { throw 'Python installation finished but Python was not found. Reopen Administrator PowerShell and rerun.' }
    }
    Write-Host "Python: $PythonExe"

    Write-Step 'Prepare the Python virtual environment'
    if ($RebuildVenv) { Reset-ProjectDirectory '.venv' }
    Invoke-Checked $PythonExe @('-m', 'venv', (Join-Path $ProjectRoot '.venv'))
    $VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

    Write-Step 'Install/upgrade project dependencies (live pip output)'
    Invoke-Checked $VenvPython @('-m', 'pip', 'install', '--upgrade', 'pip')
    Invoke-Checked $VenvPython @('-m', 'pip', 'install', '-e', $ProjectRoot)

    Write-Step 'Validate .env without printing API keys or cookies'
    Invoke-Checked $VenvPython @($SupportScript, 'config')
    if ($ResetData) {
        $configuredData = & $VenvPython $SupportScript 'data-path'
        if ($LASTEXITCODE -ne 0) { throw 'Cannot determine runtime data directory.' }
        if ([IO.Path]::GetFullPath([string]$configuredData) -ne [IO.Path]::GetFullPath((Join-Path $ProjectRoot 'data'))) {
            throw 'ALGOQUEST_DATA_DIR points outside project/data; reset that directory explicitly yourself.'
        }
        Reset-ProjectDirectory 'data'
    }

    Write-Step 'Install Chromium (live download progress)'
    $env:PLAYWRIGHT_BROWSERS_PATH = $BrowserDirectory
    Invoke-Checked $VenvPython @('-m', 'playwright', 'install', 'chromium')

    Write-Step 'Check Chromium and prepare local formula rendering resources'
    Invoke-Checked $VenvPython @($SupportScript, 'browser-check')

    Write-Step 'Install/reuse SnowLuma while retaining existing login/configuration'
    if (-not $BotOnly) {
        Assert-SnowTaskOwner
        $snowArguments = @($SnowSupportScript, 'install', '--directory', $SnowLumaDir, '--repo', $SnowLumaRepo)
        if ($SnowLumaArchive) { $snowArguments += @('--archive', $SnowLumaArchive) }
        Invoke-Checked $VenvPython $snowArguments
    } else { Write-Host 'SnowLuma installation skipped (-BotOnly).' }

    Write-Step 'Register SnowLuma in the interactive QQ session and print first-login links'
    if (-not $BotOnly) {
        $worker = Join-Path $ProjectRoot 'scripts\run_snowluma.ps1'
        $taskArguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -InstallDirectory "{1}" -LogDirectory "{2}"' -f $worker, $SnowLumaDir, $LogDirectory
        $action = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -Argument $taskArguments -WorkingDirectory $ProjectRoot
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
        $taskPrincipal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Highest
        $taskSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
        Register-ScheduledTask -TaskName $SnowTaskName -Action $action -Trigger $trigger -Principal $taskPrincipal -Settings $taskSettings -Description "Managed by AlgoQuest; project=$ProjectRoot" -Force | Out-Null
        if (-not $NoStart) { Start-ScheduledTask -TaskName $SnowTaskName }
        Invoke-Checked $VenvPython @($SnowSupportScript, 'links', '--directory', $SnowLumaDir, '--webui-port', [string]$WebUiPort, '--ssh-target', $SshTarget)
        Write-Host "SnowLuma initial password/logs: $LogDirectory\snowluma-*.out.log"
    } else { Write-Host 'SnowLuma task management skipped.' }

    Write-Step 'Install WinSW and generate the Windows service definition'
    New-Item -ItemType Directory -Force -Path $ServiceDirectory | Out-Null
    if (-not (Test-Path -LiteralPath $ServiceExe)) {
        $download = "$ServiceExe.download"
        $url = 'https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe'
        Write-Host "Downloading WinSW from $url"
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $download -TimeoutSec 600
        $stream = [IO.File]::OpenRead($download)
        try { if ($stream.ReadByte() -ne 77 -or $stream.ReadByte() -ne 90) { throw 'Downloaded WinSW file is not a Windows executable.' } } finally { $stream.Dispose() }
        Move-Item -LiteralPath $download -Destination $ServiceExe -Force
    }
    Invoke-Checked $VenvPython @($SupportScript, 'winsw', '--service', $ServiceName, '--output', $ServiceXml)
    if (-not (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)) { Invoke-Checked $ServiceExe @('install') }

    Write-Step 'Start the automatically managed Windows service'
    Set-Service -Name $ServiceName -StartupType Automatic
    if (-not $NoStart) {
        Start-Service -Name $ServiceName
        $service = Get-Service -Name $ServiceName
        $service.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Running, [TimeSpan]::FromSeconds(30))
        Write-Host "Service state: $($service.Status)"
    } else { Write-Host 'Service installed/enabled; automatic startup skipped (-NoStart).' }

    Write-Step 'Deployment complete; show live bot startup and problem-buffer progress'
    Write-Host "Deployment log: $DeploymentLog"
    Write-Host "Service: Get-Service $ServiceName; logs: $LogDirectory"
    Write-Host 'Running means the process is managed; problem warmup and QQ connection are reported in the bot logs.'
    Write-Host 'In SnowLuma WebUI, log in/attach QQ and configure reverse WebSocket: ws://127.0.0.1:8080/onebot/v11/ws/ (use PORT in .env).'
    if (-not $NoFollow -and -not $NoStart) { Follow-BotLogs }
} catch {
    Write-Host ("Deployment failed at step {0}: {1}" -f $StepNumber, $_.Exception.Message) -ForegroundColor Red
    Write-Host "Deployment log: $DeploymentLog" -ForegroundColor Yellow
    throw
} finally {
    Stop-Transcript | Out-Null
}
