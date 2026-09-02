# Amarok AMA-BR Dashboard

Um dashboard simples e local para visualizar os dados consolidados da Volkswagen Amarok AMA-BR (scraper Amayama).

O dashboard lê diretamente os arquivos `amarok-summary.json` e `amarok-redundancy.json` localizados na raiz do projeto, sem necessidade de banco de dados ou backend complexo.

## Como iniciar

Foi criado um script Python mínimo para iniciar um servidor local e abrir automaticamente o navegador, contornando limitações de CORS (segurança) que impediriam a leitura dos JSONs se o HTML fosse aberto diretamente no protocolo `file://`.

Para iniciar, rode:

```bash
python tools/dashboard/serve.py
```

O script irá:
1. Iniciar um servidor HTTP simples na porta `8080` (na raiz do projeto).
2. Abrir o navegador automaticamente no endereço `http://localhost:8080/tools/dashboard/index.html`.
3. Desativar o cache do navegador (para refletir novas mudanças no JSON imediatamente caso o scraper seja rodado novamente).

Para parar o servidor, pressione `Ctrl+C` no terminal.

## Funcionalidades
- **Modo dark/light** automático (via `@media (prefers-color-scheme: dark)`).
- **Cards** mostrando contagens gerais (Specs, Estrutura, Peças e Redundância).
- **Gráficos** construídos usando apenas HTML/CSS (rápido, sem dependências de frameworks).
- **Lista Expansível de Clusters** de redundância com:
  - Detalhes (model_code, grade, período de produção, configuration, peças).
  - Um filtro de busca instantâneo na lista (código, grade, etc.).
  - Opção de copiar o `stable_key` da spec ao clicar.
- Nenhuma dependência externa, rápido e totalmente estático pelo lado do cliente.
