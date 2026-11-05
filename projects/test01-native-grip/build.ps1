param([string]$PythonPath=$env:HD2_PYTHON)
$ErrorActionPreference='Stop'
$project=[System.IO.Path]::GetFullPath($PSScriptRoot)
$root=[System.IO.Path]::GetFullPath((Join-Path $project '..\..'))
if (-not $PythonPath) {
    if (Test-Path -LiteralPath 'F:\TOOLS\python3.11\python.exe') {$PythonPath='F:\TOOLS\python3.11\python.exe'}
    else {$PythonPath=(Get-Command python -ErrorAction Stop).Source}
}
Push-Location -LiteralPath $root
try {
    & $PythonPath (Join-Path $root 'tools\build_native_b23_108.py') --project $project
    if ($LASTEXITCODE -ne 0) {throw 'Project build or validation failed'}
} finally {Pop-Location}
