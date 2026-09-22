[CmdletBinding()]
param(
  [ValidateRange(2, 3600)] [int]$PollSeconds = 10,
  [switch]$Once
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$ProgressPath = Join-Path $Root 'exports\export_progress.json'
$LogPath = Join-Path $Root 'exports\export_queue.log'
$ErrorLogPath = Join-Path $Root 'exports\export_queue.err.log'
$AuditLogPath = Join-Path $Root 'exports\consolidation_audit_parallel.log'
$AuditErrorLogPath = Join-Path $Root 'exports\consolidation_audit_parallel.err.log'
$AuditResultPath = Join-Path $Root 'exports\hubbi_volkswagen_consolidation_audit.json'
$ConsolidatedLogPath = Join-Path $Root 'exports\consolidated_export.log'
$ConsolidatedErrorLogPath = Join-Path $Root 'exports\consolidated_export.err.log'
$ConsolidatedCsvPath = Join-Path $Root 'exports\hubbi_volkswagen_full.csv'
$ConflictReportPath = Join-Path $Root 'exports\hubbi_volkswagen_consolidation_conflicts.json'

function Format-Bytes([long]$Bytes) {
  if ($Bytes -ge 1GB) { return ('{0:N2} GiB' -f ($Bytes / 1GB)) }
  if ($Bytes -ge 1MB) { return ('{0:N2} MiB' -f ($Bytes / 1MB)) }
  return ('{0} B' -f $Bytes)
}

function Get-Elapsed($StartedAt) {
  if (-not $StartedAt) { return '-' }
  try { return ('{0:dd\.hh\:mm\:ss}' -f ((Get-Date).ToUniversalTime() - ([datetimeoffset]::Parse($StartedAt)).UtcDateTime)) }
  catch { return '-' }
}

while ($true) {
  Clear-Host
  Write-Host 'Hubbi VW BR - export queue monitor' -ForegroundColor Cyan
  Write-Host ('Updated: {0} | Ctrl+C stops only this monitor' -f (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')) -ForegroundColor DarkGray
  Write-Host ''

  if (Test-Path -LiteralPath $ProgressPath) {
    try {
      $progress = Get-Content -LiteralPath $ProgressPath -Raw | ConvertFrom-Json
      $models = @($progress.models.psobject.Properties | ForEach-Object {
        $item = $_.Value
        $size = '-'
        if ($item.csv_path -and (Test-Path -LiteralPath $item.csv_path)) { $size = Format-Bytes ((Get-Item -LiteralPath $item.csv_path).Length) }
        [pscustomobject]@{ Model=$_.Name; Status=$item.status; Elapsed=(Get-Elapsed $item.started_at); Rows=if($item.row_count){$item.row_count}else{'-'}; Csv=$size; Error=$item.error }
      })
      $summary = $models | Group-Object Status -NoElement | ForEach-Object { '{0}={1}' -f $_.Name,$_.Count }
      Write-Host ('Queue: ' + ($summary -join ' | ')) -ForegroundColor Green
      $models | Format-Table Model,Status,Elapsed,Rows,Csv,Error -AutoSize
    } catch { Write-Host ('Cannot read progress: {0}' -f $_.Exception.Message) -ForegroundColor Red }
  } else { Write-Host ('Queue state is not present: {0}' -f $ProgressPath) -ForegroundColor Yellow }

  Write-Host ''
  Write-Host 'Consolidation audit:' -ForegroundColor Cyan
  if (Test-Path -LiteralPath $AuditResultPath) {
    $auditResult = Get-Content -LiteralPath $AuditResultPath -Raw | ConvertFrom-Json
    Write-Host ('COMPLETED | specs={0} groups={1} occurrences={2} unique_parts={3}' -f $auditResult.specs,$auditResult.groups,$auditResult.occurrences,$auditResult.unique_brand_search_ref) -ForegroundColor Green
  } elseif (Test-Path -LiteralPath $AuditLogPath) {
    $auditProgress = Get-Content -LiteralPath $AuditLogPath | Where-Object { $_ -match '^AUDIT_PROGRESS ' } | Select-Object -Last 1
    if ($auditProgress -match 'specs=(\d+)/(\d+) groups=(\d+) occurrences=(\d+)') {
      $percent = [math]::Round((100 * [int]$Matches[1] / [int]$Matches[2]), 1)
      Write-Host ('RUNNING | specs={0}/{1} ({2}%) groups={3} occurrences={4}' -f $Matches[1],$Matches[2],$percent,$Matches[3],$Matches[4]) -ForegroundColor Yellow
    } else { Write-Host 'RUNNING | waiting for first progress checkpoint...' -ForegroundColor Yellow }
  } else { Write-Host 'NOT STARTED' -ForegroundColor DarkGray }

  Write-Host ''
  Write-Host 'Final consolidated export:' -ForegroundColor Cyan
  if (Test-Path -LiteralPath $ConsolidatedCsvPath) {
    $csvSize = Format-Bytes ((Get-Item -LiteralPath $ConsolidatedCsvPath).Length)
    $conflictSize = if (Test-Path -LiteralPath $ConflictReportPath) { Format-Bytes ((Get-Item -LiteralPath $ConflictReportPath).Length) } else { '-' }
    Write-Host ('COMPLETED | CSV={0} | conflict report={1}' -f $csvSize,$conflictSize) -ForegroundColor Green
  } elseif (Test-Path -LiteralPath $ConsolidatedLogPath) {
    $exportProgress = Get-Content -LiteralPath $ConsolidatedLogPath | Where-Object { $_ -match '^CONSOLIDATE_PROGRESS ' } | Select-Object -Last 1
    if ($exportProgress -match 'specs=(\d+)/(\d+) groups=(\d+) occurrences=(\d+)') {
      $percent = [math]::Round((100 * [int]$Matches[1] / [int]$Matches[2]), 1)
      Write-Host ('RUNNING | specs={0}/{1} ({2}%) groups={3} occurrences={4}' -f $Matches[1],$Matches[2],$percent,$Matches[3],$Matches[4]) -ForegroundColor Yellow
    } else { Write-Host 'RUNNING | waiting for first progress checkpoint...' -ForegroundColor Yellow }
  } else { Write-Host 'NOT STARTED' -ForegroundColor DarkGray }

  $drive = [System.IO.DriveInfo]::new($Root.Substring(0,1))
  $total = (Get-ChildItem (Join-Path $Root 'exports') -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
  Write-Host ''
  Write-Host ('Disk free: {0} | exports/: {1}' -f (Format-Bytes $drive.AvailableFreeSpace),(Format-Bytes $total)) -ForegroundColor Yellow

  $python = @(Get-Process python -ErrorAction SilentlyContinue | ForEach-Object { [pscustomobject]@{PID=$_.Id;CPU_s=[math]::Round($_.CPU,1);RAM_MiB=[math]::Round($_.WorkingSet64/1MB,1);Started=$_.StartTime.ToString('HH:mm:ss');Path=$_.Path} })
  Write-Host ''
  Write-Host 'Python processes:' -ForegroundColor Cyan
  if ($python.Count) { $python | Format-Table -AutoSize } else { Write-Host 'No active Python processes.' -ForegroundColor Yellow }

  Write-Host ''
  Write-Host 'Last exporter log lines:' -ForegroundColor Cyan
  if (Test-Path -LiteralPath $LogPath) { Get-Content -LiteralPath $LogPath -Tail 8 } else { Write-Host 'Log not created yet.' -ForegroundColor DarkGray }
  if ((Test-Path -LiteralPath $ErrorLogPath) -and (Get-Item -LiteralPath $ErrorLogPath).Length -gt 0) {
    Write-Host 'Last error lines:' -ForegroundColor Red
    Get-Content -LiteralPath $ErrorLogPath -Tail 8
  }
  Write-Host ''
  Write-Host 'Last consolidation audit log lines:' -ForegroundColor Cyan
  if (Test-Path -LiteralPath $AuditLogPath) { Get-Content -LiteralPath $AuditLogPath -Tail 8 } else { Write-Host 'Audit log not created yet.' -ForegroundColor DarkGray }
  if ((Test-Path -LiteralPath $AuditErrorLogPath) -and (Get-Item -LiteralPath $AuditErrorLogPath).Length -gt 0) {
    Write-Host 'Last audit error lines:' -ForegroundColor Red
    Get-Content -LiteralPath $AuditErrorLogPath -Tail 8
  }
  Write-Host ''
  Write-Host 'Last final-export log lines:' -ForegroundColor Cyan
  if (Test-Path -LiteralPath $ConsolidatedLogPath) { Get-Content -LiteralPath $ConsolidatedLogPath -Tail 8 } else { Write-Host 'Final-export log not created yet.' -ForegroundColor DarkGray }
  if ((Test-Path -LiteralPath $ConsolidatedErrorLogPath) -and (Get-Item -LiteralPath $ConsolidatedErrorLogPath).Length -gt 0) {
    Write-Host 'Last final-export error lines:' -ForegroundColor Red
    Get-Content -LiteralPath $ConsolidatedErrorLogPath -Tail 8
  }
  if ($Once) { break }
  Start-Sleep -Seconds $PollSeconds
}
