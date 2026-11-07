$ErrorActionPreference='Stop'
$root=(Get-Location).Path
$auditPath=Join-Path $root 'outputs\vrd-analysis-20261107\accepted-code-equivalence.json'
$audit=Get-Content -LiteralPath $auditPath -Raw|ConvertFrom-Json
if($audit.status -ne 'PASS' -or $audit.functionalSourceChange){throw 'Missing accepted-code equivalence check'}
$targets=@('outputs\native-v34-b23-integrated-20261105\manager-1.0.7','outputs\single-hd2-fix-20261106\manager')
$plan=@()
foreach($entry in $audit.binaries){
 foreach($dir in $targets){
  foreach($suffix in '.dll','.pdb'){
   $name=[IO.Path]::ChangeExtension($entry.name,$suffix)
   $src=Join-Path ([IO.Path]::GetDirectoryName($entry.source)) $name
   $dst=Join-Path (Join-Path $root $dir) $name
   if(!(Test-Path -LiteralPath $src)){throw "Missing product $src"}
   $new=(Get-FileHash -LiteralPath $src).Hash;$old=if(Test-Path -LiteralPath $dst){(Get-FileHash -LiteralPath $dst).Hash}else{$null}
   if($suffix -eq '.dll' -and $new -ne $entry.afterSha256){throw 'Compiled binary changed after equivalence verification'}
   $plan+=@{source=$src;target=$dst;sourceSha256=$new;previousSha256=$old;changed=($new -ne $old)}
  }
 }
}
# All write targets are preflighted before any backup/copy; never force-close the manager.
foreach($p in $plan|Where-Object {$_.changed}){$f=[IO.File]::Open($p.target,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);$f.Dispose()}
foreach($p in $plan|Where-Object {$_.changed}){
 $backup=$p.target+'.before-accepted-vrd-code-sync.bak'
 if(!(Test-Path -LiteralPath $backup)){Copy-Item -LiteralPath $p.target -Destination $backup}
 Copy-Item -LiteralPath $p.source -Destination $p.target -Force
}
foreach($p in $plan){if((Get-FileHash -LiteralPath $p.target).Hash -ne $p.sourceSha256){throw "Sync mismatch $($p.target)"}}
@{status='PASS';appliedAt=[DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('o');files=$plan;changedFiles=@($plan|Where-Object {$_.changed}).Count;preservedAcceptedBehavior=$true}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath 'outputs\vrd-analysis-20261107\accepted-code-sync.json' -Encoding utf8
Write-Output "Verified $($plan.Count) DLL/PDB targets; updated $(@($plan|Where-Object {$_.changed}).Count) files."
