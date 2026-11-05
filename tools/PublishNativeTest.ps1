[CmdletBinding()]
param([Parameter(Mandatory=$true)][string] $OutputDirectory, [switch] $NoRestore)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$destination=[IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $destination) { throw 'Choose a new output directory so old build artifacts cannot enter the package.' }
& (Join-Path $PSScriptRoot 'BuildNativeRuntime.ps1')
foreach ($project in @('HD2ModManager\HD2ModManager.csproj','HD2ModCli\HD2ModCli.csproj')) {
    $publishArgs = @('publish', (Join-Path $root $project), '-c', 'Release', '--output', $destination, '-p:DebugType=None', '-p:DebugSymbols=false')
    if ($NoRestore) { $publishArgs += '--no-restore' }
    & dotnet @publishArgs
    if ($LASTEXITCODE -ne 0) { throw "Publish failed: $project" }
}
$sdk=Join-Path $PSScriptRoot 'ref\HD2SDK-CommunityEdition'
$target=Join-Path $destination 'third_party\hd2sdk'
New-Item -ItemType Directory -Force -Path (Join-Path $target 'deps') | Out-Null
Copy-Item -LiteralPath (Join-Path $sdk 'deps\texconv.exe') -Destination (Join-Path $target 'deps')
Copy-Item -LiteralPath (Join-Path $sdk 'materials') -Destination $target -Recurse
if (Test-Path -LiteralPath (Join-Path $destination 'anim_batch_mod\anim_batch_mod.exe')) { throw 'Retired PyInstaller executable found in new package.' }
& (Join-Path $destination 'hd2mod.exe') --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Published CLI failed.' }
Write-Output $destination
