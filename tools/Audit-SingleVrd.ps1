param([string]$Patch='outputs\vrd-analysis-20261107\e2e-test01-single\test01\9ba626afa44a3aa3.patch_0', [string]$Report='outputs\vrd-analysis-20261107\single-fixed-model-audit.json')
$ErrorActionPreference='Stop'
$d=Join-Path (Get-Location) 'HD2ModCli\bin\Release\net10.0'
foreach($n in 'K4os.Compression.LZ4.dll','HD2ModAdaptation.dll','HD2SourceModel.dll','HD2SourceMigration.dll') { [Reflection.Assembly]::LoadFrom((Join-Path $d $n))|Out-Null }
$sm=[HD2SourceModel.SourceModelReader]::Read([IO.File]::ReadAllBytes((Join-Path (Get-Location) 'outputs\vrd-analysis-20261107\vpk-extract\test01_survivor_namvet.mdl')))
$physics=@($sm.Bones | Where-Object {$null -ne $_.Jiggle -or $null -ne $_.QuatInterp})
$names=@{}; foreach($b in $sm.Bones){$names[[HD2SourceMigration.Hd2NameHash]::Of($b.DisplayName).ToString()]=$b.DisplayName}
foreach($n in 'head','hips','chest','l_elbow','r_elbow','l_hand','r_hand'){$names[[HD2SourceMigration.Hd2NameHash]::Of($n).ToString()]=$n}
$entries=[HD2ModAdaptation.PatchReconstruction.PatchTocScanner]::new().ScanEntriesAsync((Join-Path (Get-Location) $Patch)).GetAwaiter().GetResult()
$r=[HD2ModAdaptation.PatchReconstruction.UnitMesh.PatchUnitMeshReader]::new(); $used=@{}; $units=@();$parents=@()
foreach($e in $entries){
 if($e.AssetKey.TypeId -ne [HD2ModAdaptation.PatchReconstruction.UnitMesh.PatchUnitMeshReader]::UnitTypeId){continue}
 $m=$r.ReadAsync($e,$entries).GetAwaiter().GetResult().Model; $h=$m.TransformNameHashes
 if($h.Count -ne 139){throw "Unexpected node count $($h.Count)"}
 $unitParents=@()
 foreach($b in $physics){
  $hash=[HD2SourceMigration.Hd2NameHash]::Of($b.DisplayName);$index=[Array]::IndexOf([uint[]]$h,$hash)
  if($index -lt 0){throw "Missing $($b.DisplayName)"}
  $parent=$m.TransformInfo.Entries[$index].ParentIndex; $parentName=$names[$h[$parent].ToString()]
  $local=$m.TransformInfo.LocalTransforms[$index]; $pw=$m.TransformInfo.Matrices[$parent].Values; $bw=$m.TransformInfo.Matrices[$index].Values
  for($row=0;$row -lt 3;$row++){
   for($col=0;$col -lt 3;$col++){
    $value=0.0; for($k=0;$k -lt 3;$k++){$value+=$local.Rotation[$row*3+$k]*$local.Scale[$k]*$pw[$k*4+$col]}
    if([Math]::Abs($value-$bw[$row*4+$col]) -gt 0.0001){throw "Physics world rotation mismatch $($b.DisplayName)"}
   }
   $value=$pw[12+$row];for($k=0;$k -lt 3;$k++){$value+=$local.Position[$k]*$pw[$k*4+$row]}
   if([Math]::Abs($value-$bw[12+$row]) -gt 0.0001){throw "Physics world position mismatch $($b.DisplayName)"}
  }
  $original=$sm.Bones[$b.ParentIndex]
  if($original.Jiggle -or $original.QuatInterp){$expected=$original.DisplayName}
  elseif($original.DisplayName -like '*Head1'){$expected='head'}
  elseif($original.DisplayName -like '*Pelvis'){$expected='hips'}
  elseif($original.DisplayName -like '*L_Forearm'){$expected='l_elbow'}
  elseif($original.DisplayName -like '*R_Forearm'){$expected='r_elbow'}
  else{$expected='chest'}
  if($parentName -ne $expected){throw "Wrong parent $($b.DisplayName): $parentName expected $expected"}
  $unitParents+=@{bone=$b.DisplayName;parent=$parentName}
 }
 foreach($bi in $m.BoneInfos){foreach($idx in $bi.RealIndices){$name=$names[$h[[int]$idx].ToString()];if($name){$used[$name]=$true}}}
 $units+=@{id=$e.AssetKey.FileId.ToString('x16');nodes=$h.Count}
 if($parents.Count -eq 0){$parents=$unitParents}
}
foreach($b in $physics){if(!$used.ContainsKey($b.DisplayName)){throw "Missing weight palette membership $($b.DisplayName)"}}
$reportData=@{status='PASS_STRUCTURAL_NOT_GAME_ACCEPTANCE';units=$units;physicsBones=$physics.Count;weightedPhysicsBones=$physics.Count;parents=$parents;localWorldTolerance=0.0001}
$reportData|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $Report -Encoding utf8
Write-Output "PASS: $($units.Count) units, $($physics.Count)/$($physics.Count) physics names in weights, exact source parent chains and local/world FK"
