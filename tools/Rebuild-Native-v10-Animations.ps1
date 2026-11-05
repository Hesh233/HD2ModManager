param(
    [string] $GameData = 'E:\Steam\steamapps\common\Helldivers 2\data',
    [string] $Output = (Join-Path $PSScriptRoot ('animations-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
)
$ErrorActionPreference = 'Stop'
$nativeManager = Join-Path (Split-Path -Parent $PSScriptRoot) 'manager'
$nativePython = Join-Path $nativeManager 'anim_batch_mod\runtime\python.exe'
$nativeEntry = Join-Path $nativeManager 'anim_batch_mod\main.py'
if (!(Test-Path -LiteralPath $nativePython) -or !(Test-Path -LiteralPath $nativeEntry)) {
    throw 'Place this project beside the v10 manager folder before rebuilding.'
}
& $nativePython -X utf8 $nativeEntry native-project --manifest (Join-Path $PSScriptRoot 'source-skeleton.json') --config (Join-Path $PSScriptRoot 'config.toml') --game-data $GameData --output $Output
exit $LASTEXITCODE
