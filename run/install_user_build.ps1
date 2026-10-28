$ErrorActionPreference = 'Stop'
$installationRepo = Split-Path $PSScriptRoot -Parent
$installationOutput = Join-Path $installationRepo 'dist/installers'
$installerExe = Join-Path $installationOutput 'ArcadeClip-0.2.1-performance-20261005-windows-arm64-user-setup.exe'
$installationTarget = Join-Path $env:LOCALAPPDATA 'Programs/ArcadeClip-ARM64'
$installationLog = Join-Path $installationOutput 'user-install.log'
if (-not (Test-Path -LiteralPath $installerExe -PathType Leaf)) { throw 'Build the installer first.' }
$setup = Start-Process -FilePath $installerExe -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER', '/LANG=korean', ('/DIR="' + $installationTarget + '"'), ('/LOG="' + $installationLog + '"')) -WindowStyle Hidden -Wait -PassThru
if ($setup.ExitCode -ne 0) { throw "Installer failed: $($setup.ExitCode). See $installationLog" }
$installedPython = Join-Path $installationTarget 'runtime/python.exe'
& $installedPython -X utf8 (Join-Path $PSScriptRoot 'verify_user_install.py') (Join-Path $installationRepo 'dist/ArcadeClip-arm64_analysis-options') $installationTarget (Join-Path $installationOutput 'user-install-validation.json')
if ($LASTEXITCODE -ne 0) { throw 'Installed payload validation failed.' }
$launch = Start-Process -FilePath (Join-Path $installationTarget 'ArcadeClip.exe') -WorkingDirectory $installationTarget -PassThru
$window = $null
for ($attempt = 0; $attempt -lt 15; $attempt++) {
    Start-Sleep -Seconds 2
    $launch.Refresh()
    if ($launch.HasExited) { throw "Installed app exited during startup: $($launch.ExitCode)" }
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($launch.Id)"
    foreach ($child in $children) {
        $candidate = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
        if ($candidate -and $candidate.MainWindowHandle -ne 0) { $window = $candidate; break }
    }
    if ($window) { break }
}
if (-not $window) { throw 'The launcher is running, but no application window was detected within 30 seconds.' }
$launchResult = [ordered]@{ installedPath=$installationTarget; launcherPid=$launch.Id; applicationPid=$window.Id; windowTitle=$window.MainWindowTitle; running=$true }
$launchResult | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $installationOutput 'user-launch-validation.json') -Encoding utf8
$launchResult | ConvertTo-Json
