# hubbi-amayama-scraper

Scraper dedicado à fonte **Amayama** para catálogo genuíno Volkswagen, com foco inicial em veículos relevantes ao mercado brasileiro. O projeto busca produzir dados confiáveis, reproduzíveis e integráveis ao ecossistema Hubbi, preservando a identidade original das specs coletadas (proveniência e auditabilidade).

## Status atual

🚧 **Bootstrap SDD — sem código funcional.**

Este repositório está atualmente na fase de governança e documentação (Spec-Driven Development). Nenhum scraper, parser, integração Selenium, motor de fingerprints, banco de dados, CLI ou teste funcional foi implementado ainda. Os próximos passos seguem o fluxo SDD descrito abaixo, a partir de specs e plans aprovados pelo Product Owner.

## Fonte e escopo

- **Fonte**: Amayama.
- **Escopo inicial**: Volkswagen, com relevância oficial para o mercado brasileiro, conforme pesquisa já consolidada. A Amayama não é usada como fonte de verdade para provar comercialização oficial no Brasil — essa decisão de escopo vem de evidência externa já consolidada.

## Arquitetura conceitual

O pipeline de dados obedece à separação de responsabilidades definida na Constitution:

```
transport/navigation
→ HTML/raw capture
→ parser
→ raw domain model
→ normalization/fingerprints
→ equivalence/deduplication
→ adapter/export
```

Browser, parser, deduplicação e adapter são camadas distintas e não devem ser fundidas. Dados brutos são preservados de forma imutável antes de qualquer adaptação, e a deduplicação técnica nunca apaga aplicabilidade ou origem de uma spec.

## Workflow SDD

O ciclo de vida de toda feature segue o fluxo abaixo, com aprovação explícita do Product Owner em cada gate:

```
CONSTITUTION
→ PO APPROVAL
→ SPECIFY
→ PO APPROVAL
→ CLARIFY, se necessário
→ PLAN
→ PO APPROVAL
→ TASKS
→ PO APPROVAL
→ CLAUDE IMPLEMENTA
→ CODEX REVISA
→ CHATGPT CONSOLIDA EVIDÊNCIAS
→ PO VALIDA
→ MERGE
```

## Papéis dos agentes

- **Product Owner — Flávio**: decisão final de produto; aprova/rejeita gates; única autoridade para merge.
- **Coordenação — ChatGPT**: gerencia o ciclo SDD, mantém documentação e rastreabilidade, prepara specs/plans/tasks, consolida evidências.
- **Implementador — Claude**: implementa somente artefatos e tasks aprovados; não amplia escopo silenciosamente. Ver [CLAUDE.md](CLAUDE.md).
- **Revisor — Codex**: revisão técnica independente de aderência a constitution/spec/plan/tasks, bugs, regressões, segurança e testes. Ver [docs/agents/CODEX.md](docs/agents/CODEX.md).
- **QA/Integração Experimental — Antigravity**: browser-in-the-loop, testes exploratórios, reprodução de fluxos e evidências. Ver [docs/agents/ANTIGRAVITY.md](docs/agents/ANTIGRAVITY.md).

Regras globais para qualquer agente estão consolidadas em [AGENTS.md](AGENTS.md).

## Governança

A autoridade normativa do projeto é a Constitution SDD, disponível em [`.specify/memory/constitution.md`](.specify/memory/constitution.md) (v1.0.0, ratificada em 2026-08-25).

### Governança SDD e overlay de execução

Este projeto usa o GitHub Spec Kit como infraestrutura (scripts, templates e skills auxiliares), mas o workflow genérico gerado em [`.specify/workflows/speckit/workflow.yml`](.specify/workflows/speckit/workflow.yml) é apenas infraestrutura padrão do Spec Kit — **ele não representa sozinho o workflow normativo deste projeto** (não formaliza, por exemplo, todos os gates de aprovação do PO nem os papéis de Codex/ChatGPT/PO no fluxo pós-implementação).

O workflow normativo real, com todos os gates obrigatórios e a precedência sobre defaults genéricos, está definido em:

- Constitution: [`.specify/memory/constitution.md`](.specify/memory/constitution.md)
- Execution Policy (overlay normativo): [`docs/sdd/EXECUTION_POLICY.md`](docs/sdd/EXECUTION_POLICY.md)
- Workflow declarativo do projeto: [`docs/sdd/project-workflow.yml`](docs/sdd/project-workflow.yml)

## Rastreabilidade

Este bootstrap corresponde ao [GitHub Issue #2](../../issues/2) — "Bootstrap SDD e materializar Constitution v1.0".
