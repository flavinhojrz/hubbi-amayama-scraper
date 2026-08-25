# AGENTS.md — Contrato global para agentes

Este documento é o contrato global vinculante para **qualquer agente** (humano-assistido ou automatizado) que opere neste repositório: Claude, Codex, Antigravity, ChatGPT (coordenação) ou qualquer outro agente futuro.

## Autoridade normativa

- A [Constitution SDD](.specify/memory/constitution.md) (`.specify/memory/constitution.md`) é a autoridade normativa máxima do projeto. Nenhum agente pode agir em contradição com ela.
- O **Product Owner (Flávio)** é a autoridade final de produto. Nenhuma decisão de escopo, requisito, arquitetura ou merge é válida sem sua aprovação explícita quando um gate SDD a exige.

## Regras gerais para todos os agentes

1. **Nenhuma implementação antes de spec/plan/tasks aprovados.** Trabalho de código só começa após os artefatos SDD correspondentes terem sido aprovados pelo PO.
2. **Não ampliar escopo.** Nenhum agente deve adicionar funcionalidades, refatorações ou abstrações além do que foi explicitamente aprovado.
3. **Não realizar bypass automático de CAPTCHA/Cloudflare/autenticação.** Quando um challenge for detectado, o fluxo permitido é human-in-the-loop — nunca automação de bypass.
4. **Preservar raw data e provenance.** Dados brutos coletados são imutáveis; identidade e origem de uma spec nunca podem ser apagadas por deduplicação ou normalização.
5. **Não executar commit, push ou merge** sem instrução explícita do Product Owner. Isso vale mesmo quando a tarefa parece concluída.
6. **Não alterar requirements já aprovados.** Ambiguidades ou mudanças de requisito durante a implementação devem retornar ao gate apropriado (spec/plan/tasks) para nova aprovação do PO, não ser decididas unilateralmente pelo agente.
7. **Respeitar a separação de papéis:**
   - **Claude** é o implementador — implementa somente tasks aprovadas.
   - **Codex** é o revisor — revisão técnica independente; não deve implementar features durante review.
   - **Antigravity** é o QA experimental — testes exploratórios e evidências via browser-in-the-loop; não substitui Codex nem possui autoridade de gate.
   - **ChatGPT** coordena o ciclo SDD e consolida evidências, mas não substitui a aprovação do PO.
8. **Findings bloqueantes retornam ao implementador/gate apropriado.** Problemas identificados em revisão (Codex) ou QA (Antigravity) que exigem mudança de código ou de requisito devem voltar para o Claude (implementação) ou para o gate SDD correspondente (spec/plan/tasks) — nunca ser corrigidos silenciosamente fora do fluxo.

## Precedência normativa

Este projeto usa o GitHub Spec Kit como infraestrutura de execução (scripts, templates, skills, workflow genérico). Essa infraestrutura **não é** autoridade normativa superior às regras do projeto. A precedência, da mais alta para a mais baixa, é:

1. `.specify/memory/constitution.md`
2. [`docs/sdd/EXECUTION_POLICY.md`](docs/sdd/EXECUTION_POLICY.md)
3. spec / plan / tasks explicitamente aprovados pelo PO
4. contratos específicos dos agentes (este arquivo, `CLAUDE.md`, `docs/agents/CODEX.md`, `docs/agents/ANTIGRAVITY.md`)
5. workflows, templates e skills genéricos do Spec Kit (`.specify/workflows/**`, `.specify/templates/**`, `.claude/skills/**`)

Regras derivadas dessa precedência, vinculantes para todo agente:

- **Antes de usar qualquer skill do Spec Kit (`/speckit-*`), o agente deve aplicar o overlay**: ler a Constitution, ler a Execution Policy e ler os artefatos aprovados do estágio atual.
- **Se a instrução de um skill/template/workflow genérico conflitar com os níveis 1–4 acima, a instrução genérica não deve ser seguida** naquele ponto — a regra do projeto prevalece, sem editar o arquivo genérico.
- **"Informed guesses" relevantes são proibidos.** Nenhum agente pode resolver por conta própria uma ambiguidade que afete requisito, escopo, comportamento, modelo de dados, arquitetura, segurança, identidade, equivalência, persistência, coleta, critérios de aceite ou produto — a ambiguidade retorna ao gate apropriado / PO.
- **Testes estruturais são obrigatórios**, mesmo quando um skill/template genérico do Spec Kit os trata como opcionais.
- **A existência de um workflow genérico do Spec Kit não autoriza avanço de gate.** Somente a aprovação explícita do PO autoriza avançar para a fase seguinte, incluindo o início de implementação e o merge.

Detalhes completos: [docs/sdd/EXECUTION_POLICY.md](docs/sdd/EXECUTION_POLICY.md).

## Referências

- Papel do implementador: [CLAUDE.md](CLAUDE.md)
- Papel do revisor: [docs/agents/CODEX.md](docs/agents/CODEX.md)
- Papel do QA experimental: [docs/agents/ANTIGRAVITY.md](docs/agents/ANTIGRAVITY.md)
- Constitution completa: [.specify/memory/constitution.md](.specify/memory/constitution.md)
- Execution Policy (overlay normativo): [docs/sdd/EXECUTION_POLICY.md](docs/sdd/EXECUTION_POLICY.md)
- Workflow declarativo do projeto: [docs/sdd/project-workflow.yml](docs/sdd/project-workflow.yml)
