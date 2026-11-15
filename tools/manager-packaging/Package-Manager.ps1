[CmdletBinding()]
param(
    [ValidateSet('Full','Startup')][string]$Mode = 'Full',
    [switch]$CheckOnly,
    [string]$InstallationRoot,
    [string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
function Get-LiteralSha256([string]$Path) {
    $stream = [IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose(); $stream.Dispose() }
}
if ([string]::IsNullOrWhiteSpace($InstallationRoot)) {
    $InstallationRoot = if ([string]::IsNullOrWhiteSpace($env:HD2_PACKAGE_INSTALLATION_ROOT)) { Join-Path $PSScriptRoot '..\..' } else { $env:HD2_PACKAGE_INSTALLATION_ROOT }
}
$root = [IO.Path]::GetFullPath($InstallationRoot)
if (-not (Test-Path -LiteralPath (Join-Path $root 'HD2ModManager.dll') -PathType Leaf)) { throw 'Invalid installation. Pass -InstallationRoot with the manager directory.' }
$rootPrefix = $root.TrimEnd('\') + '\'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'package-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema -ne 2) { throw 'Unsupported manifest schema.' }
# The launcher directory name is historical; bind both Full and Startup to the actual GUI assembly.
$managerAssemblyVersion = [Reflection.AssemblyName]::GetAssemblyName((Join-Path $root 'HD2ModManager.dll')).Version
$managerVersion = '{0}.{1}.{2}' -f $managerAssemblyVersion.Major,$managerAssemblyVersion.Minor,$managerAssemblyVersion.Build
if ($manifest.managerVersion -ne $managerVersion) {
    throw ("Packaging manifest versions are stale: manifest={0}, installed GUI={1}. Synchronize Package-HD2ModManager.bat and its packaging tools with Sync-ManagerPackaging.ps1; do not disable the version/hash gates." -f $manifest.managerVersion,$managerVersion)
}
if ($manifest.buildFlavor -ne 'skeleton-test' -or $manifest.selfUpdatesEnabled -ne $false) { throw 'Missing skeleton-test build policy in packaging manifest.' }
Write-Host ("GUI version: {0}; skeleton-test; program self-updates disabled." -f $managerVersion)
$relativeFiles = if ($Mode -eq 'Full') { @($manifest.full) } else { @($manifest.startup) }
if ($relativeFiles.Count -eq 0) { throw 'Empty package manifest.' }
$seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$sources = @(foreach ($relative in $relativeFiles) {
    if ([string]::IsNullOrWhiteSpace($relative) -or [IO.Path]::IsPathRooted($relative) -or $relative -match '(^|[/\\])\.\.?([/\\]|$)') { throw "Unsafe relative path: $relative" }
    $source = [IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $source.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe path: $relative" }
    if ($relative -match '(^|[/\\])(__pycache__|test-library|logs|cache|测试包|测试与诊断脚本)([/\\]|$)' -or $relative -match '\.(bak|pdb)$') { throw "Forbidden payload: $relative" }
    if (-not $seen.Add($relative.Replace('\','/'))) { throw "Duplicate entry: $relative" }
    $info = Get-Item -LiteralPath $source
    if ($info.PSIsContainer -or ($info.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Not a regular file: $relative" }
    # Reject junctions in parent components, too.
    $parent = $info.Directory
    while ($parent.FullName.Length -gt $root.Length) {
        if ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked directory: $relative" }
        $parent = $parent.Parent
    }
    [pscustomobject]@{ Relative = $relative.Replace('\','/'); Path = $source; Size = $info.Length; ModifiedTicks = $info.LastWriteTimeUtc.Ticks; Hash = $null }
})
# Fail closed if an updated build adds a managed/native dependency to its deps.json.
$stems = if ($Mode -eq 'Full') { @('HD2ModManager','hd2mod') } else { @('HD2ModManager') }
foreach ($stem in $stems) {
    $deps = Get-Content -LiteralPath (Join-Path $root ($stem+'.deps.json')) -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($target in $deps.targets.PSObject.Properties) {
        foreach ($library in $target.Value.PSObject.Properties) {
            foreach ($asset in $library.Value.runtime.PSObject.Properties) {
                $required = [IO.Path]::GetFileName($asset.Name)
                if (-not $seen.Contains($required)) { throw "Manifest is outdated: dependency $required must be allowlisted." }
            }
            foreach ($asset in $library.Value.runtimeTargets.PSObject.Properties) {
                if ($asset.Value.rid -eq 'win-x64' -and -not $seen.Contains($asset.Name.Replace('\','/'))) { throw "Manifest is outdated: native dependency $($asset.Name) must be allowlisted." }
            }
        }
    }
}
if ($Mode -eq 'Full') {
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $root 'anim_batch_mod') -File -Filter '*.py') {
        if ($file.Name -notmatch '^(test_|diag_)' -and $file.Name -notin @('gui.py','remove_state_machine.py') -and -not $seen.Contains('anim_batch_mod/'+$file.Name)) {
            throw "Manifest is outdated: new Python module $($file.Name) requires dependency analysis."
        }
    }
}
$licensePath = Join-Path $PSScriptRoot '项目许可证.txt'
if (-not (Test-Path -LiteralPath $licensePath -PathType Leaf)) { throw 'Project license is missing.' }
# Full packages must carry the independently deployable production physics ZIP.
# Never select a candidate/test ZIP by name, date or highest version.
$artifacts = @()
$b3Capabilities = $null
$helper = Join-Path $PSScriptRoot 'ManagerPackageSupport.dll'
$helperFiles = @('ManagerPackageSupport.dll','ManagerPackageSupport.deps.json','ManagerPackageSupport.runtimeconfig.json')
if ($Mode -eq 'Full') {
    $artifacts = @($manifest.productionArtifacts)
    if ($artifacts.Count -ne 1 -or $artifacts[0].kind -ne 'physics-runtime' -or $artifacts[0].path -ne '运行时配套/物理运行时.zip' -or $artifacts[0].addonId -ne 'mods/hd2modmanager/physbone' -or $artifacts[0].modGuid -ne '7c1e2b90-5f3a-4d68-9a11-2b7c4e5f6a01') { throw 'Full manifest must contain the production physics artifact definition.' }
    if (-not $seen.Add($artifacts[0].path)) { throw 'Duplicate production artifact path.' }
    foreach ($file in $helperFiles) {
        $helperInfo = Get-Item -LiteralPath (Join-Path $PSScriptRoot $file)
        if ($helperInfo.PSIsContainer -or ($helperInfo.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Invalid packaging helper: $file" }
    }
    if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) { throw 'dotnet is required to export installed production physics.' }
    & dotnet $helper physics-check $root
    if ($LASTEXITCODE -ne 0) { throw 'Installed production physics validation failed.' }
    if ($seen.Contains('anim_batch_mod/runtime_companions.py')) {
        $b3Check = & dotnet $helper companion-check $root
        if ($LASTEXITCODE -ne 0) { throw 'Installed Core/Python production B3 validation failed.' }
        $b3Capabilities = ($b3Check -join [Environment]::NewLine) | ConvertFrom-Json
        if ($b3Capabilities.status -ne 'ready') { throw 'Production B3 generator is not ready.' }
        if ($manifest.runtimeCompanionVersion -ne $b3Capabilities.runtimeVersion -or $manifest.attachmentRepairPolicyVersion -ne $b3Capabilities.runtimeVersion) { throw 'Packaging manifest runtime/profile versions are stale.' }
        Write-Host 'Production B3 1.0.19 / repair profile + skeleton/config hashes / FP Source 1.0.1 generator validated; per-model ZIPs are created on export.'
    }
}
$totalBytes = ($sources | Measure-Object Size -Sum).Sum
Write-Host ("Mode: {0}; payload: {1} files, {2:N2} MiB; ZIP: {3} entries ({4} generated physics ZIP)" -f $Mode,$sources.Count,($totalBytes/1MB),($sources.Count+3+$artifacts.Count),$artifacts.Count)
Write-Host 'Requires Windows x64 + .NET 10 Desktop Runtime + Microsoft VC++ v14 x64 Redistributable. No personal library, paths, indexes or caches are included.'
if ($Mode -eq 'Startup') { Write-Warning 'STARTUP ONLY: CLI, VPK conversion, native/single skeleton animations, metadata and Chinese resources are NOT included.' }
if ($CheckOnly) { Write-Host 'All allowlisted source files and production artifact inputs validated. No ZIP has been written.'; return }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$outDir = if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { [IO.Path]::GetFullPath((Join-Path $root '非运行文件\打包输出')) } else { [IO.Path]::GetFullPath($OutputDirectory) }
# Explicit output directories let verification keep generated ZIPs outside the user's installation.
# Validate every existing ancestor before creating anything, including when the caller selects another directory.
$ancestorPath = $outDir
while (-not [string]::IsNullOrWhiteSpace($ancestorPath)) {
    if (Test-Path -LiteralPath $ancestorPath) {
        $ancestor = Get-Item -LiteralPath $ancestorPath
        if (-not $ancestor.PSIsContainer -or ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Output path must contain only real directories.' }
    }
    $parent = [IO.Directory]::GetParent($ancestorPath)
    $ancestorPath = if ($null -eq $parent) { $null } else { $parent.FullName }
}
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$time = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTimeOffset]::UtcNow, 'China Standard Time').ToString('yyyyMMdd-HHmmss')
$name = 'HD2ModManager-' + $managerVersion + '-skeleton-test-win-x64-' + $Mode.ToLowerInvariant() + '-' + $time + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$zipPath = Join-Path $outDir ($name + '.zip')
$partial = $zipPath + '.partial'
$folder = 'HD2ModManager/'
$artifactRecords = @()
$artifactWork = $null
if ($Mode -eq 'Full') {
    $artifactWork = Join-Path $outDir ('.physics-' + [Guid]::NewGuid().ToString('N'))
    & dotnet $helper physics $root $artifactWork
    if ($LASTEXITCODE -ne 0) { throw 'Production physics export failed. No completed ZIP was published.' }
    $proof = Get-Content -LiteralPath (Join-Path $artifactWork 'physics-provenance.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $physicsZip = Join-Path $artifactWork 'physics-runtime.zip'
    if ($proof.owner -ne $artifacts[0].addonId -or $proof.guid -ne $artifacts[0].modGuid -or (Get-LiteralSha256 $physicsZip) -ne $proof.zipSha256 -or (Get-LiteralSha256 (Join-Path $root 'HD2ModCore.dll')) -ne $proof.inputs.'HD2ModCore.dll') { throw 'Production artifact provenance mismatch.' }
    $info = Get-Item -LiteralPath $physicsZip
    $sources += [pscustomobject]@{ Relative = $artifacts[0].path; Path = $physicsZip; Size = $info.Length; ModifiedTicks = $info.LastWriteTimeUtc.Ticks; Hash = $null }
    $artifactRecords += [pscustomobject]@{ path = $folder + $artifacts[0].path; provenance = $proof }
}
$entryRecords = New-Object 'System.Collections.Generic.List[object]'
$settings = $manifest.settings | ConvertTo-Json -Depth 10 | ConvertFrom-Json
if ($Mode -eq 'Startup') { $settings.Language = 'en-US' }
$readme = @"
HD2ModManager skeleton-test portable package ($managerVersion / $Mode / win-x64)

GUI display: 基于$managerVersion 骨架测试. Program self-update controls and
background update checks/downloads/installation are disabled in this build.
Skeleton animation import prompts and the dual-skeleton option default off;
enable them explicitly in Settings when needed.

Install Microsoft .NET 10 Desktop Runtime x64 before launching HD2ModManager.exe.
Also install Microsoft Visual C++ v14 x64 Redistributable (2015-2022 or newer).
Sodium needs VCRUNTIME140; texconv also needs MSVCP140/VCOMP140/VCRUNTIME140_1.
These machine-wide prerequisites are not counted in this ZIP's file total.
Extract this entire folder to a writable location. Do not run inside the ZIP.
Choose your own game-data directory and Mod library in Settings.
Personal paths, active profiles, user libraries, game files, indexes, logs, caches,
PDBs, BAKs, tests and experimental delivery ZIPs are excluded.
Full additionally includes runtime companions at 运行时配套/物理运行时.zip:
a production physics package generated from this installation's Core assembly,
with root manifest.json and three patch files (Arsenal direct-import layout).
Import the physics ZIP into your Mod manager, enable ONE physics runtime,
redeploy and completely restart the game. Requires a compatible shared loader
and character patches containing physics parameters. Do not enable both the
built-in and external physics runtimes. Physics is independent of grip options.
Startup does NOT include this artifact and remains a loader-only diagnostic.
Full includes the production B3 generator and independent FP Source module.
Each dual-skeleton model export automatically creates its own base-runtime ZIP
and options-panel ZIP; import them separately. Model-specific test ZIPs are not
used as templates or included. Physics remains an independent companion.
Automatic metadata/index checks and built-in Lua/physics are off in the fresh
settings. Configure them explicitly for your own library; installed settings
and the original library have NOT been changed by packaging.

Full: includes CLI, VPK tools, embedded CPython 3.11 x64, LZ4, metadata,
Chinese resources, material tools and native/single skeleton reference bundles.
Startup: assembly-loader minimum ONLY; it is not a functional distribution.
.NET runtime itself and the game are not included. Full requires ~650 MiB
uncompressed because the two version-matched animation references are needed.

License: GPL-3.0. See LICENSE.txt and third-party license files.
For redistribution, provide the matching source code as required by GPL.
"@
function Add-TextEntry([string]$Relative, [string]$Text) {
    if (-not $seen.Add($Relative)) { throw "Duplicate generated entry: $Relative" }
    $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes($Text)
    $entry = $archive.CreateEntry($folder + $Relative, [IO.Compression.CompressionLevel]::Optimal)
    $stream = $entry.Open()
    try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
    $entryRecords.Add([pscustomobject]@{path=$folder+$Relative;size=$bytes.Length;sha256=$hash})
}
$fileStream = $null; $archive = $null
try {
    $fileStream = [IO.File]::Open($partial,[IO.FileMode]::CreateNew,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    $archive = New-Object IO.Compression.ZipArchive($fileStream,[IO.Compression.ZipArchiveMode]::Create,$true)
    $index = 0
    foreach ($source in $sources) {
        $input = [IO.File]::Open($source.Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        try {
            $sha = [Security.Cryptography.SHA256]::Create()
            try { $source.Hash = [BitConverter]::ToString($sha.ComputeHash($input)).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
            $input.Position = 0
            $entry = $archive.CreateEntry($folder + $source.Relative,[IO.Compression.CompressionLevel]::Optimal)
            $modified = (Get-Item -LiteralPath $source.Path).LastWriteTime
            if ($modified.Year -ge 1980 -and $modified.Year -le 2107) { $entry.LastWriteTime = [DateTimeOffset]$modified }
            $output = $entry.Open()
            try { $input.CopyTo($output) } finally { $output.Dispose() }
        } finally { $input.Dispose() }
        $entryRecords.Add([pscustomobject]@{path=$folder+$source.Relative;size=$source.Size;sha256=$source.Hash})
        $index++
        Write-Progress -Activity 'Building ZIP' -Status $source.Relative -PercentComplete ([int](100*$index/$sources.Count))
    }
    Add-TextEntry 'settings.json' ($settings | ConvertTo-Json -Depth 10)
    Add-TextEntry 'PACKAGE-README.txt' $readme
    Add-TextEntry 'LICENSE.txt' (Get-Content -LiteralPath $licensePath -Raw -Encoding UTF8)
} finally {
    if ($archive) { $archive.Dispose() }
    if ($fileStream) { $fileStream.Dispose() }
    Write-Progress -Activity 'Building ZIP' -Completed
}
# Verify every entry's length and SHA256 without extracting into the installation.
$reader = [IO.Compression.ZipFile]::OpenRead($partial)
try {
    if ($reader.Entries.Count -ne $entryRecords.Count) { throw 'ZIP entry count mismatch.' }
    foreach ($record in $entryRecords) {
        $entry = $reader.GetEntry($record.path)
        if ($null -eq $entry -or $entry.Length -ne $record.size) { throw "ZIP length mismatch: $($record.path)" }
        $stream = $entry.Open(); $sha = [Security.Cryptography.SHA256]::Create()
        try { $hash = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose(); $stream.Dispose() }
        if ($hash -ne $record.sha256) { throw "ZIP hash mismatch: $($record.path)" }
    }
} finally { $reader.Dispose() }
foreach ($source in $sources) {
    $info = Get-Item -LiteralPath $source.Path
    if ($info.Length -ne $source.Size -or $info.LastWriteTimeUtc.Ticks -ne $source.ModifiedTicks -or (Get-LiteralSha256 $source.Path) -ne $source.Hash) {
        throw "Source changed during packaging. Retry after maintenance finishes: $($source.Relative)"
    }
}
# The assembly shipped in this ZIP must be the same assembly that generated
# its companion, even if maintenance happened between export and compression.
foreach ($artifact in $artifactRecords) {
    foreach ($dependency in $artifact.provenance.inputs.PSObject.Properties) {
        $matched = @($sources | Where-Object { $_.Relative -eq $dependency.Name })
        if ($matched.Count -ne 1 -or $matched[0].Hash -ne $dependency.Value) { throw "Production companion/packaged assembly mismatch: $($dependency.Name)" }
    }
}
Move-Item -LiteralPath $partial -Destination $zipPath
$zipHash = (Get-LiteralSha256 $zipPath)
# Only remove this invocation's private workspace after all readbacks pass.
if ($artifactWork) {
    $resolved = [IO.Path]::GetFullPath($artifactWork)
    $outputPrefix = $outDir.TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($outputPrefix, [StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notmatch '^\.physics-[a-f0-9]{32}$') { throw 'Unsafe artifact cleanup path.' }
    if ((Get-Item -LiteralPath $resolved).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unsafe linked artifact workspace.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
$report = [ordered]@{managerVersion=$managerVersion;buildFlavor='skeleton-test';selfUpdatesEnabled=$false;mode=$Mode;platform='win-x64';fileCount=$entryRecords.Count;payloadCount=$relativeFiles.Count;generatedArtifactCount=$artifactRecords.Count;productionArtifacts=$artifactRecords;modelRuntimeCompanions=$b3Capabilities;uncompressedBytes=($entryRecords|Measure-Object size -Sum).Sum;zipBytes=(Get-Item -LiteralPath $zipPath).Length;sha256=$zipHash;entries=$entryRecords.ToArray()}
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath ($zipPath+'.manifest.json') -Encoding UTF8
Write-Host ("SUCCESS: {0}" -f $zipPath)
Write-Host ("{0} entries; {1:N2} MiB ZIP; SHA256 {2}" -f $entryRecords.Count,($report.zipBytes/1MB),$zipHash)




