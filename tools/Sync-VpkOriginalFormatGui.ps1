[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$out=Join-Path $root 'outputs\vpk-original-format-option-20261111'
$install=Join-Path $root 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7'
$audit=Get-Content -LiteralPath (Join-Path $out 'gui-code-audit.json') -Raw -Encoding UTF8|ConvertFrom-Json
$smoke=Get-Content -LiteralPath (Join-Path $out 'ui-final\gui-smoke.json') -Raw -Encoding UTF8|ConvertFrom-Json
if($audit.status -ne 'PASS_SCOPED_GUI_ONLY' -or $smoke.status -ne 'PASS' -or $smoke.cases.Count -ne 8 -or !$smoke.originalFormatWithoutPythonRuntime){throw 'Missing final route/GUI certification'}
$source=Join-Path $out 'candidate\HD2ModManager.dll';$target=Join-Path $install 'HD2ModManager.dll'
$backup=Join-Path $out 'before\outputs\native-v34-b23-integrated-20261105\manager-1.0.7\HD2ModManager.dll'
function Hash([string]$p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
if((Hash $source) -ne $audit.afterSha256 -or (Hash $target) -ne $audit.beforeSha256 -or (Hash $backup) -ne $audit.beforeSha256){throw 'Source or installed GUI changed since certification'}
$protected=Get-Content -LiteralPath (Join-Path $out 'protected-before.json') -Raw -Encoding UTF8|ConvertFrom-Json
foreach($p in $protected){if((Hash $p.path) -ne $p.sha256.ToLowerInvariant()){throw "Protected physics input changed: $($p.path)"}}
$handle=[IO.File]::Open($target,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);$handle.Dispose()
[IO.File]::Copy($source,$target,$true)
if((Hash $target) -ne $audit.afterSha256){throw 'Installed GUI readback differs'}
foreach($p in $protected){if((Hash $p.path) -ne $p.sha256.ToLowerInvariant()){throw 'Protected physics changed during GUI copy'}}
@{status='SYNCED_GUI_ONLY';target=$target;source=$source;backup=$backup;beforeSha256=$audit.beforeSha256;afterSha256=$audit.afterSha256;changedFiles=@('HD2ModManager.dll');physicsRuntimeVersion='2.3.3';protectedFilesUnchanged=$protected.Count;gameDeployed=$false}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $out 'installation-sync.json') -Encoding utf8
Write-Output 'Installed GUI synchronized. Core, physics 2.3.3 and frozen package/archive unchanged.'
