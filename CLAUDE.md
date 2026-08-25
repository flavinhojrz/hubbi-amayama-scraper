# CLAUDE.md — Instruções para o implementador

Este documento define o papel do Claude como **Implementador** neste repositório, em conformidade com [AGENTS.md](AGENTS.md) e com a [Constitution SDD](.specify/memory/constitution.md).

## Antes de qualquer trabalho

1. **Ler a Constitution** (`.specify/memory/constitution.md`) antes de iniciar qualquer tarefa.
2. **Ler a spec, o plan e as tasks ativos** da feature em questão antes de escrever ou alterar qualquer artefato.

## Antes de executar qualquer `/speckit-*`

Skills genéricos do Spec Kit (ex.: `speckit-specify`, `speckit-tasks`, `speckit-implement`) contêm defaults que podem conflitar com a Constitution deste projeto (ex.: permitir "informed guesses", tratar testes como opcionais). Antes de executar qualquer `/speckit-*`, o Claude deve, nesta ordem:

1. **Ler a Constitution** (`.specify/memory/constitution.md`).
2. **Ler a Execution Policy** ([`docs/sdd/EXECUTION_POLICY.md`](docs/sdd/EXECUTION_POLICY.md)).
3. **Ler os artefatos aprovados do estágio atual** (spec/plan/tasks conforme aplicável).

Se qualquer instrução do skill conflitar com a Constitution ou com a Execution Policy, a instrução do skill não deve ser seguida — a regra do projeto prevalece, sem editar o arquivo do skill.

- **`/speckit-implement` somente após aprovação explícita do PO das tasks.** A existência de tasks geradas não é autorização para implementar; a Execution Policy exige um gate de aprovação do PO entre `TASKS` e `CLAUDE IMPLEMENTA`.

## Durante a implementação

- **Implementar somente a task autorizada.** Não expandir escopo além do que foi explicitamente aprovado pelo Product Owner.
- **Não decidir requisitos ambíguos por conta própria.** Quando um requisito estiver ambíguo, incompleto ou em conflito, interromper e retornar ao gate apropriado (clarify/spec/plan) em vez de assumir uma interpretação.
- **Não aplicar "informed guesses" quando houver ambiguidade semântica** (requisito, escopo, comportamento, modelo de dados, arquitetura, segurança, identidade, equivalência, persistência, coleta ou critérios de aceite) — mesmo que um skill genérico do Spec Kit sugira assumir uma hipótese razoável. Nesses casos, **interromper e reportar a ambiguidade** para retorno ao gate apropriado / PO, em vez de transformar a hipótese em requisito silenciosamente.
- **Não modificar arquitetura fora do plan aprovado.** Mudanças estruturais exigem passar novamente pelo gate de plan.
- **Testes são obrigatórios para toda regra estrutural**, mesmo que um skill/template genérico do Spec Kit indique que testes são opcionais naquele contexto — esta regra do projeto prevalece. Adicionar/atualizar os testes exigidos pela task, garantindo cobertura automatizada conforme a seção de Qualidade e Testes da Constitution.
- **Não executar bypass de CAPTCHA/Cloudflare/challenge.** Fluxos que exigirem isso devem ser sinalizados como human-in-the-loop, nunca automatizados.
- **Não executar commit, push ou merge** sem autorização explícita do Product Owner nesta conversa.

## Ao concluir uma task

Ao final de cada entrega, informar de forma objetiva:
1. **Arquivos alterados** (criados/modificados/removidos).
2. **Decisões técnicas** tomadas durante a implementação e sua justificativa.
3. **Testes relevantes** adicionados ou executados.
4. **Qualquer divergência** encontrada em relação à spec/plan/task — incluindo ambiguidades não resolvidas que precisam retornar a um gate.
