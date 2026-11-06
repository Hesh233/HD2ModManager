[CmdletBinding()]
param([string]$Python='F:\TOOLS\python3.11\python.exe')
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Push-Location $root
try {
    & $Python (Join-Path $PSScriptRoot 'prepare_test07_grip_candidate.py')
    if ($LASTEXITCODE -ne 0) { throw 'Profile preparation failed' }
    & dotnet build HD2ModCore/HD2ModCore.csproj --no-restore -v minimal
    if ($LASTEXITCODE -ne 0) { throw 'Core build failed' }
    Add-Type -Path (Join-Path $root 'HD2GameItemAssets/bin/Debug/net8.0/HD2GameItemAssets.dll')
    Add-Type -Path (Join-Path $root 'HD2ModCore/bin/Debug/net8.0/HD2ModCore.dll')
    $out=Join-Path $root 'outputs/test07-sidearm-fix-111-20261106'
    $profile=Get-Content -LiteralPath (Join-Path $out 'attachment-profile.lua') -Raw
    $source=[HD2ModCore.Infrastructure.PhysBoneLuaSource]::ComposeAttachmentFixPackage('mods/hd2modmanager/attachment_fix',$profile)
    $candidate=Join-Path $out 'candidate-111'
    [IO.Directory]::CreateDirectory($candidate) | Out-Null
    [IO.File]::WriteAllText((Join-Path $candidate 'hd2attachmentfix.lua'),$source,[Text.UTF8Encoding]::new($false))
    [HD2ModCore.Infrastructure.LuaAddonPatchBuilder]::Write($candidate,'mods/hd2modmanager/attachment_fix',$source) | Out-Null
    & $Python (Join-Path $PSScriptRoot 'prepare_test07_grip_candidate.py') --package
    if ($LASTEXITCODE -ne 0) { throw 'Package verification failed' }
} finally { Pop-Location }
