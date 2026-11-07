$ErrorActionPreference='Stop'
$root=(Get-Location).Path;$newDir=Join-Path $root 'HD2ModCli\bin\Release\net10.0';$oldDir=Join-Path $root 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7'
foreach($p in Get-ChildItem -LiteralPath $newDir -Filter *.dll){if($p.Name -notin 'HD2SourceMigration.dll','HD2ModCore.dll','HD2SourceModel.dll','hd2mod.dll'){try{[Reflection.Assembly]::LoadFrom($p.FullName)|Out-Null}catch{}}}
[Reflection.Assembly]::LoadFrom((Join-Path $newDir 'HD2SourceModel.dll'))|Out-Null
function Inspect($a){
 $methods=@{};$constants=@{};$resources=@{}
 foreach($t in $a.GetTypes()){
  foreach($m in @($t.GetMethods([Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly'))+@($t.GetConstructors([Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly'))){$b=$m.GetMethodBody();$methods[$t.FullName+'|'+$m.ToString()]=if($b){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($b.GetILAsByteArray()))}else{'none'}}
  foreach($f in $t.GetFields([Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly')){if($f.IsLiteral){$constants[$t.FullName+'|'+$f.Name]=[string]$f.GetRawConstantValue()}}
 }
 foreach($n in $a.GetManifestResourceNames()){$stream=$a.GetManifestResourceStream($n);$resources[$n]=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($stream));$stream.Dispose()}
 return @{methods=$methods;constants=$constants;resources=$resources}
}
$rows=@()
foreach($n in 'HD2ModCore.dll','HD2SourceModel.dll','HD2SourceMigration.dll'){
 $op=Join-Path $oldDir $n;$np=Join-Path $newDir $n;$oh=(Get-FileHash -LiteralPath $op).Hash;$nh=(Get-FileHash -LiteralPath $np).Hash
 $row=@{name=$n;beforeSha256=$oh;afterSha256=$nh;binaryExact=($oh -eq $nh);source=$np}
 if($oh -ne $nh){
  $c1=[System.Runtime.Loader.AssemblyLoadContext]::new('accepted-'+$n,$true);$c2=[System.Runtime.Loader.AssemblyLoadContext]::new('compiled-'+$n,$true)
  $a1=$c1.LoadFromAssemblyPath($op);$a2=$c2.LoadFromAssemblyPath($np);$x=Inspect $a1;$y=Inspect $a2
  foreach($kind in 'methods','constants','resources'){
   $changes=@($x[$kind].Keys|Where-Object {$x[$kind][$_] -ne $y[$kind][$_]})
   if($x[$kind].Count -ne $y[$kind].Count -or $changes.Count){throw "Accepted $n has changed $kind ($($changes.Count)); do not alter its behavior"}
   $row[$kind+'Exact']=$x[$kind].Count
  }
  $row['identityExact']=($a1.FullName -eq $a2.FullName);if(!$row.identityExact){throw 'Assembly identity changed'}
 }
 $rows+=$row
}
@{status='PASS';functionalSourceChange=$false;binaries=$rows}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath 'outputs\vrd-analysis-20261107\accepted-code-equivalence.json' -Encoding utf8
$rows|ForEach-Object {'{0}: byteExact={1}; identicalMethods={2}; identicalResources={3}' -f $_.name,$_.binaryExact,$_.methodsExact,$_.resourcesExact}

