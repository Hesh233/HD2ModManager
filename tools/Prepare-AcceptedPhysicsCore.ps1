[CmdletBinding()]
param([string]$InstallationRoot,[string]$OutputDirectory,[string]$PhysicalSourceDirectory)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(!$InstallationRoot){$InstallationRoot=Join-Path $root 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7'}
if(!$OutputDirectory){$OutputDirectory=Join-Path $root 'outputs\test1201-source2-accepted-20261111\resource-freeze'}
$prefix=$root.TrimEnd('\')+'\';$temp=[IO.Path]::GetFullPath($OutputDirectory)
if(!$temp.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $temp)){throw 'Choose a new resource directory inside the workspace'}
New-Item -ItemType Directory -Path $temp|Out-Null
$baseline=Join-Path $InstallationRoot 'HD2ModCore.dll';$hash=(Get-FileHash -LiteralPath $baseline).Hash
Copy-Item -LiteralPath $baseline -Destination (Join-Path $temp 'installed-baseline.dll')
$ctx=[System.Runtime.Loader.AssemblyLoadContext]::new('accepted-physics-resource-baseline',$true)
$xml=[Xml.Linq.XDocument]::Parse('<Project/>');$target=[Xml.Linq.XElement]::Parse('<Target/>')
$target.SetAttributeValue('Name','FreezeNonPhysicalInstalledResources');$target.SetAttributeValue('BeforeTargets','AssignTargetPaths');$target.SetAttributeValue('Condition',("'"+'$(MSBuildProjectName)' + "' == 'HD2ModCore'"))
$items=[Xml.Linq.XElement]::Parse('<ItemGroup/>');$remove=[Xml.Linq.XElement]::Parse('<EmbeddedResource/>');$remove.SetAttributeValue('Remove','@(EmbeddedResource)');$items.Add($remove)
if(!$PhysicalSourceDirectory){$PhysicalSourceDirectory=Join-Path $root 'outputs\test1201-source2-accepted-20261111\formal'}
if(![IO.Path]::GetFullPath($PhysicalSourceDirectory).StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Physical source directory escapes workspace'}
$replacement=@{'HD2ModCore.PhysBone.physbone_compat.lua'=Join-Path $PhysicalSourceDirectory 'physbone_compat.lua';'HD2ModCore.PhysBone.physbone_runtime.lua'=Join-Path $PhysicalSourceDirectory 'physbone_runtime.lua'}
$rows=@();$i=0
try{
 $a=$ctx.LoadFromAssemblyPath((Join-Path $temp 'installed-baseline.dll'));$identity=$a.FullName
 foreach($n in $a.GetManifestResourceNames()){
  $stream=$a.GetManifestResourceStream($n);$memory=[IO.MemoryStream]::new();$stream.CopyTo($memory);$data=$memory.ToArray();$stream.Dispose();$memory.Dispose()
  $file=Join-Path $temp ('resource-{0:D3}.bin' -f $i);[IO.File]::WriteAllBytes($file,$data)
  $include=if($replacement.ContainsKey($n)){$replacement[$n]}else{$file}
  $item=[Xml.Linq.XElement]::Parse('<EmbeddedResource/>');$item.SetAttributeValue('Include',$include);$item.SetAttributeValue('LogicalName',$n);$items.Add($item)
  $rows+=@{name=$n;beforeSha256=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($data));include=$include;afterSha256=(Get-FileHash -LiteralPath $include).Hash};$i++
 }
}finally{$a=$null;$ctx.Unload();$ctx=$null}
if(@($rows|Where-Object {$replacement.ContainsKey($_.name)}).Count -ne 2){throw 'Missing production physics resources'}
if((Get-FileHash -LiteralPath $baseline).Hash -ne $hash){throw 'Installation changed during resource snapshot'}
$target.Add($items);$xml.Root.Add($target);$targets=Join-Path $temp 'physics233-isolation.targets';$xml.Save($targets)
@{installation=$InstallationRoot;coreSha256=$hash;identity=$identity;resources=$rows;allowedResources=@($replacement.Keys);targets=$targets}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $temp 'baseline.json') -Encoding utf8
Write-Output "Prepared $i resources; only 2 physical resources substituted. $targets"
