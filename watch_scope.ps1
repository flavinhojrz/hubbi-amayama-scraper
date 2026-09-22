param(
    [string]$RunId = "",
    [string]$Manufacturer = "VOLKSWAGEN",
    [string]$VehicleModel = "",
    [string]$Market = "",
    [string]$Scope = "",
    [string]$Label = "",
    [int]$PollSeconds = 15
)

$Python = ".\.venv\Scripts\python.exe"
$MonitorStartedAt = Get-Date

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python do projeto nao encontrado em $Python. Rode a partir da raiz do repo."
}

if (-not $RunId) {
    if (-not $Scope) {
        if (-not $VehicleModel -or -not $Market) {
            throw "Informe -RunId ou -VehicleModel e -Market. Ex: .\watch_scope.ps1 -VehicleModel GOLF-VARIANT -Market GOV-BR"
        }
        $Scope = "AMAYAMA:$Manufacturer`:$VehicleModel`:$Market"
    }

    $findRunCode = @"
import sqlite3, json, sys
scope = "$Scope"
conn = sqlite3.connect("amayama.db")
conn.row_factory = sqlite3.Row
rows = list(conn.execute('''
select run_id, scope, started_at, resumed_at, completed_at
from collection_run
where scope=?
order by
  case when completed_at is null then 0 else 1 end,
  coalesce(resumed_at, started_at, '') desc,
  rowid desc
limit 1
''', (scope,)))
if not rows:
    print(json.dumps({"error": "scope_not_found", "scope": scope}))
    sys.exit(2)
print(json.dumps(dict(rows[0]), ensure_ascii=False))
"@

    $runJson = $findRunCode | & $Python -
    $runInfo = $runJson | ConvertFrom-Json
    if ($runInfo.error) {
        throw "Scope nao encontrado no banco: $($runInfo.scope)"
    }
    $RunId = $runInfo.run_id
    $Scope = $runInfo.scope
}

if (-not $Label) {
    if ($VehicleModel -and $Market) {
        $Label = "$VehicleModel / $Market"
    } elseif ($Scope) {
        $Label = $Scope
    } else {
        $Label = $RunId
    }
}

$baseCode = @"
import sqlite3
run_id = "$RunId"
conn = sqlite3.connect("amayama.db")
row = conn.execute(
    "select count(*) from checkpoint_entry where run_id=? and status='ACCEPTED'",
    (run_id,),
).fetchone()
print(row[0] or 0)
"@
$BaseGroups = [int]($baseCode | & $Python -)
Write-Host "Monitor: $Label"
Write-Host "RunId:   $RunId"
if ($Scope) { Write-Host "Scope:   $Scope" }
Write-Host "Baseline: $BaseGroups grupos ACCEPTED (calculado agora)"
Start-Sleep -Seconds 2

while ($true) {
    Clear-Host
    $now = Get-Date
    Write-Host "STATUS $Label - $($now.ToString('yyyy-MM-dd HH:mm:ss'))"
    Write-Host ""

    $code = @"
import sqlite3, json, ast
from datetime import datetime, timezone
run_id = "$RunId"
base = $BaseGroups

conn = sqlite3.connect("amayama.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

run = cur.execute(
    "select run_id, scope, started_at, resumed_at, completed_at from collection_run where run_id=?",
    (run_id,),
).fetchone()

latest_manifests = list(cur.execute('''
with latest as (
  select spec_key, max(id) id
  from spec_group_manifest
  where run_id=?
  group by spec_key
)
select m.spec_key, m.categories_json, m.manifest_complete
from latest l
join spec_group_manifest m on m.id=l.id
''', (run_id,)))

specs_total = len(latest_manifests)
manifests_complete = sum(1 for r in latest_manifests if r["manifest_complete"] == 1)
manifests_incomplete = specs_total - manifests_complete

categories_expected_current = 0
max_categories_per_spec = 0
for r in latest_manifests:
    try:
        cats = json.loads(r["categories_json"])
    except Exception:
        try:
            cats = ast.literal_eval(r["categories_json"])
        except Exception:
            cats = []
    n = len(cats) if isinstance(cats, list) else 0
    categories_expected_current += n
    max_categories_per_spec = max(max_categories_per_spec, n)

categories_expected_estimated = specs_total * max_categories_per_spec if max_categories_per_spec else categories_expected_current

vis = {r["status"]: r["n"] for r in cur.execute(
    "select status, count(*) n from spec_category_visit where run_id=? group by status",
    (run_id,),
)}

ck = {r["status"]: r["n"] for r in cur.execute(
    "select status, count(*) n from checkpoint_entry where run_id=? group by status",
    (run_id,),
)}
groups_accepted = ck.get("ACCEPTED", 0)
groups_pending_known = sum(v for k, v in ck.items() if k != "ACCEPTED")

leases = [dict(r) for r in cur.execute(
    "select owner, spec_key, expires_at from spec_lease where run_id=? and datetime(expires_at)>datetime('now') order by expires_at desc",
    (run_id,),
)]

hb = [dict(r) for r in cur.execute(
    "select worker_id, pid, started_at, last_heartbeat_at from worker_heartbeat where run_id=? order by last_heartbeat_at desc limit 16",
    (run_id,),
)]

rl = cur.execute(
    "select effective_concurrency, updated_at from rate_limiter_state where run_id=?",
    (run_id,),
).fetchone()

requests_total = cur.execute(
    "select count(*) from raw_capture where run_id=?",
    (run_id,),
).fetchone()[0] or 0

ch = cur.execute('''
select
  count(*) challenges_total,
  sum(case when resolved_at is null then 1 else 0 end) challenges_open
from challenge_event
where run_id=?
''', (run_id,)).fetchone()

wait_rows = list(cur.execute(
    "select observed_at, resolved_at from challenge_event where run_id=?",
    (run_id,),
))
challenge_wait_seconds_total = 0.0
for r in wait_rows:
    try:
        start = datetime.fromisoformat(r["observed_at"].replace("Z", "+00:00"))
        end_text = r["resolved_at"]
        end = datetime.fromisoformat(end_text.replace("Z", "+00:00")) if end_text else datetime.now(timezone.utc)
        challenge_wait_seconds_total += max((end - start).total_seconds(), 0)
    except Exception:
        pass

categories_done = vis.get("ACCEPTED", 0)
out = {
    "run_id": run_id,
    "scope": run["scope"] if run else None,
    "started_at": run["started_at"] if run else None,
    "resumed_at": run["resumed_at"] if run else None,
    "completed_at": run["completed_at"] if run else None,
    "manifests": {
        "done": manifests_complete,
        "todo": manifests_incomplete,
        "total": specs_total,
        "pct": round((manifests_complete / specs_total * 100), 2) if specs_total else 0,
    },
    "categories": {
        "done_ACCEPTED": categories_done,
        "rejected": vis.get("REJECTED", 0),
        "expected_current_manifests": categories_expected_current,
        "expected_estimated_final": categories_expected_estimated,
        "todo_vs_current_manifests": max(categories_expected_current - categories_done, 0),
        "todo_vs_estimated_final": max(categories_expected_estimated - categories_done, 0),
    },
    "groups": {
        "done_ACCEPTED": groups_accepted,
        "new_since_monitor_start": groups_accepted - base,
        "pending_known": groups_pending_known,
    },
    "requests_total": requests_total,
    "challenges_total": ch["challenges_total"] or 0,
    "challenges_open": ch["challenges_open"] or 0,
    "challenge_wait_seconds_total": round(challenge_wait_seconds_total, 2),
    "checkpoints_by_status": ck,
    "active_leases": leases,
    "heartbeats_latest": hb,
    "effective_concurrency": rl["effective_concurrency"] if rl else None,
    "rate_limiter_updated_at": rl["updated_at"] if rl else None,
}
print(json.dumps(out, ensure_ascii=False, indent=2))
"@

    $json = $code | & $Python -
    $state = $json | ConvertFrom-Json

    $elapsed = New-TimeSpan -Start $MonitorStartedAt -End $now
    $elapsedMinutes = [Math]::Max($elapsed.TotalMinutes, 0.01)
    $elapsedHours = [Math]::Max($elapsed.TotalHours, 0.01)
    $groupsPerMinute = [Math]::Round(($state.groups.new_since_monitor_start / $elapsedMinutes), 2)
    $challengesPerHour = [Math]::Round(($state.challenges_total / $elapsedHours), 2)

    Write-Host "run_id:                  $($state.run_id)"
    Write-Host "scope:                   $($state.scope)"
    Write-Host "completed_at:            $($state.completed_at)"
    Write-Host "elapsed_monitor:         $($elapsed.ToString('hh\:mm\:ss'))"
    Write-Host ""

    Write-Host "MANIFESTS"
    Write-Host "  feitos:                $($state.manifests.done) / $($state.manifests.total) ($($state.manifests.pct)%)"
    Write-Host "  faltam:                $($state.manifests.todo)"
    Write-Host ""

    Write-Host "CATEGORIAS"
    Write-Host "  ACCEPTED:              $($state.categories.done_ACCEPTED)"
    Write-Host "  REJECTED:              $($state.categories.rejected)"
    Write-Host "  esperadas atuais:      $($state.categories.expected_current_manifests)"
    Write-Host "  faltam atuais:         $($state.categories.todo_vs_current_manifests)"
    Write-Host "  estimativa final:      $($state.categories.expected_estimated_final)"
    Write-Host "  faltam estimado:       $($state.categories.todo_vs_estimated_final)"
    Write-Host ""

    Write-Host "GRUPOS"
    Write-Host "  ACCEPTED total:        $($state.groups.done_ACCEPTED)"
    Write-Host "  novos no monitor:      $($state.groups.new_since_monitor_start)"
    Write-Host "  pendentes conhecidos:  $($state.groups.pending_known)"
    Write-Host "  groups/min monitor:    $groupsPerMinute"
    Write-Host ""

    Write-Host "REQUESTS / CHALLENGES"
    Write-Host "  requests_total:        $($state.requests_total)"
    Write-Host "  challenges_total:      $($state.challenges_total)"
    Write-Host "  challenges_abertos:    $($state.challenges_open)"
    Write-Host "  challenges/h monitor:  $challengesPerHour"
    Write-Host "  challenge_wait_total:  $($state.challenge_wait_seconds_total)s"
    Write-Host ""

    Write-Host "EXECUCAO"
    Write-Host "  effective_concurrency: $($state.effective_concurrency)"
    Write-Host "  leases ativos:         $($state.active_leases.Count)"
    Write-Host "  rate_limiter_update:   $($state.rate_limiter_updated_at)"
    Write-Host ""

    Write-Host "Workers vivos por PID (worker=true exige processo python vivo):"
    $state.heartbeats_latest |
        Select-Object -Property pid, worker_id, last_heartbeat_at -Unique |
        ForEach-Object {
            $pidValue = $_.pid
            $p = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
            if ($p -and $p.ProcessName -eq "python") {
                [pscustomobject]@{
                    PID = $pidValue.ToString()
                    Alive = $true
                    Worker = $true
                    Name = $p.ProcessName
                    CPU = $p.CPU
                    LastHeartbeat = $_.last_heartbeat_at
                }
            } elseif ($p) {
                [pscustomobject]@{
                    PID = $pidValue.ToString()
                    Alive = $true
                    Worker = $false
                    Name = $p.ProcessName
                    CPU = $p.CPU
                    LastHeartbeat = $_.last_heartbeat_at
                }
            } else {
                [pscustomobject]@{
                    PID = $pidValue.ToString()
                    Alive = $false
                    Worker = $false
                    Name = ""
                    CPU = ""
                    LastHeartbeat = $_.last_heartbeat_at
                }
            }
        } | Format-Table -AutoSize

    Start-Sleep -Seconds $PollSeconds
}
