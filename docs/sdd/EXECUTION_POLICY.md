# Project SDD Execution Policy

Project: hubbi-amayama-scraper
Policy Version: 1.0.0
Constitution: .specify/memory/constitution.md

Este documento é um **overlay normativo** específico do projeto. Ele existe porque a infraestrutura genérica do GitHub Spec Kit (workflows, templates e skills gerados) não representa, por si só, todos os gates e regras obrigatórias definidos na Constitution deste projeto. Este overlay resolve esse gap sem alterar nenhum arquivo gerado pelo Spec Kit.

## Hierarquia de autoridade

Em caso de conflito, a precedência é estritamente a seguinte, da mais alta para a mais baixa:

1. `.specify/memory/constitution.md`
2. `docs/sdd/EXECUTION_POLICY.md` (este documento)
3. spec / plan / tasks explicitamente aprovados pelo PO para a feature em curso
4. contratos específicos dos agentes (`AGENTS.md`, `CLAUDE.md`, `docs/agents/CODEX.md`, `docs/agents/ANTIGRAVITY.md`)
5. workflows, templates e skills genéricos do Spec Kit (`.specify/workflows/**`, `.specify/templates/**`, `.claude/skills/**`)

**Regra obrigatória:** se qualquer workflow, template ou skill genérico do Spec Kit (nível 5) conflitar com qualquer item dos níveis 1–4, a instrução genérica deve ser ignorada naquele ponto específico, e a regra do projeto prevalece. O arquivo genérico não é editado — apenas sua instrução conflitante não é seguida.

## Workflow oficial

O fluxo abaixo é o único workflow normativo deste projeto. Ele formaliza e substitui, para efeitos de autoridade, qualquer workflow genérico do Spec Kit:

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
→ correção pelo Claude se houver REQUEST_CHANGES
→ nova revisão quando necessário
→ CHATGPT CONSOLIDA EVIDÊNCIAS
→ PO VALIDA ENTREGA
→ autorização explícita do PO
→ MERGE
```

Regras explícitas:

- **Nenhum passo posterior a um gate pode começar sem aprovação explícita do PO.** A existência de um artefato anterior não é, por si só, aprovação.
- **`speckit.implement` nunca deve ser executado automaticamente após `speckit.tasks`.** Entre `TASKS` e `CLAUDE IMPLEMENTA` há sempre um gate de aprovação explícita do PO.
- **A existência de um workflow genérico do Spec Kit não constitui autorização para avançar.** Scripts, templates ou skills que sugerem ou automatizam avanço de fase não substituem a aprovação do PO.
- **Aprovação do Codex não constitui autorização para merge.** `CODEX REVISA` é um passo técnico; `MERGE` só ocorre após `PO VALIDA ENTREGA` e autorização explícita do PO.

## Política de ambiguidades

- **"Informed guesses" de skills genéricos NÃO são permitidos** para decisões que possam alterar requisito, escopo, comportamento, modelo de dados, arquitetura, segurança, identidade, equivalência, persistência, coleta, critérios de aceite ou produto.
- Nesses casos, o agente deve **parar** e retornar a ambiguidade para ChatGPT/PO no gate apropriado (clarify/spec/plan/tasks), em vez de assumir uma interpretação.
- **Não transformar hipótese em requisito silenciosamente.** Uma suposição feita para destravar um raciocínio não pode virar comportamento implementado sem passar por aprovação.
- Apenas **decisões puramente mecânicas/de formatação sem efeito semântico** (ex.: nome de arquivo dentro de convenção já definida, formatação de Markdown, ordenação alfabética de uma lista não normativa) podem ser tomadas localmente pelo agente, sem retornar ao gate.

## Política de testes

- **Qualquer regra estrutural ou regra de domínio implementada deve possuir teste automatizado.** Isso vale independentemente do que um skill ou template genérico do Spec Kit disser sobre testes serem opcionais.
- **Testes de regressão devem ser adicionados para bugs**, quando aplicável, conforme a Constitution (seção de Qualidade e Testes).
- **Quando um skill/template genérico disser que testes são opcionais em determinado contexto, esta regra específica prevalece** — testes de regra estrutural nunca são opcionais neste projeto.
- **Tasks que implementam regra estrutural devem incluir trabalho de teste correspondente.** Uma task sem cobertura de teste para uma regra estrutural está incompleta.
- **Testes verdes não substituem validação do PO.** Suíte passando é condição necessária, não suficiente, para avanço de gate.

## Papel do Spec Kit

- O Spec Kit fornece **infraestrutura**: scripts, templates, skills e workflows auxiliares que aceleram a execução do ciclo SDD.
- Seus arquivos gerados (`.specify/workflows/**`, `.specify/scripts/**`, `.specify/templates/**`, `.claude/skills/**`) **permanecem intactos** — este overlay não os edita nem os substitui fisicamente.
- Esses arquivos **não são autoridade normativa superior à Constitution ou a esta Execution Policy.** Eles são ferramentas de execução, não fonte de regras de produto, segurança ou processo.
- **Os agentes devem aplicar este overlay antes de executar qualquer skill** (`/speckit-*`): ler Constitution → ler esta Execution Policy → ler os artefatos aprovados do estágio atual → só então usar o skill, ignorando qualquer instrução do skill que conflite com os níveis 1–4 da hierarquia de autoridade acima.
