# Quickstart / Guia de Validação: Performance Worker Pool

**Feature**: `005-performance-worker-pool` | **Spec**: [spec.md](./spec.md) | **Contracts**: [contracts/worker-pool-contract.md](./contracts/worker-pool-contract.md)

> Cenários executáveis **quando a implementação existir** (TASKS futura, sob
> aprovação do PO). Nenhum código é criado por este documento. Os cenários
> de teste automatizado são 100% offline/determinísticos (SC-002 a SC-004);
> a validação real (Fase de benchmark) exige N Chromes reais e é o item 14
> do pedido do PO — evidência de integração, fora do escopo desta entrega.

## Como cada worker obtém sua sessão de navegador (FR-040 a FR-043)

Cada worker é um **processo de SO independente** com seu próprio
`ChromeCdpTransport`, anexado a um Chrome real distinto — nunca uma thread
compartilhando um driver Selenium (ver
`contracts/worker-pool-contract.md` §0 para o porquê).

Pré-requisito operacional: o operador abre **N** Chromes reais, um por
worker, cada um numa porta de depuração remota distinta:

```powershell
# Worker 0
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
    --remote-debugging-port=9222 --user-data-dir="$env:TEMP\amayama-chrome-0"

# Worker 1
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
    --remote-debugging-port=9223 --user-data-dir="$env:TEMP\amayama-chrome-1"
```

(um `--user-data-dir` dedicado por worker — nunca o perfil pessoal do
operador nem um diretório compartilhado entre workers; confirmar, uma vez
por sessão de cada Chrome, que a tradução automática está desativada — mesma
pré-condição já documentada em `specs/002-.../quickstart.md`.)

Depois, `amayama-scraper run --workers 2` (default `--cdp-ports` deriva de
`--cdp-port`/`9222` como base + índice do worker; ou explicitamente
`--cdp-ports 9222,9223`).

## Cenário 1 — `--workers 1` é bit-a-bit idêntico ao pipeline pré-005

**Valida**: FR-003, SC-001.

```
pytest tests/integration/test_worker_pool_workers_one_parity.py
pytest -q   # suíte completa 001-004 continua verde
```

**Esperado**: nenhuma diferença de eventos/checkpoints entre `--workers 1`
(caminho de código legado) e o pipeline anterior a 005.

## Cenário 2 — Claim/lease nunca duplica dono de spec

**Valida**: FR-020 a FR-023, SC-002, SC-003.

```
pytest tests/unit/test_lease_claim_semantics.py
pytest tests/integration/test_worker_pool_no_double_claim.py
pytest tests/integration/test_worker_pool_lease_recovery.py
```

**Esperado**: dois claims concorrentes para a mesma `spec_key` nunca ambos
sucedem; um lease expirado é recuperável sem reprocessar grupos `ACCEPTED`.

## Cenário 3 — Rate limiter reage a challenge e recupera com estabilidade

**Valida**: FR-060 a FR-065, SC-004.

```
pytest tests/unit/test_rate_limiter.py
pytest tests/integration/test_worker_pool_rate_limiter_reacts.py
```

**Esperado**: sequência determinística de `effective_concurrency` dado um
clock injetado — nunca depende de `time.sleep` real.

## Cenário 4 — Isolamento de contexto 004 sob concorrência

**Valida**: FR-100, FR-101, SC-005.

```
pytest tests/integration/test_worker_pool_context_isolation.py
pytest tests/integration/test_multi_model_isolation.py   # 004, continua verde
```

## Cenário 5 — Resume com worker pool

**Valida**: FR-090, FR-091.

```
pytest tests/integration/test_worker_pool_resume.py
```

---

## Validação real (fora desta entrega) — item 14 do pedido do PO

**Pré-condição**: implementação aprovada pelo PO e efetivamente executada
(gate `CLAUDE IMPLEMENTA`), suíte automatizada 100% verde.

> ⚠️ **Isolamento de porta CDP é responsabilidade do operador — obrigatório
> antes de cada run do benchmark, sem exceção:**
>
> 1. **Nunca rode o baseline (`--workers 1`) e a comparação (`--workers 2`)
>    ao mesmo tempo.** Execute-os **sequencialmente**: espere o baseline
>    terminar (ou seja encerrado deliberadamente) antes de iniciar o run de
>    2 workers.
> 2. **Nenhuma porta de depuração remota (`--cdp-ports`) pode estar em uso
>    por outro processo Selenium/WebDriver simultaneamente** — nem outro
>    benchmark, nem uma sessão manual de debug, nem um Chrome "esquecido"
>    aberto de uma execução anterior. Confirme (`netstat`/Task Manager) que
>    a única coisa conectada a cada porta é o worker atual antes de iniciar.
> 3. **Cada worker precisa do seu próprio Chrome exclusivo** — nunca
>    reaproveite a mesma janela/porta entre dois workers, ou entre um
>    benchmark anterior e o atual.
>
> Anexar um segundo cliente WebDriver à mesma porta CDP enquanto outro já
> está anexado é uma configuração **não suportada** pelo par
> Selenium/chromedriver: o chromedriver associa cada sessão a um estado de
> destino (`target`) que assume controle exclusivo para correlação
> confiável de comando/resposta. Quando um segundo processo anexa-se à
> mesma porta e emite comandos concorrentes (ex.: `Page.navigate`) no mesmo
> destino, a primeira sessão pode observar seu destino/estado invalidado
> externamente — o sintoma típico é `InvalidSessionIdException: invalid
> session id` na sessão mais antiga, sem que nada esteja errado no código
> do worker pool. Este risco já constava, sem validação empírica prévia, em
> `contracts/worker-pool-contract.md` §5 ("duas sessões WebDriver vivas no
> mesmo Chrome, nunca concorrentes"); trate-o como uma pré-condição
> operacional obrigatória, não como algo que o scraper deva detectar ou
> corrigir em runtime.

```powershell
# Baseline — 1 worker (poucas specs reais)
# Rode isto sozinho. Espere terminar por completo antes do próximo bloco.
amayama-scraper run --manufacturer VOLKSWAGEN --vehicle-model GOL --market GL-BR `
    --workers 1 --limit-specs 10 --new-run

# Comparação — 2 workers (mesmo escopo, novo run)
# Só inicie depois que o baseline acima tiver terminado e as portas 9222/9223
# estiverem livres de qualquer outro processo.
amayama-scraper run --manufacturer VOLKSWAGEN --vehicle-model GOL --market GL-BR `
    --workers 2 --cdp-ports 9222,9223 --limit-specs 10 --new-run
```

**Métrica de decisão**: `groups/min` (US4) e taxa de challenge
(`challenges/hora`) dos dois runs — sucesso é throughput real maior **sem**
aumento desproporcional de challenge, nunca apenas "rodou com 2 workers".
