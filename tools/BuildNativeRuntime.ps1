[CmdletBinding()]
param([string] $PythonArchive = (Join-Path $PSScriptRoot 'python-runtime-cache\python-3.11.9-embed-amd64.zip'))
$ErrorActionPreference = 'Stop'
$managerRoot = Split-Path -Parent $PSScriptRoot
$animationRoot = Split-Path -Parent $managerRoot
$runtime = Join-Path $PSScriptRoot 'native-python\anim_batch_mod'
$pythonDirectory = Join-Path $runtime 'runtime'
if (!(Test-Path -LiteralPath $PythonArchive)) {
    throw 'Download the official python-3.11.9-embed-amd64.zip from python.org into tools/python-runtime-cache first. No generated executable is used.'
}
New-Item -ItemType Directory -Force -Path $pythonDirectory | Out-Null
Expand-Archive -LiteralPath $PythonArchive -DestinationPath $pythonDirectory -Force
$python = Join-Path $pythonDirectory 'python.exe'
$signature = Get-AuthenticodeSignature -LiteralPath $python
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Python Software Foundation*') {
    throw "Python executable signature is not valid: $($signature.Status)"
}
# Isolated stdlib plus the sibling source directory; main.py adds the package parent.
"python311.zip`n.`n..`n" | Set-Content -LiteralPath (Join-Path $pythonDirectory 'python311._pth') -Encoding ascii
$names = @('__init__.py','main.py','cli.py','native_skeleton.py','native_animation.py','native_arm_reference.py','attachment_skeleton.py','motion_skeleton.py','archive.py','batch.py','binary.py','constants.py','formats.py','math3d.py','processor.py','weapon_grip_targets.json','config.toml')
foreach ($name in $names) { Copy-Item -LiteralPath (Join-Path $animationRoot $name) -Destination $runtime -Force }
$vendor = Join-Path (Split-Path -Parent $animationRoot) 'utils\lz4_311'
foreach ($relative in @('__init__.py','version.py','LICENSE.txt','_version.cp311-win_amd64.pyd','block\__init__.py','block\_block.cp311-win_amd64.pyd')) {
    $target = Join-Path $runtime ('utils\lz4_311\' + $relative)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath (Join-Path $vendor $relative) -Destination $target -Force
}
& $python -X utf8 (Join-Path $runtime 'main.py') native-project --help
if ($LASTEXITCODE -ne 0) { throw 'Official Python + source entry point failed.' }
$manifest = [ordered]@{ builtUtc=[DateTime]::UtcNow.ToString('o'); runtime='Official CPython 3.11.9 embeddable x64';
    archiveSha256=(Get-FileHash -LiteralPath $PythonArchive -Algorithm SHA256).Hash;
    signer=$signature.SignerCertificate.Subject;
    files=@($names | ForEach-Object { @{name=$_;sha256=(Get-FileHash -LiteralPath (Join-Path $runtime $_) -Algorithm SHA256).Hash} }) }
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $runtime 'build-info.json') -Encoding utf8
