[CmdletBinding()]
param([string] $InstallationRoot, [string] $OutputDirectory)
# Keep the accepted physics/legacy resources byte-for-byte; add only production B3.
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ([string]::IsNullOrWhiteSpace($InstallationRoot)) {
    $InstallationRoot = Join-Path $root 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7'
}
$install = [IO.Path]::GetFullPath($InstallationRoot)
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $root ('tmp\b3-production-resource-freeze-' + [Guid]::NewGuid().ToString('N'))
}
$temp = [IO.Path]::GetFullPath($OutputDirectory)
$prefix = $root.TrimEnd('\') + '\'
if (!$temp.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Resource work directory must be inside this repository.' }
if (Test-Path -LiteralPath $temp) { throw 'Choose a new empty resource work directory.' }
New-Item -ItemType Directory -Path $temp | Out-Null
$corePath = Join-Path $install 'HD2ModCore.dll'
$ctx = [System.Runtime.Loader.AssemblyLoadContext]::new('b3-installed-resource-baseline', $true)
$xml = [Xml.Linq.XDocument]::Parse('<Project/>')
$target = [Xml.Linq.XElement]::Parse('<Target/>')
$target.SetAttributeValue('Name', 'FreezeInstalledLegacyResourcesForB3')
$target.SetAttributeValue('BeforeTargets', 'AssignTargetPaths')
$target.SetAttributeValue('Condition', ("'" + '$(MSBuildProjectName)' + "' == 'HD2ModCore'"))
$items = [Xml.Linq.XElement]::Parse('<ItemGroup/>')
$remove = [Xml.Linq.XElement]::Parse('<EmbeddedResource/>')
$remove.SetAttributeValue('Remove', '@(EmbeddedResource)'); $items.Add($remove)
$rows = @(); $index = 0
try {
    $core = $ctx.LoadFromAssemblyPath($corePath)
    foreach ($name in $core.GetManifestResourceNames()) {
        if ($name -like '*.PhysBone.Production.*') { continue }
        $stream = $core.GetManifestResourceStream($name); $memory = [IO.MemoryStream]::new()
        try { $stream.CopyTo($memory); $data = $memory.ToArray() } finally { $stream.Dispose(); $memory.Dispose() }
        $file = Join-Path $temp ('legacy-{0:D3}.bin' -f $index); [IO.File]::WriteAllBytes($file, $data)
        $item = [Xml.Linq.XElement]::Parse('<EmbeddedResource/>')
        $item.SetAttributeValue('Include', $file); $item.SetAttributeValue('LogicalName', $name); $items.Add($item)
        $rows += @{ name=$name; sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($data)) }; $index++
    }
} finally { $core=$null; $ctx.Unload(); $ctx=$null }
$production = @()
$names = @('native_grip_transfer.lua','native_grip_entry.lua','native_first_person_guard.lua','attachment_fix_runtime.lua',
    'first_person_source.lua','attachment_option_switches.lua','fp_arm_hidden_mode.lua','attachment_repair_policy.json')
foreach ($name in $names) {
    $file = Join-Path $root ('HD2PhysBoneCompat\src\production\' + $name)
    $logical = 'HD2ModCore.PhysBone.Production.' + $name
    $item = [Xml.Linq.XElement]::Parse('<EmbeddedResource/>')
    $item.SetAttributeValue('Include', $file); $item.SetAttributeValue('LogicalName', $logical); $items.Add($item)
    $production += @{ name=$logical; sha256=(Get-FileHash -LiteralPath $file).Hash }
}
if ($rows.Count -ne 31 -or $production.Count -ne 8) { throw 'Unexpected accepted legacy or production B3 resource set.' }
$target.Add($items); $xml.Root.Add($target); $path = Join-Path $temp 'b3-isolation.targets'; $xml.Save($path)
@{ installation=$install; coreSha256=(Get-FileHash -LiteralPath $corePath).Hash; legacy=$rows; added=$production; targets=$path } |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $temp 'resource-baseline.json') -Encoding utf8
Write-Output $path
