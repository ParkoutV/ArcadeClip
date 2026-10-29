param(
    [ValidateSet('all', 'amd64', 'arm64')]
    [string]$Architecture = 'all',
    [string]$Amd64Bundle = 'dist/ArcadeClip-amd64',
    [string]$Arm64Bundle = 'dist/ArcadeClip-arm64',
    [string]$Compiler = 'build/installer-tools/inno/ISCC.exe',
    [string]$Python = 'python',
    [string]$RuntimeProbe = 'build/installer-tools/runtime-probe.exe'
)
$ErrorActionPreference = 'Stop'
$installerRoot = Split-Path $PSScriptRoot -Parent
Set-Location $installerRoot
$compilerPath = (Resolve-Path -LiteralPath $Compiler).Path
$probePath = (Resolve-Path -LiteralPath $RuntimeProbe).Path
$payloads = @()
foreach ($arch in @('amd64', 'arm64')) {
    if ($Architecture -ne 'all' -and $Architecture -ne $arch) { continue }
    $bundle = if ($arch -eq 'amd64') { $Amd64Bundle } else { $Arm64Bundle }
    $payloads += ,@($arch, (Resolve-Path -LiteralPath $bundle).Path)
}
foreach ($pair in $payloads) {
    & $Python (Join-Path $PSScriptRoot 'validate_bundle.py') $pair[1] --arch $pair[0]
    if ($LASTEXITCODE -ne 0) { throw "Invalid $($pair[0]) payload." }
}
$versions = @($payloads | ForEach-Object { (Get-Content (Join-Path $_[1] 'build-manifest.json') -Raw | ConvertFrom-Json).version } | Select-Object -Unique)
if ($versions.Count -ne 1) { throw 'Payload versions differ.' }
$version = $versions[0]
$outputPath = Join-Path $installerRoot 'dist/installers'
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
foreach ($pair in $payloads) {
    $arch, $bundlePath = $pair
    $logPath = Join-Path $outputPath "installer-build-$arch.log"
    & $compilerPath "/DTargetArchitecture=$arch" "/DBundleDir=$bundlePath" "/DAppVersion=$version" "/DRuntimeProbe=$probePath" "/DOutputDir=$outputPath" (Join-Path $PSScriptRoot 'installer/ArcadeClip-user.iss') *> $logPath
    if ($LASTEXITCODE -ne 0) {
        Get-Content -LiteralPath $logPath -Tail 30
        throw 'Installer compilation failed.'
    }
    $installerPath = Join-Path $outputPath "ArcadeClip-$version-windows-$arch-user-setup.exe"
    $digest = Get-FileHash -LiteralPath $installerPath -Algorithm SHA256
    ($digest.Hash.ToLower() + '  ' + (Split-Path $installerPath -Leaf)) | Set-Content -LiteralPath ($installerPath + '.sha256') -Encoding ascii
    Get-Item -LiteralPath $installerPath | Select-Object FullName,Length
    Write-Output "SHA256: $($digest.Hash)"
}
