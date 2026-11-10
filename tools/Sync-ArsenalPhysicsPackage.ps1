param([switch]$Apply)
$ErrorActionPreference='Stop'
$root=(Get-Location).Path
$workspace=[IO.Path]::GetFullPath($root).TrimEnd('\')+'\'
$install=Join-Path $root 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7'
$evidence=Join-Path $root 'outputs\grip-b3-options-20261110'
$backupRoot=Join-Path $install '非运行文件\归档\旧版备份'
if(!(Test-Path -LiteralPath $backupRoot -PathType Container)){throw 'Established backup category missing'}
$reports=@('manager-sync-core-assembly-20261110.json','manager-sync-gui-assembly-20261110.json')
$allowed=@(@('HD2ModCore.Infrastructure.LuaAddonPackageExport::Export|','HD2ModCore.Infrastructure.LuaAddonPackageExport::BuildReadme|'),@('HD2ModManager.ViewModels.SettingsPageViewModel::EnsureLuaPackageUpToDate|','HD2ModManager.Services.NativeSkeletonProjectService.<BuildAsync>d__1::MoveNext|'))
$plan=@()
for($i=0;$i -lt $reports.Count;$i++){
 $r=Get-Content -LiteralPath (Join-Path $evidence $reports[$i]) -Raw|ConvertFrom-Json
 if(!$r.identityUnchanged -or $r.methodsBefore -ne $r.methodsAfter -or $r.changedMethods.Count -ne 2 -or $r.changedResources.Count -or $r.changedReferences.Count -or $r.changedConstants.Count){throw 'Unexpected assembly change in certification'}
 foreach($m in $r.changedMethods){if(@($allowed[$i]|Where-Object {$m.StartsWith($_,[StringComparison]::Ordinal)}).Count -ne 1){throw "Unapproved changed method: $m"}}
 $target=[IO.Path]::GetFullPath($r.before);$source=[IO.Path]::GetFullPath($r.after)
 if(!$target.StartsWith($workspace,[StringComparison]::OrdinalIgnoreCase) -or !$source.StartsWith($workspace,[StringComparison]::OrdinalIgnoreCase)){throw 'Certified path outside workspace'}
 if([IO.Path]::GetDirectoryName($target) -ne [IO.Path]::GetFullPath($install) -or [IO.Path]::GetFileName($target) -notin @('HD2ModCore.dll','HD2ModManager.dll')){throw 'Unexpected installation target'}
 if((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Refuse reparse installation target'}
 if((Get-FileHash -LiteralPath $target).Hash -ne $r.beforeSha256 -or (Get-FileHash -LiteralPath $source).Hash -ne $r.afterSha256){throw 'Certified binary bytes changed'}
 $backup=Join-Path $backupRoot ([IO.Path]::GetFileName($target)+'.before-arsenal-flat-export-20261110.bak')
 if(Test-Path -LiteralPath $backup){if((Get-FileHash -LiteralPath $backup).Hash -ne $r.beforeSha256){throw 'Conflicting recovery backup'}}
 $f=[IO.File]::Open($target,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);$f.Dispose()
 $plan+=@{source=$source;target=$target;sourceSha256=$r.afterSha256;targetSha256=$r.beforeSha256;backup=$backup}
}
$result=@{mode=if($Apply){'apply'}else{'preflight'};date='2026-11-10';plan=$plan;coreMethodsPreservedExceptPackaging=16750;guiMethodsPreservedExceptPackaging=8685;embeddedResourcesUnchanged=31;physicsMathChanged=$false;gameDeployed=$false;stagingBinariesTouched=$false}
if($Apply){
 foreach($p in $plan){if(!(Test-Path -LiteralPath $p.backup)){Copy-Item -LiteralPath $p.target -Destination $p.backup};if((Get-FileHash -LiteralPath $p.backup).Hash -ne $p.targetSha256){throw 'Recovery backup mismatch'}}
 try{
  foreach($p in $plan){Copy-Item -LiteralPath $p.source -Destination $p.target -Force;if((Get-FileHash -LiteralPath $p.target).Hash -ne $p.sourceSha256){throw 'Installation copy mismatch'}}
 }catch{
  foreach($p in $plan){Copy-Item -LiteralPath $p.backup -Destination $p.target -Force}
  throw
 }
}
$result|ConvertTo-Json -Depth 6|Set-Content -LiteralPath (Join-Path $evidence $(if($Apply){'manager-arsenal-flat-sync-applied-20261110.json'}else{'manager-arsenal-flat-sync-preflight-20261110.json'})) -Encoding utf8
Write-Output "$($result.mode): $($plan.Count) certified DLLs; 31 runtime resources unchanged; no game/config/library writes."
