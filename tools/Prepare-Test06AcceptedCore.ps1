param([switch]$FreezeAllInstalledResources)
# Builds the already validated physical source with every other installed resource frozen.
$ErrorActionPreference='Stop'
$root=(Get-Location).Path
$install=Join-Path $root 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7'
$audit=Join-Path $root 'outputs\test06-vrd-skirt-analysis-20261109'
$temp=Join-Path $root 'tmp\lua-boot'
$proof=if(!$FreezeAllInstalledResources){Get-Content -LiteralPath (Join-Path $audit 'fix-package-readback.json') -Raw|ConvertFrom-Json}else{$null}
$source=Join-Path $install 'HD2ModCore.dll'
$baseline=Join-Path $temp 'physics131-installed-baseline.dll'
$sourceHash=(Get-FileHash -LiteralPath $source).Hash
Copy-Item -LiteralPath $source -Destination $baseline -Force
if((Get-FileHash -LiteralPath $baseline).Hash -ne $sourceHash){throw 'Baseline copy mismatch'}
$context=[System.Runtime.Loader.AssemblyLoadContext]::new('test06-resource-baseline',$true)
$assembly=$context.LoadFromAssemblyPath($baseline)
$identity=$assembly.FullName
$rows=@();$index=0
foreach($name in $assembly.GetManifestResourceNames()){
 $stream=$assembly.GetManifestResourceStream($name)
 $memory=[IO.MemoryStream]::new();$stream.CopyTo($memory);$stream.Dispose()
 $bytes=$memory.ToArray();$memory.Dispose()
 $file=Join-Path $temp ('physics131-resource-{0:D3}.bin' -f $index)
 [IO.File]::WriteAllBytes($file,$bytes)
 $rows+=@{name=$name;path=$file;sha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))}
 $index++
}
$assembly=$null;$context.Unload();$context=$null
[GC]::Collect();[GC]::WaitForPendingFinalizers();[GC]::Collect()
if((Get-FileHash -LiteralPath $source).Hash -ne $sourceHash){throw 'Installed Core changed during extraction'}
$resources=if($FreezeAllInstalledResources){@{}}else{@{
 'HD2ModCore.PhysBone.physbone_compat.lua'=Join-Path $root 'HD2PhysBoneCompat\src\physbone_compat.lua'
 'HD2ModCore.PhysBone.physbone_runtime.lua'=Join-Path $root 'HD2PhysBoneCompat\src\physbone_runtime.lua'
}}
foreach($pair in @(@('HD2ModCore.PhysBone.physbone_compat.lua','compat'),@('HD2ModCore.PhysBone.physbone_runtime.lua','runtime'))){
 if($FreezeAllInstalledResources){break}
 $bytes=[IO.File]::ReadAllBytes($resources[$pair[0]])
 $text=[Text.Encoding]::UTF8.GetString($bytes).Replace("`r`n","`n")
 $hash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($text)))
 if($hash -ne $proof.sourceSha256.($pair[1])){throw 'Physical source differs from accepted package'}
}
$xml=[Xml.Linq.XDocument]::Load((Join-Path $temp 'physics130-isolation.targets'))
$items=$xml.Root.Element('Target').Element('ItemGroup').Elements('EmbeddedResource')
$known=@{}
foreach($item in $items){
 if(!$item.Attribute('Include')){continue}
 $name=$item.Attribute('LogicalName').Value
 $known[$name]=$true
 $row=@($rows|Where-Object {$_.name -eq $name})
 if($row.Count -ne 1){throw "Installed manifest changed: $name"}
 $file=if($resources.ContainsKey($name)){$resources[$name]}else{$row[0].path}
 $item.SetAttributeValue('Include',$file)
}
if($known.Count -ne $rows.Count){throw 'Installed resource count differs from isolation template'}
$targets=Join-Path $temp $(if($FreezeAllInstalledResources){'arsenal-flat-isolation.targets'}else{'physics131-isolation.targets'})
$xml.Save($targets)
@{installedCore=$source;installedCoreSha256=$sourceHash;assemblyIdentity=$identity;resources=$rows;target=$targets;allowedResources=@($resources.Keys)}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $audit $(if($FreezeAllInstalledResources){'arsenal-flat-resource-baseline.json'}else{'accepted-resource-baseline.json'})) -Encoding utf8
Write-Output "Prepared $($rows.Count) installed resources; $($resources.Count) accepted physical resources substituted. FreezeAll=$FreezeAllInstalledResources"
