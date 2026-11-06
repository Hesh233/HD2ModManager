$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'UpdateIntegratedManager.ps1'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($script, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Updater has PowerShell syntax errors.' }
$function = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-PackageOwnedPath' }, $true)
if (!$function) { throw 'Updater ownership filter was not found.' }
. ([scriptblock]::Create($function.Extent.Text))
$excluded = @('settings.json','config.toml','data\indexes\asset-index.sqlite','data/indexes/asset-index.sqlite',
    'config\attachment-fix.json','cache\model.bin','logs\app.log','test-library\character\model.patch_0',
    'isolated-library\test\model.patch_0','anim_batch_mod\__pycache__\single_skeleton.cpython-311.pyc',
    'anim_batch_mod/utils/lz4_311/block/__pycache__/__init__.cpython-311.pyc')
$included = @('HD2ModManager.dll','HD2SourceMigration.dll','hd2mod.dll','anim_batch_mod\single_skeleton.py',
    'anim_batch_mod\config.toml','anim_batch_mod\presets\native-v15\grip-fixes-1.0.10.json')
foreach ($path in $excluded) { if (Test-PackageOwnedPath $path) { throw "Protected file would be copied: $path" } }
foreach ($path in $included) { if (!(Test-PackageOwnedPath $path)) { throw "Required package file would be excluded: $path" } }
if ($ast.Find({ param($node) $node -is [Management.Automation.Language.CommandAst] -and $node.GetCommandName() -eq 'New-Item' }, $true)) {
    throw 'Updater must not create directories.'
}
Write-Output 'PASS: 17 ownership-filter cases, PowerShell syntax, and no directory creation commands.'
