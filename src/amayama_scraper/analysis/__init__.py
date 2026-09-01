"""analysis/ — resumo, qualidade, redundância e comparação sobre o corpus já coletado.

003-corpus-analysis-tool. Puro (sem sqlite3/I/O) — mesma disciplina do
DOMAIN_LAYER_PACKAGES (tests/unit/test_architecture_boundaries.py), embora
este pacote não seja adicionado à lista de enforcement do teste existente
(extensão nova, não mudança de contrato já aprovado). Toda leitura de banco
acontece em persistence/repositories/*.py; toda composição/apresentação
acontece em cli/analyze.py.
"""

from __future__ import annotations
