[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$target=Join-Path $repo 'outputs\native-v34-b23-integrated-20261105\manager-1.0.7'
$stage=Join-Path $repo 'outputs\single-hd2-fix-20261106\manager'
$preset='anim_batch_mod\presets\native-v15\grip-fixes-1.0.11.json'
$sourcePreset=Join-Path $repo ('tools\native-python\'+$preset)
$diagnosticSources=@('native_config.py')
$compiled=Join-Path $repo 'HD2ModCore\bin\Release\net8.0'
foreach($dir in @($target,$stage,$compiled)) {if(!(Test-Path -LiteralPath $dir -PathType Container)){throw "Missing existing directory: $dir"}}
$destinations=@((Join-Path $target 'HD2ModCore.dll'),(Join-Path $target 'HD2ModCore.pdb'),(Join-Path $target $preset),(Join-Path $target 'anim_batch_mod\build-info.json'),(Join-Path $stage 'HD2ModCore.dll'),(Join-Path $stage 'HD2ModCore.pdb'))
foreach($base in @($target,$stage)) {
 $destinations+=@((Join-Path $base $preset),(Join-Path $base 'anim_batch_mod\build-info.json'))
}
$destinations+=Join-Path $repo 'tools\native-python\anim_batch_mod\build-info.json'
foreach($base in @($target,$stage)){foreach($name in $diagnosticSources){$destinations+=Join-Path $base ('anim_batch_mod\'+$name)}}
$destinations=@($destinations|Select-Object -Unique)
# Preflight all existing destinations before backups/writes. Do not kill the GUI.
foreach($file in $destinations) {
 if(Test-Path -LiteralPath $file){$handle=[IO.File]::Open($file,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None);$handle.Dispose()}
}
$protected=@((Join-Path $target 'settings.json'),(Join-Path $target 'test-library\library.json'),(Join-Path $target 'test-library\profiles.json'))
$library=Join-Path $target 'test-library'
foreach($folder in @('[骨骼挂点修正]test01','[原比例模型]test01','[原比例混合动画](test01)')) {
 $protected+=@(Get-ChildItem -LiteralPath (Join-Path $library $folder) -Recurse -File | ForEach-Object FullName)
}
$before=@{};foreach($file in $protected){if(Test-Path -LiteralPath $file){$before[$file]=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash}}
$changes=@()
foreach($base in @($target,$stage)) {
 foreach($name in @('HD2ModCore.dll','HD2ModCore.pdb')) {
  $dest=Join-Path $base $name;$source=Join-Path $compiled $name
  if((Get-FileHash -LiteralPath $dest).Hash -ne (Get-FileHash -LiteralPath $source).Hash) {
   $backup=$dest+'.test01-1.0.17.bak';if(!(Test-Path -LiteralPath $backup)){Copy-Item -LiteralPath $dest -Destination $backup}
   Copy-Item -LiteralPath $source -Destination $dest -Force;$changes+=$dest
  }
 }
 foreach($name in $diagnosticSources) {
  $source=Join-Path $repo ('tools\native-python\anim_batch_mod\'+$name)
  $dest=Join-Path $base ('anim_batch_mod\'+$name)
  if((Get-FileHash -LiteralPath $dest).Hash -ne (Get-FileHash -LiteralPath $source).Hash) {
   $backup=$dest+'.test01-1.0.17.bak';if(!(Test-Path -LiteralPath $backup)){Copy-Item -LiteralPath $dest -Destination $backup}
   Copy-Item -LiteralPath $source -Destination $dest -Force;$changes+=$dest
  }
 }
 $dest=Join-Path $base $preset
 if((Get-FileHash -LiteralPath $dest).Hash -ne (Get-FileHash -LiteralPath $sourcePreset).Hash) {
  $backup=$dest+'.test01-1.0.17.bak';if(!(Test-Path -LiteralPath $backup)){Copy-Item -LiteralPath $dest -Destination $backup}
  Copy-Item -LiteralPath $sourcePreset -Destination $dest -Force;$changes+=$dest
 }
}
# Update only Lua metadata and preset digest; keep current single-rig pipeline fields.
foreach($base in @($target,$stage,(Join-Path $repo 'tools\native-python'))) {
 $file=Join-Path $base 'anim_batch_mod\build-info.json';$info=Get-Content -LiteralPath $file -Raw -Encoding utf8|ConvertFrom-Json
 $originalSingle=$info.singleSkeletonPipelineVersion
 if($base -eq $target){$backup=$file+'.test01-1.0.17.bak';if(!(Test-Path -LiteralPath $backup)){Copy-Item -LiteralPath $file -Destination $backup}}
 $info.luaVersion='1.0.17'
 $info|Add-Member -NotePropertyName physicsRuntimeVersion -NotePropertyValue '2.2.1' -Force
 $info|Add-Member -NotePropertyName gripFixRevision -NotePropertyValue 'bounded-runtime-logs-20261107' -Force
 foreach($row in $info.presetFiles) {
  if($row.name -eq 'presets/native-v15/grip-fixes-1.0.11.json'){$row.sha256=(Get-FileHash -LiteralPath (Join-Path $base ('anim_batch_mod\'+$row.name))).Hash}
 }
 foreach($row in $info.files){if($diagnosticSources -contains $row.name){$row.sha256=(Get-FileHash -LiteralPath (Join-Path $base ('anim_batch_mod\'+$row.name))).Hash}}
 $text=$info|ConvertTo-Json -Depth 12;[IO.File]::WriteAllText($file,$text,[Text.UTF8Encoding]::new($false))
 if((Get-Content -LiteralPath $file -Raw|ConvertFrom-Json).singleSkeletonPipelineVersion -ne $originalSingle){throw 'Single-rig metadata changed'}
 $changes+=$file
}
foreach($file in $before.Keys){if((Get-FileHash -LiteralPath $file).Hash -ne $before[$file]){throw "Protected file changed: $file"}}
if((Get-FileHash -LiteralPath (Join-Path $target 'HD2ModCore.dll')).Hash -ne (Get-FileHash -LiteralPath (Join-Path $compiled 'HD2ModCore.dll')).Hash){throw 'Installed Core differs from compiled Core'}
$report=[ordered]@{status='PASS';luaVersion='1.0.17';target=$target;changedFiles=$changes;protectedFileCount=$before.Count;protectedFilesUnchanged=$true;installedCoreSha256=(Get-FileHash -LiteralPath (Join-Path $target 'HD2ModCore.dll')).Hash;newReleaseDirectories=$false;activeLibraryChanged=$false;gameDeployed=$false;modelRebaked=$false;animationRebaked=$false}
[IO.File]::WriteAllText((Join-Path $target '日志缩减-1.0.17-管理器同步.json'),($report|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false));$report|ConvertTo-Json -Depth 8
