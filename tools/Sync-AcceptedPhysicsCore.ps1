[CmdletBinding()]
param([string]$InstallationRoot,[string]$CandidateDirectory,[string]$ReportPath,[switch]$Apply,[string]$AcceptanceDirectory)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$out=Join-Path $root 'outputs\test1201-source2-accepted-20261111'
if($AcceptanceDirectory){$out=[IO.Path]::GetFullPath($AcceptanceDirectory)}
if(!$out.StartsWith($root.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Acceptance workspace escapes repository'}
if(!$InstallationRoot){$InstallationRoot=Join-Path $root 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7'}
if(!$CandidateDirectory){$CandidateDirectory=Join-Path $out 'candidate'}
if(!$ReportPath){$ReportPath=Join-Path $out 'core-sync.json'}
foreach($p in @($InstallationRoot,$CandidateDirectory,$ReportPath)){if(![IO.Path]::GetFullPath($p).StartsWith($root.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Path escapes workspace'}}
$target=Join-Path $InstallationRoot 'HD2ModCore.dll';$source=Join-Path $CandidateDirectory 'HD2ModCore.dll';$beforeHash=(Get-FileHash -LiteralPath $target).Hash;$sourceHash=(Get-FileHash -LiteralPath $source).Hash
$allowed=@('HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua')
$shadow=Join-Path $out ('certification-'+[Guid]::NewGuid().ToString('N'));New-Item -ItemType Directory -Path $shadow|Out-Null
$loadBefore=Join-Path $shadow 'before.dll';$loadAfter=Join-Path $shadow 'after.dll';[IO.File]::Copy($target,$loadBefore,$false);[IO.File]::Copy($source,$loadAfter,$false)
if((Get-FileHash -LiteralPath $loadBefore).Hash -ne $beforeHash -or (Get-FileHash -LiteralPath $loadAfter).Hash -ne $sourceHash){throw 'Shadow copy differs'}
$ctx1=[System.Runtime.Loader.AssemblyLoadContext]::new('physical-core-before',$true);$ctx2=[System.Runtime.Loader.AssemblyLoadContext]::new('physical-core-after',$true)
$resolver={param($c,$n) $f=Join-Path $InstallationRoot ($n.Name+'.dll');if(Test-Path -LiteralPath $f){return $c.LoadFromAssemblyPath($f)};return $null}.GetNewClosure()
$ctx1.add_Resolving($resolver);$ctx2.add_Resolving($resolver)
function Methods($a){
 $rows=@{};foreach($t in $a.GetTypes()){
  foreach($m in @($t.GetMethods([Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly'))+@($t.GetConstructors([Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly'))){
   $b=$m.GetMethodBody();$key=$t.FullName+'|'+$m.ToString();$rows[$key]=if($b){[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($b.GetILAsByteArray()))+'|'+$b.MaxStackSize+'|'+$b.InitLocals+'|'+(@($b.LocalVariables|ForEach-Object {$_.LocalType.ToString()+' '+$_.IsPinned}) -join ';')+'|'+(@($b.ExceptionHandlingClauses|ForEach-Object {[string]$_.Flags+' '+$_.TryOffset+' '+$_.TryLength+' '+$_.HandlerOffset+' '+$_.HandlerLength+' '+$(if($_.Flags -eq 'Clause'){$_.CatchType.ToString()}elseif($_.Flags -eq 'Filter'){$_.FilterOffset}else{''})}) -join ';')}else{'none'}
  }
 };return $rows
}
function Constants($a){$rows=@{};foreach($t in $a.GetTypes()){foreach($f in $t.GetFields([Reflection.BindingFlags]'Public,NonPublic,Instance,Static,DeclaredOnly')){if($f.IsLiteral){$rows[$t.FullName+'|'+$f.Name]=[string]$f.GetRawConstantValue()}}};return $rows}
try{
 $a=$ctx1.LoadFromAssemblyPath($loadBefore);$b=$ctx2.LoadFromAssemblyPath($loadAfter)
 if($a.FullName -ne $b.FullName){throw 'Assembly identity differs'}
 $m1=Methods $a;$m2=Methods $b;$different=@($m1.Keys|Where-Object {$m1[$_] -ne $m2[$_]})
 if($m1.Count -ne $m2.Count -or $different.Count){throw "Unrelated code differs: before=$($m1.Count) after=$($m2.Count); $($different -join ', ')"}
 $c1=Constants $a;$c2=Constants $b;if($c1.Count -ne $c2.Count -or @($c1.Keys|Where-Object {$c1[$_] -ne $c2[$_]}).Count){throw 'Constants differ'}
 $names=$a.GetManifestResourceNames();if((@($names|Sort-Object) -join '|') -ne (@($b.GetManifestResourceNames()|Sort-Object) -join '|')){throw 'Resource set differs'}
 $changed=@();$resources=@()
 foreach($n in $names){$x=$a.GetManifestResourceStream($n);$y=$b.GetManifestResourceStream($n);$h1=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($x));$h2=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($y));$x.Dispose();$y.Dispose();if($h1 -ne $h2){$changed+=$n};$resources+=@{name=$n;beforeSha256=$h1;afterSha256=$h2}}
 if((@($changed|Sort-Object)-join '|') -ne (@($allowed|Sort-Object)-join '|')){throw 'Changes must be exactly the two approved physics resources'}
 foreach($n in $allowed){$reader=[IO.StreamReader]::new($b.GetManifestResourceStream($n));$text=$reader.ReadToEnd();$reader.Dispose();$expected=[IO.File]::ReadAllText((Join-Path $out ('formal\'+$n.Split('.')[-2]+'.lua')));if($text.Replace("`r`n","`n") -ne $expected.Replace("`r`n","`n")){throw 'Candidate resource differs from approved formal source'}}
 $record=@{status='CERTIFIED_PHYSICS_ONLY';mode='preflight';target=$target;source=$source;beforeSha256=$beforeHash;afterSha256=$sourceHash;identity=$a.FullName;methodsIdentical=$m1.Count;constantsIdentical=$c1.Count;resourceCount=$names.Count;changedResources=$changed;resources=$resources}
}finally{$a=$null;$b=$null;$ctx1.Unload();$ctx2.Unload();$ctx1=$null;$ctx2=$null;[GC]::Collect();[GC]::WaitForPendingFinalizers();[GC]::Collect()}
if($Apply){
 if((Get-FileHash -LiteralPath $target).Hash -ne $beforeHash -or (Get-FileHash -LiteralPath $source).Hash -ne $sourceHash){throw 'Files changed since certification'}
 $f=[IO.File]::Open($target,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);$f.Dispose()
 $backup=Join-Path $out ('before/'+[IO.Path]::GetRelativePath($root,$target));if(!(Test-Path -LiteralPath $backup)){New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($backup)) -Force|Out-Null;[IO.File]::Copy($target,$backup,$false)}
 if((Get-FileHash -LiteralPath $backup).Hash -ne $beforeHash){throw 'Backup differs from current baseline'}
 [IO.File]::Copy($source,$target,$true);if((Get-FileHash -LiteralPath $target).Hash -ne $sourceHash){throw 'Copy readback failed'};$record.mode='apply';$record.backup=$backup
}
$record|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $ReportPath -Encoding utf8
Write-Output "$($record.mode): $($m1.Count) methods and $($c1.Count) constants exact; $($names.Count) resources, only 2 physics changes."
