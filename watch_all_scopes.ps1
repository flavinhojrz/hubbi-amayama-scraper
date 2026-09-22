param([int]$PollSeconds = 15)

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "Python do projeto nao encontrado: $Python" }

$targets = @(
  @('EOS','EOS-BR'), @('PARATI-4P','PR-BR'), @('JETTA','JE-BR'), @('JETTA','JEB-BR'),
  @('JETTA-A7-PA2','JE-BR'), @('JETTA-VARIANT','JEV-BR'), @('NEW-BEETLE','NBE-BR'),
  @('NOVO-FUSCA','NFU-BR'), @('NIVUS','NIV-BR'), @('TCROSS','TCR-BR'), @('TAOS','TAO-BR'),
  @('TIGUAN','TIG-BR'), @('TIGUAN-ALLSPACE','TIGL-BR'), @('TIGUAN-TIGUAN-L','TIG-BR'),
  @('TOUAREG','TOUA-BR'), @('ID-BUZZ','IDB-BR'), @('ID4','ID4-BR'), @('ID4-ID5','ID4-BR'),
  @('PASSAT','PA-BR'), @('PASSAT-4MOTION','PA-BR'), @('PASSAT-VARIANT','PA-BR'),
  @('PASSAT-VARIANT-SANTANA','PA-BR'), @('PASSAT-CC','PACC-BR'), @('PASSAT-CC-COUPE','PACC-BR'),
  @('POLO','PO-BR'), @('POLO-DERBY-VENTO-IND','PO-BR'), @('POLO-POLO-JIN-QIN','PO-BR'),
  @('POLO-VENTO-CLASSIC-IND','PO-BR'), @('POLO-LIM-STUFENH-SEDAN','POS-BR'), @('POLO-SEDAN','POS-BR'),
  @('POLO-TRACK','POT-BR'), @('SANTANA-VARIANT','SA-BR'), @('SPACEFOX','SPRA-BR'),
  @('SPORTVAN','SPRA-BR'), @('TRANSPORTER','TR-BR'), @('TRANSPORTER-KOMBI','TR-BR'),
  @('UP','UP-BR'), @('UP-EUP','UP-BR'), @('VIRTUS','VIR-BR'), @('GOL-SPECIAL-2P','GLS-BR'), @('GOL','GL-BR')
)
$scopes = @($targets | ForEach-Object { "AMAYAMA:VOLKSWAGEN:$($_[0]):$($_[1])" })
$scopeJson = ($scopes | ConvertTo-Json -Compress)
$started = Get-Date
$base = @{}

while ($true) {
  $code = @"
import sqlite3,json,os
scopes=json.loads(r'''$scopeJson''')
con=sqlite3.connect('amayama.db'); con.row_factory=sqlite3.Row; c=con.cursor()
out=[]
for scope in scopes:
    run=c.execute("""select run_id,completed_at from collection_run where scope=? order by case when completed_at is null then 0 else 1 end, coalesce(resumed_at,started_at,'') desc,rowid desc limit 1""",(scope,)).fetchone()
    if not run: out.append({'scope':scope,'missing':1}); continue
    rid=run['run_id']
    m=c.execute("""with x as (select spec_key,max(id) id from spec_group_manifest where run_id=? group by spec_key) select sum(manifest_complete=1) done,count(*) total from spec_group_manifest m join x on x.id=m.id""",(rid,)).fetchone()
    v={r['status']:r['n'] for r in c.execute("select status,count(*) n from spec_category_visit where run_id=? group by status",(rid,))}
    g={r['status']:r['n'] for r in c.execute("select status,count(*) n from checkpoint_entry where run_id=? group by status",(rid,))}
    req=c.execute("select count(*) from raw_capture where run_id=?",(rid,)).fetchone()[0] or 0
    ch=c.execute("select count(*) from challenge_event where run_id=?",(rid,)).fetchone()[0] or 0
    leases=c.execute("select count(*) from spec_lease where run_id=? and datetime(expires_at)>datetime('now')",(rid,)).fetchone()[0]
    hb=list(c.execute("select pid,last_heartbeat_at from worker_heartbeat where run_id=? order by last_heartbeat_at desc limit 8",(rid,)))
    out.append({'scope':scope,'run_id':rid,'completed_at':run['completed_at'],'m_done':m['done'] or 0,'m_total':m['total'] or 0,'a':v.get('ACCEPTED',0),'r':v.get('REJECTED',0),'g':g.get('ACCEPTED',0),'gp':sum(n for s,n in g.items() if s!='ACCEPTED'),'req':req,'ch':ch,'leases':leases,'pids':[h['pid'] for h in hb]})
print(json.dumps(out))
"@
  $rows = (($code | & $Python -) | ConvertFrom-Json)
  Clear-Host
  $now = Get-Date
  Write-Host "STATUS VOLKSWAGEN - $($now.ToString('yyyy-MM-dd HH:mm:ss'))"
  Write-Host "Escopos: $($rows.Count) | monitorando desde $($started.ToString('HH:mm:ss')) | Ctrl+C para sair"
  Write-Host ""
  $table = foreach ($r in $rows) {
    if ($r.missing) { [pscustomobject]@{Scope=$r.scope -replace '^AMAYAMA:VOLKSWAGEN:','';RunId='NA';Specs='NA';Cats='NA';Rejected='NA';Groups='NA';Pending='NA';Req='NA';Ch='NA';Leases='NA';Workers='NA';Status='NAO ENCONTRADO'}; continue }
    $live = @($r.pids | Where-Object { try { $p=Get-Process -Id $_ -ErrorAction Stop; $p.ProcessName -match 'python' } catch { $false } }).Count
    $short = $r.run_id.Substring(0,8)
    [pscustomobject]@{Scope=$r.scope -replace '^AMAYAMA:VOLKSWAGEN:','';RunId=$short;Specs="$($r.m_done)/$($r.m_total)";Cats=$r.a;Rejected=$r.r;Groups=$r.g;Pending=$r.gp;Req=$r.req;Ch=$r.ch;Leases=$r.leases;Workers=$live;Status=if($r.completed_at){'CONCLUIDO'}else{'ATIVO'}}
  }
  $table | Format-Table -AutoSize
  Start-Sleep -Seconds ([Math]::Max(2,$PollSeconds))
}
