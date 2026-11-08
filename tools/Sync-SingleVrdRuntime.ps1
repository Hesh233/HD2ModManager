param([switch]$Apply, [ValidateSet('single-vrd-121','front-skirt-122','front-skirt-123')][string]$Revision='single-vrd-121')
$frontSkirt = $Revision -like 'front-skirt-*'
$frontVersion = if($Revision -eq 'front-skirt-123'){'1.2.3'}else{'1.2.2'}
$reportPath = if($frontSkirt){"outputs\native-v34-b23-integrated-20261105\manager-1.0.7\归档\测试报告\前裙修复-$frontVersion-同步校验-20261108.json"}else{'outputs\vrd-analysis-20261107\single-vrd-sync-audit.json'}
$allowedResources = @('HD2ModCore.PhysBone.physbone_compat.lua')
if($frontSkirt){$allowedResources += 'HD2ModCore.PhysBone.physbone_runtime.lua'}
$backupSuffix=if($frontSkirt){'.before-'+$Revision+'-20261108.bak'}else{'.before-single-vrd-fix.bak'}
$ErrorActionPreference='Stop'
if($Apply){
 $audit=Get-Content -LiteralPath $reportPath -Raw|ConvertFrom-Json
 if($audit.coreMethodsExact -ne 16744 -or @($audit.changedResources|Where-Object {$_ -notin $allowedResources}).Count){throw 'Missing isolation certification'}
 foreach($p in $audit.plan){
  if((Get-FileHash -LiteralPath $p.source).Hash -ne $p.sourceHash -or (Get-FileHash -LiteralPath $p.target).Hash -ne $p.targetHash){throw "Files changed since certification: $($p.target)"}
  $f=[IO.File]::Open($p.target,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);$f.Dispose()
 }
 foreach($p in $audit.plan){
  $backup=$p.target+$backupSuffix
  if(!(Test-Path -LiteralPath $backup)){Copy-Item -LiteralPath $p.target -Destination $backup}
  Copy-Item -LiteralPath $p.source -Destination $p.target -Force
  if((Get-FileHash -LiteralPath $p.target).Hash -ne $p.sourceHash){throw "Copy failed: $($p.target)"}
 }
 $audit.mode='apply';$audit|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $reportPath -Encoding utf8
 Write-Output "Synced $($audit.plan.Count) certified files."
 return
}
$root=(Get-Location).Path
$install=Join-Path $root 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7'
$stage=Join-Path $root 'outputs\single-hd2-fix-20261106\manager'
$cli=Join-Path $root 'HD2ModCli\bin\Release\net10.0'
$core=if($frontSkirt){Join-Path $root 'HD2ModCore\bin\Release\net8.0\HD2ModCore.dll'}else{Join-Path $root 'outputs\vrd-analysis-20261107\lua-package\export-physics\bin\Release\net8.0\HD2ModCore.dll'}
foreach($p in Get-ChildItem -LiteralPath $cli -Filter *.dll){if($p.Name -notin 'HD2ModCore.dll','hd2mod.dll'){try{[Reflection.Assembly]::LoadFrom($p.FullName)|Out-Null}catch{}}}
$ctx1=[System.Runtime.Loader.AssemblyLoadContext]::new('isolation-before',$true)
$ctx2=[System.Runtime.Loader.AssemblyLoadContext]::new('isolation-after',$true)
$a=$ctx1.LoadFromAssemblyPath((Join-Path $install 'HD2ModCore.dll'))
$b=$ctx2.LoadFromAssemblyPath($core)
function HashMethods($assembly){
 $rows=@{};foreach($t in $assembly.GetTypes()){
  foreach($m in @($t.GetMethods([Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly'))+@($t.GetConstructors([Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly'))){
   $body=$m.GetMethodBody();$key=$t.FullName+'|'+$m.ToString()
   $rows[$key]=if($body){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($body.GetILAsByteArray()))}else{'none'}
  }
 };return $rows
}
$m1=HashMethods $a;$m2=HashMethods $b
if($m1.Count -ne $m2.Count -or @($m1.Keys|Where-Object {$m1[$_] -ne $m2[$_]}).Count){throw 'Core code differs; do not ship unrelated multi-rig changes'}
$changedResources=@();foreach($n in $a.GetManifestResourceNames()){
 $x=$a.GetManifestResourceStream($n);$y=$b.GetManifestResourceStream($n)
 if(!$y){throw "Missing resource $n"}
 if([Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($x)) -ne [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($y))){$changedResources+=$n}
 $x.Dispose();$y.Dispose()
}
if(@($changedResources|Where-Object {$_ -notin $allowedResources}).Count){throw 'Unrelated embedded resources changed'}
if($frontSkirt){
 function HashConstants($assembly){
  $rows=@{};foreach($t in $assembly.GetTypes()){
   foreach($f in $t.GetFields([Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly')){
    if($f.IsLiteral){$rows[$t.FullName+'|'+$f.Name]=[string]$f.GetRawConstantValue()}
   }
  };return $rows
 }
 $c1=HashConstants $a;$c2=HashConstants $b
 if($c1.Count -ne $c2.Count -or @($c1.Keys|Where-Object {$c1[$_] -ne $c2[$_]}).Count){throw 'Core constants differ'}
 if($a.FullName -ne $b.FullName){throw 'Core assembly identity changed'}
 if($a.GetManifestResourceNames().Count -ne $b.GetManifestResourceNames().Count){throw 'Resource count changed'}
}
$oldHashes=@{};$plan=@()
$names=if($frontSkirt){@('HD2ModCore.dll','HD2ModCore.pdb')}else{@('HD2ModCore.dll','HD2SourceModel.dll','HD2SourceMigration.dll')}
foreach($n in $names){
 $source=if($n -like 'HD2ModCore.*'){Join-Path ([IO.Path]::GetDirectoryName($core)) $n}elseif($n -eq 'HD2SourceModel.dll'){Join-Path $root 'HD2SourceModel\bin\Release\net8.0\HD2SourceModel.dll'}else{Join-Path $cli $n}
 $target=Join-Path $install $n;$oldHashes[$n]=(Get-FileHash -LiteralPath $target).Hash
 $plan+=@{source=$source;target=$target;sourceHash=(Get-FileHash -LiteralPath $source).Hash;targetHash=(Get-FileHash -LiteralPath $target).Hash}
 $staged=Join-Path $stage $n
 if(Test-Path -LiteralPath $staged){
  if((Get-FileHash -LiteralPath $staged).Hash -ne $oldHashes[$n]){throw "Staging differs from installed baseline: $n"}
  $plan+=@{source=$source;target=$staged;sourceHash=(Get-FileHash -LiteralPath $source).Hash;targetHash=(Get-FileHash -LiteralPath $staged).Hash}
 }
}
# Release loaded contexts before lock checks/copy. DLLs remain isolated from the running manager.
$a=$null;$b=$null;$ctx1.Unload();$ctx2.Unload();$ctx1=$null;$ctx2=$null
[GC]::Collect();[GC]::WaitForPendingFinalizers();[GC]::Collect()

$result=@{mode=if($Apply){'apply'}else{'preflight'};revision=$Revision;coreMethodsExact=$m1.Count;coreConstantsExact=if($frontSkirt){$c1.Count}else{$null};changedResources=$changedResources;plan=$plan}
if($Apply){
 foreach($p in $plan){
  $backup=$p.target+$backupSuffix
  if(!(Test-Path -LiteralPath $backup)){Copy-Item -LiteralPath $p.target -Destination $backup}
  Copy-Item -LiteralPath $p.source -Destination $p.target -Force
  if((Get-FileHash -LiteralPath $p.source).Hash -ne (Get-FileHash -LiteralPath $p.target).Hash){throw "Copy verification failed: $($p.target)"}
 }
}
$result|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $reportPath -Encoding utf8
Write-Output "Core $($m1.Count) method bodies exact; only revision-allowed Lua resources changed. $($plan.Count) files $($result.mode)."
