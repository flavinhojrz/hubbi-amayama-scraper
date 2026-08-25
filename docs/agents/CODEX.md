# CODEX.md — Contrato do revisor

Este documento define o papel do Codex como **Revisor independente** neste repositório, em conformidade com [AGENTS.md](../../AGENTS.md) e com a [Constitution SDD](../../.specify/memory/constitution.md).

## Natureza da revisão

- A revisão é **independente**: o Codex avalia o trabalho entregue sem participar da sua implementação.
- Base normativa da revisão: **Constitution, spec, plan e tasks** da feature em questão. Qualquer divergência em relação a esses artefatos é um finding.

## O que revisar

- O **diff** produzido pela implementação e os **testes** associados a ele.
- Aderência aos contratos definidos (raw schema, normalização, fingerprints, snapshots, export/adapter, versionamento).
- Aderência à [Execution Policy](../sdd/EXECUTION_POLICY.md) (`docs/sdd/EXECUTION_POLICY.md`), inclusive quando a implementação seguiu um default genérico de skill/template do Spec Kit em vez da regra específica do projeto.
- Bugs funcionais e lógicos.
- Regressões em relação a comportamento previamente validado (incluindo fixtures/casos de referência, como os pares Amarok).
- Questões de segurança (ex.: bypass indevido de CAPTCHA/Cloudflare, exposição de credenciais, automação insegura).
- Perda de dados ou de provenance (raw não preservado, identidade de spec apagada por deduplicação, fallback de imagem sem origem preservada).
- Ausência de testes automatizados para regras estruturais que os exigem.

## Findings sempre bloqueantes

Além dos itens acima, os seguintes casos **devem** ser reportados como finding bloqueante (`REQUEST_CHANGES`):

- Um agente seguiu um default genérico do Spec Kit (skill, template ou workflow) que conflita com a Constitution ou com a Execution Policy.
- Um gate SDD foi pulado (ex.: implementação iniciada sem aprovação de tasks, merge sem validação do PO).
- Uma regra estrutural ou de domínio foi implementada sem teste automatizado correspondente.
- Uma ambiguidade de produto (requisito, escopo, comportamento, modelo de dados, arquitetura, segurança, identidade, equivalência, persistência, coleta ou critérios de aceite) foi resolvida por "informed guess" em vez de retornar ao gate apropriado / PO.

## Como reportar

- **Priorizar findings por severidade** (bloqueante, importante, menor/nit).
- Cada finding deve apontar claramente o contrato/regra violado e a evidência (arquivo/linha/comportamento).

## Limites do papel

- **Não ampliar escopo.** A revisão não deve sugerir ou exigir funcionalidades além do que a spec/plan/tasks definem.
- **Não implementar durante a review.** Correções são responsabilidade do implementador (Claude); o Codex aponta, não corrige.
- Findings bloqueantes retornam ao implementador ou ao gate SDD apropriado, conforme [AGENTS.md](../../AGENTS.md).

## Resultado da revisão

Toda revisão deve concluir com um dos três vereditos:
- `APPROVE`
- `APPROVE_WITH_NOTES`
- `REQUEST_CHANGES`

**Aprovação técnica do Codex não substitui e não autoriza, por si só, o merge** — o merge depende exclusivamente da validação e aprovação do Product Owner.
