[CmdletBinding()]
param(
    [string] $TargetDirectory = 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7',
    [string] $PublishedDirectory = 'outputs\single-hd2-fix-20261106\manager',
    [switch] $SkipBuild,
    [switch] $ManagedOnly
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
function In-Repo([string] $Path) {
    $full = [IO.Path]::GetFullPath($(if ([IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path $repo $Path }))
    if (!$full.StartsWith($repo + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path must stay inside the manager workspace: $full"
    }
    return $full
}
$target = In-Repo $TargetDirectory
$publish = In-Repo $PublishedDirectory
$fixedTarget = In-Repo 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7'
if ($target -ne $fixedTarget) { throw 'Reuse the user-designated manager-1.0.7 directory; do not create another release directory.' }
if (!(Test-Path -LiteralPath $target -PathType Container) -or !(Test-Path -LiteralPath $publish -PathType Container)) {
    throw 'Target and reusable build staging directories must already exist; this updater does not create directories.'
}
if ($target -eq $publish) { throw 'Publish staging must differ from the user-configured installation.' }
if ($ManagedOnly) {
    $sourceRoot = In-Repo 'HD2ModManager\bin\Release\net10.0-windows'
    $names = @('HD2ModManager','hd2mod','HD2ModCore','HD2SourceModel','HD2SourceMigration')
    $plan = @()
    foreach ($name in $names) { foreach ($extension in '.dll','.pdb') {
        $file = $name + $extension
        $moduleRoot = switch($name) {
            'HD2ModManager' { $sourceRoot }
            'hd2mod' { In-Repo 'HD2ModCli\bin\Release\net10.0' }
            'HD2ModCore' { In-Repo 'HD2ModCore\bin\Release\net8.0' }
            'HD2SourceModel' { In-Repo 'HD2SourceModel\bin\Release\net8.0' }
            'HD2SourceMigration' { In-Repo 'HD2SourceMigration\bin\Release\net8.0' }
        }
        $source = In-Repo (Join-Path $moduleRoot $file)
        if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing compiled file $source" }
        $hash = (Get-FileHash -LiteralPath $source).Hash
        foreach ($directory in @($target,$publish)) {
            $destination = In-Repo (Join-Path $directory $file)
            if (!(Test-Path -LiteralPath $destination -PathType Leaf)) { throw "Missing existing target $destination" }
            $old = (Get-FileHash -LiteralPath $destination).Hash
            $plan += [ordered]@{ source=$source;target=$destination;sha256=$hash;previousSha256=$old;changed=($old -ne $hash) }
        }
    } }
    # Preflight every target before any copy; never close or overwrite a running manager.
    foreach ($item in $plan | Where-Object {$_.changed}) {
        $probe = [IO.File]::Open($item.target,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
        $probe.Dispose()
    }
    foreach ($item in $plan | Where-Object {$_.changed}) {
        $backup = $item.target + '.before-wrist-config-hand-follow-20261108.bak'
        if (!(Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $item.target -Destination $backup }
        Copy-Item -LiteralPath $item.source -Destination $item.target -Force
    }
    foreach ($item in $plan) {
        if ((Get-FileHash -LiteralPath $item.target).Hash -ne $item.sha256) { throw "Managed update verification failed: $($item.target)" }
    }
    @{status='PASS';managedOnly=$true;files=$plan;gameDeployed=$false;updatedUtc=[DateTimeOffset]::UtcNow.ToString('o')} |
        ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $target '归档\测试报告\腕配置手部联动-工具同步-20261108.json') -Encoding utf8
    Write-Output "Verified $($plan.Count) managed targets; updated $(@($plan | Where-Object {$_.changed}).Count). Python/config/library/game unchanged."
    return
}
if (!$SkipBuild) {
    & (Join-Path $PSScriptRoot 'BuildNativeRuntime.ps1')
    & dotnet publish (Join-Path $repo 'HD2ModManager\HD2ModManager.csproj') -c Release --no-restore -p:CETCompat=false -o $publish -v minimal
    if ($LASTEXITCODE -ne 0) { throw 'Manager publish failed.' }
}
$info = Get-Content -LiteralPath (Join-Path $publish 'anim_batch_mod\build-info.json') -Raw | ConvertFrom-Json
if ($info.pipelineVersion -ne '1.0.15' -or $info.singleSkeletonPipelineVersion -ne '1.0.21' -or $info.singleOutputEncodingProfile -ne 'single-constant-float-boundary2-v1' -or $info.singleProcessingProfile -ne 'standard-single-v3-normal-reference' -or $info.singlePlaybackRevision -ne 'normal-reference-r2') {
    throw 'Refusing an old or mixed runtime without the single HD2 bind fix.'
}
foreach ($file in $info.files) {
    if ((Get-FileHash -LiteralPath (Join-Path $publish ('anim_batch_mod\' + $file.name)) -Algorithm SHA256).Hash -ne $file.sha256) {
        throw "Published Python source differs from build-info: $($file.name)"
    }
}
foreach ($file in $info.presetFiles) {
    if ((Get-FileHash -LiteralPath (Join-Path $publish ('anim_batch_mod\' + $file.name)) -Algorithm SHA256).Hash -ne $file.sha256) { throw "Published template differs from build-info: $($file.name)" }
}
foreach ($required in @('anim_batch_mod\single_animation_compaction.py','anim_batch_mod\playback_reference.py','anim_batch_mod\presets\single-normal-reference\playback.zip','HD2ModManager.dll','HD2ModCore.dll','HD2SourceMigration.dll','hd2mod.dll','anim_batch_mod\single_skeleton.py')) {
    if (!(Test-Path -LiteralPath (Join-Path $publish $required))) { throw "Incomplete publish: $required" }
}
# Existing presets/configuration are user-owned. The new single converter normalizes
# the old rotation_compensation=false setting without overwriting the user's TOML.
$protected = @('settings.json','config.toml','config\attachment-fix.json')
$protectedHashes = @{}
foreach ($relative in $protected) {
    $path = In-Repo (Join-Path $target $relative)
    if (Test-Path -LiteralPath $path -PathType Leaf) { $protectedHashes[$relative] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }
}
function Test-PackageOwnedPath([string] $relative) {
    $segments = $relative.Replace([char]92, [char]47).Split([char]47)
    return ($segments[0] -notin @('data','cache','logs','test-library','isolated-library','config') -and
        $segments -notcontains '__pycache__' -and $relative -notin @('settings.json','config.toml') -and $relative -notmatch '\.bak$')
}
$files = @(Get-ChildItem -LiteralPath $publish -Recurse -File | Where-Object {
    Test-PackageOwnedPath $_.FullName.Substring($publish.Length + 1)
})
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$changes = @()
$requiredDirectories = @()
# Finish every validation and lock check before backing up or copying anything.
foreach ($source in $files) {
    $relative = $source.FullName.Substring($publish.Length + 1)
    $destination = In-Repo (Join-Path $target $relative)
    if (!(Test-Path -LiteralPath (Split-Path -Parent $destination) -PathType Container)) {
        if ($relative.Replace([char]92,[char]47) -ne 'anim_batch_mod/presets/single-normal-reference/playback.zip') {
            throw "Would require an unexpected directory: $relative. No files have been updated."
        }
        $requiredDirectories += (Split-Path -Parent $destination)
    }
    $hash = (Get-FileHash -LiteralPath $source.FullName -Algorithm SHA256).Hash
    $oldHash = if (Test-Path -LiteralPath $destination -PathType Leaf) { (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash } else { $null }
    if ($oldHash -eq $hash) { continue }
    if ($oldHash -and $relative -match '\.(dll|exe)$') {
        $probe = [IO.File]::Open($destination, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        $probe.Dispose()
    }
    $backup = if ($oldHash) { In-Repo ($destination + '.before-update-' + $stamp + '.bak') } else { $null }
    $changes += [ordered]@{ path=$relative; source=$source.FullName; destination=$destination; previousSha256=$oldHash; sha256=$hash; backupFile=$backup }
}
if (!$changes.Count) { Write-Output 'Manager is already up to date; no files or directories were created.'; return }
# Recovery copies are files beside the originals, not new backup/release directories.
foreach ($change in $changes) {
    if ($change.backupFile) {
        Copy-Item -LiteralPath $change.destination -Destination $change.backupFile
        if ((Get-FileHash -LiteralPath $change.backupFile -Algorithm SHA256).Hash -ne $change.previousSha256) { throw "Backup hash mismatch: $($change.path)" }
    }
}
foreach ($directory in $requiredDirectories) { New-Item -ItemType Directory -Force -Path (In-Repo $directory) | Out-Null }
foreach ($change in $changes) {
    Copy-Item -LiteralPath $change.source -Destination $change.destination -Force
    if ((Get-FileHash -LiteralPath $change.destination -Algorithm SHA256).Hash -ne $change.sha256) { throw "Update hash mismatch: $($change.path)" }
}
foreach ($relative in $protectedHashes.Keys) {
    if ((Get-FileHash -LiteralPath (Join-Path $target $relative) -Algorithm SHA256).Hash -ne $protectedHashes[$relative]) {
        throw "User configuration changed unexpectedly: $relative"
    }
}
$manifest = [ordered]@{ pipelineVersion=$info.pipelineVersion; singleSkeletonPipelineVersion=$info.singleSkeletonPipelineVersion; singlePlaybackRevision=$info.singlePlaybackRevision;
    target=$target; staging=$publish; updatedUtc=[DateTime]::UtcNow.ToString('o'); changedFiles=$changes;
    preserved=@('settings.json','config.toml','config','data','cache','logs','test-library'); protectedHashes=$protectedHashes;
    createdDirectories=$requiredDirectories; gameDeployed=$false; gameTested=$false }
$manifest | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $target '更新记录.json') -Encoding utf8
"pipelineVersion=$($info.pipelineVersion)`nsingleSkeletonPipelineVersion=$($info.singleSkeletonPipelineVersion)`nsinglePlaybackRevision=$($info.singlePlaybackRevision)`ninstallation=manager-1.0.7`nreuseDirectory=true`nnewReleaseDirectories=false" |
    Set-Content -LiteralPath (Join-Path $target '生成链版本.txt') -Encoding utf8
Write-Output "Updated $($changes.Count) package-owned files in $target. Only required template directories may be created; no new release directory. Recovery copies are adjacent .bak files."
