"""JS injetado via `execute_async_script()` para fetch em lote dentro do
navegador já autenticado — compartilhado entre os adapters de transporte
(`chrome_cdp_adapter.py`, `undetected_chrome_adapter.py`).

Módulo puro (nenhum import de biblioteca de automação de navegador) — só a
string do script, para não duplicá-la entre os dois adapters. `fetch()` com
`credentials: 'include'` reusa os cookies da sessão já aberta; nada aqui
lê/escreve token de challenge, decide resultado de validação, ou tenta
esconder que a requisição vem de um navegador automatizado — só dispara a
mesma requisição HTTP que o próprio navegador já autenticado faria.
"""

from __future__ import annotations

# Sub-batelamento interno: uma única chamada execute_async_script com muitas
# URLs estoura o timeout do CLIENTE HTTP do Selenium (urllib3, ~120s) antes
# mesmo do script_timeout do Chrome ser atingido — bug encontrado e corrigido
# em spikes/batched_fetch_spike.py. 150 URLs/chamada, a ~300-400ms/URL
# observado empiricamente, fica bem dentro da margem.
MAX_URLS_PER_SCRIPT_CALL = 150

# fetch() em chunks concorrentes (Promise.all), com AbortController por-URL
# (nunca deixa uma URL travada segurar o lote inteiro) e credentials:'include'
# (reusa os cookies da sessão já autenticada — sem isso o fetch() não carrega
# nada além de conteúdo público). Captura também `r.url` (URL final
# pós-redirect) para popular BrowserCapture.effective_url corretamente
# quando o servidor redireciona (ex.: para uma página de challenge com outra
# URL).
BATCH_FETCH_JS = """
var callback = arguments[arguments.length - 1];
var urls = Array.from(arguments).slice(0, arguments.length - 1);
var results = {};
var i = 0;
var BATCH = arguments.__chunk_size__;
var TIMEOUT = arguments.__timeout_ms__;

function next() {
    if (i >= urls.length) { callback(results); return; }
    var chunk = urls.slice(i, i + BATCH);
    i += BATCH;
    var promises = chunk.map(function(url) {
        var ctrl = new AbortController();
        var tid = setTimeout(function() { ctrl.abort(); }, TIMEOUT);
        return fetch(url, {
            credentials: 'include',
            headers: {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            },
            signal: ctrl.signal
        })
        .then(function(r) {
            clearTimeout(tid);
            if (!r.ok) return null;
            return r.text().then(function(html) { return { html: html, url: r.url }; });
        })
        .catch(function() { clearTimeout(tid); return null; })
        .then(function(entry) {
            if (entry && entry.html) results[url] = entry;
        });
    });
    Promise.all(promises).then(next);
}
next();
"""


def render_batch_fetch_js(*, chunk_size: int, timeout_ms: int) -> str:
    return BATCH_FETCH_JS.replace("arguments.__chunk_size__", str(chunk_size)).replace(
        "arguments.__timeout_ms__", str(timeout_ms)
    )
