param(
    [string]$Amd64Bundle = 'dist/ArcadeClip-amd64',
    [string]$Arm64Bundle = 'dist/ArcadeClip-arm64',
    [string]$Compiler = 'build/installer-tools/inno/ISCC.exe',
    [string]$Python = 'python',
    [string]$RuntimeProbe = 'build/installer-tools/runtime-probe.exe'
)
$ErrorActionPreference = 'Stop'
$installerRoot = Split-Path $PSScriptRoot -Parent
Set-Location $installerRoot
$amd64Path = (Resolve-Path -LiteralPath $Amd64Bundle).Path
$arm64Path = (Resolve-Path -LiteralPath $Arm64Bundle).Path
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$probePath = (Resolve-Path -LiteralPath $RuntimeProbe).Path
foreach ($pair in @(@('amd64', $amd64Path), @('arm64', $arm64Path))) {
    & $Python (Join-Path $PSScriptRoot 'validate_bundle.py') $pair[1] --arch $pair[0]
    if ($LASTEXITCODE -ne 0) { throw "Invalid $($pair[0]) payload." }
}
$version = (Get-Content (Join-Path $amd64Path 'build-manifest.json') -Raw | ConvertFrom-Json).version
$armVersion = (Get-Content (Join-Path $arm64Path 'build-manifest.json') -Raw | ConvertFrom-Json).version
if ($version -ne $armVersion) { throw 'Payload versions differ.' }
$outputPath = Join-Path $installerRoot 'dist/installers'
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
$logPath = Join-Path $outputPath 'installer-build.log'
& $compilerPath "/DAmd64Bundle=$amd64Path" "/DArm64Bundle=$arm64Path" "/DAppVersion=$version" "/DRuntimeProbe=$probePath" "/DOutputDir=$outputPath" (Join-Path $PSScriptRoot 'installer/ArcadeClip-universal.iss') *> $logPath
if ($LASTEXITCODE -ne 0) {
    Get-Content -LiteralPath $logPath -Tail 30
    throw 'Installer compilation failed.'
}
$installerPath = Join-Path $outputPath "ArcadeClip-$version-windows-universal-user-setup.exe"
$digest = Get-FileHash -LiteralPath $installerPath -Algorithm SHA256
($digest.Hash.ToLower() + '  ' + (Split-Path $installerPath -Leaf)) | Set-Content -LiteralPath ($installerPath + '.sha256') -Encoding ascii
Get-Item -LiteralPath $installerPath | Select-Object FullName,Length
Write-Output "SHA256: $($digest.Hash)"
