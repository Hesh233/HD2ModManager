[CmdletBinding()]
param([string]$InstallationRoot, [switch]$Apply, [switch]$IncludeStaticSupport, [string]$BackupRoot)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
function Get-LiteralSha256([string]$Path) {
    $stream = [IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','') } finally { $sha.Dispose(); $stream.Dispose() }
}
function Get-BytesSha256([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($Bytes)).Replace('-','') } finally { $sha.Dispose() }
}
function Assert-RealDirectoryPath([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while (-not [string]::IsNullOrWhiteSpace($current)) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current
            if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Linked/non-directory path refused: $current" }
        }
        $parent = [IO.Directory]::GetParent($current)
        $current = if ($null -eq $parent) { $null } else { $parent.FullName }
    }
}
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if ([string]::IsNullOrWhiteSpace($InstallationRoot)) { $InstallationRoot = Join-Path $repo 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7' }
$root = [IO.Path]::GetFullPath($InstallationRoot)
if (-not (Test-Path -LiteralPath (Join-Path $root 'HD2ModManager.dll') -PathType Leaf)) { throw 'Not a manager installation.' }
$target = [IO.Path]::GetFullPath((Join-Path $root '非运行文件\打包工具'))
$rootPrefix = $root.TrimEnd('\') + '\'
if (-not $target.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe target.' }
# Bind the packaging manifest to this installation, not a historical directory name or another backend's metadata.
$managerAssemblyVersion = [Reflection.AssemblyName]::GetAssemblyName((Join-Path $root 'HD2ModManager.dll')).Version
$managerVersion = '{0}.{1}.{2}' -f $managerAssemblyVersion.Major,$managerAssemblyVersion.Minor,$managerAssemblyVersion.Build
$buildInfoPath = Join-Path $root 'anim_batch_mod\build-info.json'
$buildInfo = Get-Content -LiteralPath $buildInfoPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($buildInfo.managerVersion -ne $managerVersion) { throw 'Installed GUI and build-info versions differ; preserve configuration and synchronize the program metadata first.' }
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'package-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$boundFields = @('managerVersion','runtimeCompanionVersion','firstPersonSourceVersion','attachmentRepairPolicyVersion','attachmentRepairPolicyRevision','attachmentRepairPolicySha256','attachmentFixConfigSha256','physicsRuntimeVersion','physicsCompatVersion','directPhysicsRuntimeVersion','directPhysicsCompatVersion','physicsRouteVersion','physicsRoutingPolicy','physicsSourceFiles')
foreach ($name in $boundFields) {
    $manifest.PSObject.Properties.Remove($name)
    $property = $buildInfo.PSObject.Properties[$name]
    if ($null -ne $property) { $manifest | Add-Member -NotePropertyName $name -NotePropertyValue $property.Value }
}
$manifest.managerVersion = $managerVersion
$manifestBytes = (New-Object Text.UTF8Encoding($false)).GetBytes(($manifest | ConvertTo-Json -Depth 20 -Compress) + [Environment]::NewLine)
# Normal and test installations retain their different physics backends. Full packaging still validates Core/Python/policy/config hashes.
# Existing generation-chain descriptions are intentionally NOT overwritten during an ordinary launcher/tool sync.
$staticPayloads = if ($IncludeStaticSupport) { @('生成链版本.txt') } else { @() }
foreach ($name in $staticPayloads) { if ($name -notin @($manifest.full)) { throw "Static support payload is not in the Full manifest: $name" } }
$entries = @(foreach ($name in @('Package-Manager.ps1','package-manifest.json','README.md','项目许可证.txt','ManagerPackageSupport.dll','ManagerPackageSupport.deps.json','ManagerPackageSupport.runtimeconfig.json')) {
    $source = if ($name -like 'ManagerPackageSupport.*') { Join-Path $repo ('tools\ManagerPackageSupport\bin\Release\net10.0\' + $name) } else { Join-Path $PSScriptRoot $name }
    [pscustomobject]@{ Source=$source; Target=(Join-Path $target $name); GeneratedBytes=$(if ($name -eq 'package-manifest.json') { $manifestBytes } else { $null }) }
})
$entries += [pscustomobject]@{ Source=(Join-Path $PSScriptRoot 'Package-HD2ModManager.bat'); Target=(Join-Path $root 'Package-HD2ModManager.bat'); GeneratedBytes=$null }
$entries += @(foreach ($name in $staticPayloads) { [pscustomobject]@{ Source=(Join-Path $PSScriptRoot $name); Target=(Join-Path $root $name); GeneratedBytes=$null } })
$plans = @(foreach ($entry in $entries) {
    if (-not (Test-Path -LiteralPath $entry.Source -PathType Leaf)) { throw "Missing packaging/static support source: $($entry.Source). Build the support helper if needed." }
    $sourceInfo = Get-Item -LiteralPath $entry.Source
    if ($sourceInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked support source refused: $($entry.Source)" }
    $dest = [IO.Path]::GetFullPath($entry.Target)
    if (-not $dest.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe support destination.' }
    $hash = if ($null -ne $entry.GeneratedBytes) { Get-BytesSha256 $entry.GeneratedBytes } else { Get-LiteralSha256 $entry.Source }
    $action = 'Copy'
    if ((Test-Path -LiteralPath $dest -PathType Leaf) -and (Get-LiteralSha256 $dest) -eq $hash) { $action = 'Unchanged' }
    [pscustomobject]@{ Source=$entry.Source; Target=$dest; Hash=$hash; Action=$action; GeneratedBytes=$entry.GeneratedBytes }
})
$backupDirectory = if ([string]::IsNullOrWhiteSpace($BackupRoot)) { Join-Path $target '验证记录' } else { [IO.Path]::GetFullPath($BackupRoot) }
if ($Apply) {
    if (-not (Test-Path -LiteralPath $target -PathType Container)) { throw 'The fixed packaging directory must already exist.' }
    foreach ($plan in $plans) {
        Assert-RealDirectoryPath (Split-Path -Parent $plan.Target)
        if (Test-Path -LiteralPath $plan.Target) {
            $existing = Get-Item -LiteralPath $plan.Target
            if ($existing.PSIsContainer -or ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Invalid target file.' }
            if ($plan.Action -eq 'Copy') {
                if (-not (Test-Path -LiteralPath $backupDirectory -PathType Container)) { throw 'Existing verification directory required for backups; optionally pass -BackupRoot.' }
                Assert-RealDirectoryPath $backupDirectory
            }
        }
    }
    foreach ($plan in $plans) {
        if (Test-Path -LiteralPath $plan.Target) {
            $oldHash = Get-LiteralSha256 $plan.Target
            if ($oldHash -eq $plan.Hash) { continue }
            $backup = Join-Path $backupDirectory ((Split-Path -Leaf $plan.Target) + '.before-' + $oldHash.Substring(0,16))
            if (-not (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $plan.Target -Destination $backup }
            if ((Get-LiteralSha256 $backup) -ne $oldHash) { throw 'Packaging backup mismatch.' }
        }
        if ($null -ne $plan.GeneratedBytes) { [IO.File]::WriteAllBytes($plan.Target,[byte[]]$plan.GeneratedBytes) }
        else { Copy-Item -LiteralPath $plan.Source -Destination $plan.Target -Force }
        if ((Get-LiteralSha256 $plan.Target) -ne $plan.Hash) { throw 'Packaging support copy mismatch.' }
    }
}
Write-Output ($plans | Select-Object Source,Target,Hash,Action | ConvertTo-Json -Depth 4)
Write-Output "Packaging launcher/tool sync: Apply=$Apply; GUI=$managerVersion; IncludeStaticSupport=$IncludeStaticSupport. No Core/GUI/config/library/game writes."
