param([string[]] $ReportNames = @('package-inspection.json'))
$ErrorActionPreference = 'Stop'
$nativeWork = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../outputs/native-v14-20261104'))
$nativeRemoved = [Collections.Generic.List[object]]::new()
$nativeCleanupPath = Join-Path $nativeWork 'import-library-cleanup.json'
if (Test-Path -LiteralPath $nativeCleanupPath) {
    $previous = Get-Content -LiteralPath $nativeCleanupPath -Raw | ConvertFrom-Json
    foreach ($row in $previous.removed) { $nativeRemoved.Add($row) }
}
foreach ($name in $ReportNames) {
    $reportPath = [IO.Path]::GetFullPath((Join-Path $nativeWork $name))
    if (!$reportPath.StartsWith($nativeWork + [IO.Path]::DirectorySeparatorChar)) { throw 'Report outside work folder' }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if ($report.status -ne 'PASS' -or $report.gameDeployed -ne $false -or $report.dailyLibraryModified -ne $false) { throw 'Unverified import report' }
    $sandbox = [IO.Path]::GetFullPath($report.sandbox)
    if ([IO.Path]::GetDirectoryName($sandbox) -ne $nativeWork -or [IO.Path]::GetFileName($sandbox) -notlike 'import-audit-*') { throw 'Unexpected import sandbox' }
    $libraries = [Collections.Generic.HashSet[string]]::new()
    foreach ($package in $report.packages) {
        foreach ($resource in $package.verifiedPatchFiles) {
            foreach ($relative in $resource.imported) {
                $parts = $relative -split '[\\/]'
                if ($parts.Count -lt 4 -or $parts[0] -notmatch '^\d+$' -or $parts[1] -ne 'library') { throw 'Unexpected imported path' }
                $library = [IO.Path]::GetFullPath((Join-Path $sandbox ($parts[0] + '/library')))
                $path = [IO.Path]::GetFullPath((Join-Path $sandbox $relative))
                if (!$library.StartsWith($sandbox + [IO.Path]::DirectorySeparatorChar) -or !$path.StartsWith($library + [IO.Path]::DirectorySeparatorChar)) { throw 'Path leaves sandbox' }
                if (Test-Path -LiteralPath $library) {
                    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $resource.sha256) { throw 'Imported resource changed' }
                    [void] $libraries.Add($library)
                }
            }
        }
    }
    foreach ($library in $libraries) {
        $items = @(Get-ChildItem -LiteralPath $library -File -Recurse)
        $bytes = ($items | Measure-Object -Property Length -Sum).Sum
        # Only disposable libraries named in a successful isolated import report.
        if ([IO.Path]::GetFileName($library) -ne 'library' -or !$library.StartsWith($sandbox + [IO.Path]::DirectorySeparatorChar)) { throw 'Unsafe deletion target' }
        Remove-Item -LiteralPath $library -Recurse -Force
        $nativeRemoved.Add([pscustomobject]@{ path=$library; bytes=$bytes; files=$items.Count; report=$name })
    }
}
$result = [pscustomobject]@{ status='PASS'; removed=@($nativeRemoved.ToArray()); bytes=($nativeRemoved | Measure-Object -Property bytes -Sum).Sum; retained='Import plans, logs, reports, delivered packages and version backups' }
$result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $nativeCleanupPath -Encoding utf8
$result | Select-Object status,bytes

