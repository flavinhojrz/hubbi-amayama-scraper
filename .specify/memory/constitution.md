# hubbi-amayama-scraper Constitution

**Project**: hubbi-amayama-scraper
**Constitution Version**: 1.0.0
**Ratified**: 2026-08-25
**Last Amended**: 2026-08-25

## 1. Missão do projeto

Construir um scraper dedicado à fonte Amayama para catálogo genuíno Volkswagen, com foco inicial em veículos relevantes ao mercado brasileiro, preservando aplicabilidade, proveniência e auditabilidade dos dados.

O projeto deve produzir dados confiáveis, reproduzíveis e integráveis ao ecossistema Hubbi sem apagar a identidade original das specs da Amayama.

## 2. Fonte e escopo

- A fonte atribuída ao projeto é a Amayama.
- O escopo inicial de produto é Volkswagen com relevância oficial para o Brasil conforme pesquisa já consolidada.
- A Amayama não é fonte de verdade para provar comercialização oficial no Brasil; essa decisão de escopo vem de evidência externa já consolidada.
- O scraper deve preservar a hierarquia:
  modelo → mercado → spec entry → categoria → grupo → schema → OEM
- `model_code` sozinho não identifica uma entrada de catálogo.
- `amayama_catalog_id` e `source_url` devem participar da identidade da spec.

## 3. Preservação de identidade

A deduplicação técnica nunca pode apagar aplicabilidade ou origem.

Fluxo conceitual:

```
spec original
→ conteúdo pode ser equivalente
→ coleta pode ser deduplicada
→ identidade e aplicações continuam preservadas
```

Cada spec deve preservar no mínimo:
- mercado;
- model_code;
- amayama_catalog_id;
- período de produção;
- grade/configuração quando comprovada;
- source_url.

## 4. Raw data imutável e auditável

- Dados brutos coletados devem ser preservados antes de adaptação ou limpeza destrutiva.
- Cada coleta aceita deve gerar evidência suficiente para auditoria.
- Snapshots válidos são imutáveis.
- Reprocessamento deve gerar nova observação/snapshot, nunca sobrescrever silenciosamente histórico anterior.
- Transformações derivadas devem ser reproduzíveis a partir do raw preservado.

## 5. Coleta e segurança

- Não automatizar bypass de autenticação, CAPTCHA ou Cloudflare.
- Quando a árvore `/epc/` exigir challenge, o fluxo permitido é human-in-the-loop.
- O navegador pode ser usado como transporte validado; parsing deve permanecer separado da automação de browser.
- CAPTCHA, challenge, tradução automática do navegador ou HTML inválido nunca podem ser aceitos como conteúdo de catálogo.
- O scraper deve suportar checkpoints e retomada para evitar refazer trabalho já validado.

## 6. Separação de responsabilidades

Arquitetura conceitual obrigatória:

```
transport/navigation
→ HTML/raw capture
→ parser
→ raw domain model
→ normalization/fingerprints
→ equivalence/deduplication
→ adapter/export
```

Browser, parser, deduplicação e adapter não devem ser fundidos em uma única camada.

## 7. Normalização conservadora

- Normalização deve ser determinística e versionada.
- Unicode NFKC, whitespace e códigos técnicos podem ser padronizados conforme contrato aprovado.
- Não traduzir, fazer stemming, fuzzy matching, correção ortográfica ou substituição por sinônimos como parte da equivalência exata.
- Mudança de regra de normalização exige nova versão e revalidação dos fingerprints dependentes.

## 8. Fingerprints e equivalência

- Deduplicação de peças é content-addressable e determinística.
- SHA-256 com domain separators e versões explícitas.
- Registros são comparados como multiset; duplicatas legítimas devem alterar o resultado.
- `parts`, schema semântico e imagens possuem fingerprints independentes.
- Imagens não participam da decisão de equivalência de peças.
- A deduplicação só é permitida quando a comparação é válida e `parts_relation == EXACT`.
- Heurísticas servem apenas para geração de candidatos, nunca como prova de equivalência.

## 9. Classes de equivalência e representante

O cluster canônico de peças deve ser derivado deterministicamente por:

```
scope + fingerprint_version + spec_parts_hash
```

O representante serve apenas para otimizar coleta.
Specs não representantes continuam existindo como aplicações/origens válidas.

Critério determinístico do representante:
1. snapshot válido;
2. maior cobertura de imagens;
3. catálogo mais atual;
4. maior completude de metadados;
5. chave estável como desempate.

## 10. Imagens e fallback

- Cobertura de imagens é independente da equivalência de peças.
- Fallback de imagem só é permitido dentro de classe de equivalência comprovada.
- A origem real da imagem usada deve ser preservada.
- Nunca atribuir silenciosamente uma imagem de outra spec sem provenance.

## 11. Snapshots e revalidação

- Cada coleta completa aceita gera snapshot imutável.
- Estados mínimos:
  - VALID
  - INCOMPLETE
  - STALE
  - SUPERSEDED
  - INVALID
- INCOMPLETE e INVALID não participam de equivalência.
- Mudança apenas de imagem não altera cluster de peças.
- Mudança de `spec_parts_hash` move a spec para outra classe de equivalência.
- Revalidação deve ser incremental e aproveitar fingerprints hierárquicos para localizar divergências.
- Políticas de freshness devem ser configuráveis e podem diferenciar specs atuais e encerradas.

## 12. Qualidade e testes

- Núcleos de domínio devem ser determinísticos e testáveis sem rede.
- Toda regra estrutural deve possuir teste automatizado.
- Regressões dos pares Amarok já estudados devem virar fixtures/testes de referência.
- Testes verdes não substituem aprovação de produto.
- Bugs encontrados por revisão devem gerar caso de regressão quando aplicável.
- Nenhuma mudança pode quebrar silenciosamente contratos versionados.

## 13. Versionamento e compatibilidade

Versionar explicitamente pelo menos:
- parser;
- normalizer;
- fingerprint algorithm;
- raw schema quando necessário;
- export/adapter schema quando necessário.

Hashes calculados por versões incompatíveis não devem ser comparados diretamente como se fossem equivalentes.

## 14. SDD e gates obrigatórios

Fluxo oficial:

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

Regras:
- nenhuma fase avança sem aprovação explícita do PO quando houver gate;
- Claude implementa somente tasks aprovadas;
- Codex revisa aderência à spec/plan/task, qualidade, testes e regressões;
- aprovação do Codex não substitui aprovação do PO;
- mudanças de requisito durante implementação retornam ao gate apropriado;
- PR permanece draft enquanto a entrega não estiver validada;
- merge automático é proibido;
- main é a linha estável.

## 15. Papéis

**Product Owner — Flávio**
- decisão final de produto;
- aprova/rejeita gates;
- valida funcionalmente as entregas;
- única autoridade para autorizar avanço de gate e merge final.

**Coordenação — ChatGPT**
- gerencia o ciclo SDD;
- mantém documentação e rastreabilidade;
- prepara specs, plans e tasks;
- consolida evidências de Claude, Codex e Antigravity;
- não substitui aprovação do PO.

**Implementador — Claude**
- implementa somente artefatos e tasks aprovados;
- não amplia escopo silenciosamente;
- não decide requisitos ausentes;
- ambiguidades relevantes devem retornar ao gate apropriado.

**Revisor — Codex**
- revisão independente;
- verifica aderência a constitution/spec/plan/tasks;
- verifica bugs, regressões, segurança, contratos e testes;
- não deve transformar revisão em implementação de novas funcionalidades;
- aprovação técnica não substitui aprovação do PO.

**QA/Integração Experimental — Antigravity**
- browser-in-the-loop;
- testes exploratórios;
- reprodução de fluxos;
- investigação experimental de falhas;
- geração de artifacts/evidências;
- não substitui Claude como implementador;
- não substitui Codex como revisor;
- não possui autoridade de gate.

## 16. Rastreabilidade

Toda feature implementada deve ser rastreável:

```
requisito
→ spec
→ plan
→ task
→ commit / PR
→ testes e revisão
→ aprovação do PO
```

Decisões estruturais relevantes devem permanecer registradas no GitHub e/ou documentação do projeto.

## 17. Alteração da Constitution

Mudanças na Constitution exigem:
1. proposta explícita;
2. justificativa;
3. avaliação de impacto;
4. aprovação do Product Owner;
5. atualização versionada do documento;
6. reavaliação de specs/plans ativos quando a mudança os afetar.

---

Fim da Constitution aprovada.
