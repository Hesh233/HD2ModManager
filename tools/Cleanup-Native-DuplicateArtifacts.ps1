[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$outputRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../outputs'))
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $outputRoot 'native-manual-20261103'))
$workRoot = [IO.Path]::GetFullPath((Join-Path $outputRoot 'native-v13-20261104'))
$before = (Get-PSDrive -Name I).Free
$all = @(Get-ChildItem -LiteralPath $outputRoot -Recurse -File | Where-Object Length -gt 200MB)
$retained = @($all | Where-Object {
    $_.FullName.StartsWith($releaseRoot + '\') -or
    ($_.FullName -match '\\native-v(?:4|5|6|8|10|11)-\d{8}\\project\\animations\\runtime\\')
})
$candidates = @($all | Where-Object {
    -not $_.FullName.StartsWith($releaseRoot + '\') -and
    -not $_.FullName.StartsWith($workRoot + '\') -and
    ($_.FullName -match '\\native-(?:v\d+|fix|regression)-\d{8}\\test01-配套动画\.zip$' -or
     $_.FullName -match '\\native-v\d+-\d{8}\\import-(?:audit-[^\\]+\\library|test-library)\\' -or
     $_.FullName -match '\\native-v(?:7|9|12)-\d{8}\\project\\animations\\runtime\\')
})
$hashes = @{}
function Read-Digest([string]$path) {
    if (-not $hashes.ContainsKey($path)) { $hashes[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }
    return $hashes[$path]
}
$removed = [Collections.Generic.List[object]]::new()
$skipped = [Collections.Generic.List[string]]::new()
foreach ($candidate in $candidates) {
    $path = [IO.Path]::GetFullPath($candidate.FullName)
    if (-not $path.StartsWith($outputRoot + '\') -or $path.StartsWith($releaseRoot + '\') -or $path.StartsWith($workRoot + '\')) { throw 'Cleanup boundary violation' }
    $matches = @($retained | Where-Object { $_.Length -eq $candidate.Length -and $_.FullName -ne $path })
    $keeper = $null
    foreach ($other in $matches) {
        if ((Read-Digest $path) -eq (Read-Digest $other.FullName)) { $keeper = $other; break }
    }
    if ($null -eq $keeper) { $skipped.Add($path); continue }
    # Recheck both files immediately before removing this generated duplicate.
    if (-not (Test-Path -LiteralPath $keeper.FullName) -or (Get-Item -LiteralPath $path).Length -ne $keeper.Length) { throw 'Duplicate changed during cleanup' }
    $record = [ordered]@{ removed=$path; retained=$keeper.FullName; bytes=$candidate.Length; sha256=(Read-Digest $path) }
    Remove-Item -LiteralPath $path -Force
    $removed.Add($record)
    [ordered]@{ status='IN_PROGRESS'; freeBefore=$before; removed=$removed; skipped=$skipped } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $workRoot 'duplicate-cleanup.json') -Encoding utf8
    Write-Output ('Removed verified duplicate: ' + $candidate.FullName)
}
$after = (Get-PSDrive -Name I).Free
$removedBytes = [long]0
foreach ($entry in $removed) { $removedBytes += $entry['bytes'] }
[ordered]@{ status='PASS'; freeBefore=$before; freeAfter=$after; removedBytes=$removedBytes; removed=$removed; skipped=$skipped; retainedDeliveryAndVersionBackups=$true } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $workRoot 'duplicate-cleanup.json') -Encoding utf8
Write-Output ('Free space: ' + [math]::Round($after/1GB,2) + ' GiB')
