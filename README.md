# Workplace English Practice

Colete exemplos de comunicação profissional em inglês publicados pela Doist e pelo Zulip e consulte o material localmente para estudar.

## Baixar a coleta

Abra o PowerShell na raiz do clone `workplace-english-practice` e rode com Python 3.11 ou superior e acesso à internet.

```powershell
python .\baixar_conversas.py
```

O comando grava em `dados/` ao lado do script. Ele baixa os exemplos da Doist, percorre as mensagens públicas do Zulip e verifica o acesso aos anexos referenciados. Se interromper com `Ctrl+C` ou alguma etapa falhar, rode o mesmo comando para retomar. Use `--amostra` para baixar somente os exemplos selecionados originalmente.

## Abrir os dados

- **Doist**. Abra `dados/doist/index.html` no navegador após a coleta. O [inventário de fontes](fontes/doist.json) já lista as publicações, as seções, a evidência e os links para os originais.
- **Zulip**. Rode `python .\ler_zulip.py` e abra [o leitor local](http://127.0.0.1:8765/). Escolha um canal e um tópico. Cada mensagem mostra o corpo original, o autor, a data UTC e o link para o Zulip. `Ctrl+C` fecha o leitor.
- **Piloto do Zulip**. Se você tem a cópia local do piloto, use `python .\ler_zulip.py --dados .\dados\zulip-piloto` para explorar as mensagens já baixadas durante o teste.

A coleta integral do Zulip gera `dados/zulip/mensagens.jsonl`, `canais.json`, `coleta.json`, `anexos.jsonl` e `anexos-resumo.json`. `coleta.json` registra o limite UTC e o maior ID do primeiro lote, a sequência de páginas, o total, o intervalo e `history_limited`. `canais.json` compara o inventário público com os canais observados. `coleta.sqlite3` guarda o checkpoint e alimenta o leitor. O comando retorna código 3 quando o JSONL foi exportado e o relatório tem ressalvas de cobertura.

## Cobertura

O Zulip percorre `chat.zulip.org` desde a primeira página de `channels=web-public` até o servidor confirmar `found_oldest`. Arquivamento, mudanças de visibilidade, exclusões e limites de retenção podem afetar o histórico que o servidor disponibiliza. A sequência de páginas comprova o histórico público retornado durante a execução até o limite registrado. Lacunas numéricas de ID são esperadas. [Acesso público do Zulip](https://zulip.com/help/public-access-option) · [API de mensagens](https://zulip.com/api/get-messages)

O inventário de anexos reúne URLs de uploads do próprio Zulip citadas nas mensagens. Ele registra a disponibilidade anônima de cada URL no momento da consulta e guarda as referências às mensagens. Os arquivos dos anexos ficam no Zulip.

O inventário da Doist registra 71 endereços e referências, incluindo os 49 endereços do sitemap do Async Newsletter. Das 105 candidatas, 46 capturas distintas de 17 publicações foram confirmadas. A cobertura refere-se a essas capturas. Algumas páginas só expuseram prévias ou estavam indisponíveis, como o artigo “Betting Against Slack”, que retornou HTTP 404. Os critérios exigem evidência de uma troca real de trabalho ou de uma mensagem de trabalho autêntica. Exemplos hipotéticos, interfaces demonstrativas e itens de origem incerta ficam registrados com a decisão de cobertura. [Artigo do Twist](https://async.twist.com/when-to-take-real-time-meetings-async/) · [Artigo do Todoist](https://www.todoist.com/inspiration/remote-team-communication-tools)

## Verificações feitas

- **Doist**. Duas execuções baixaram 2 e depois 1 das 46 capturas. Validei os três PNGs por decodificação, tamanho e SHA-256 e conferi os links locais do índice.
- **Zulip**. Duas execuções gravaram 500 e 1.000 mensagens no piloto local (`dados/zulip-piloto/coleta.json`). O SQLite passou na verificação de integridade, e suas 1.500 mensagens coincidem com o JSONL, sem IDs duplicados. O segundo lote começou na âncora exclusiva do primeiro. O limite é o ID `2553912`, capturado em `2026-11-14T14:46:48Z`. As mensagens vão de `2026-10-15T19:49:05Z` a `2026-11-14T13:15:05Z`, em 22 dos 26 canais listados pelo cliente público.
- **Anexos**. O piloto local (`dados/zulip-piloto/anexos-resumo.json`) identificou 149 URLs. Duas consultas limitadas confirmaram 4 públicas e 3 indisponíveis, deixando 142 para depois. A extração local encontrou todas as 88 mensagens retornadas pelo filtro `has:attachment` no intervalo testado (`dados/zulip-piloto/anexos-validacao-piloto.json`).
- **Navegação**. O leitor abriu os canais do piloto e filtrou tópicos. Um tópico com 121 mensagens abriu em duas páginas, na ordem dos IDs e sem sobreposição.
- **Comando principal**. Um teste local com substitutos para os módulos conferiu a ordem das etapas, a execução a partir de outra pasta e a interrupção da etapa de anexos quando a coleta de mensagens falha.

A execução integral e a verificação de cobertura ficam para a execução manual. O piloto do Zulip ainda tem `found_oldest=false`.

## Teste sem rede

```powershell
python -B -m unittest discover -s testes -v
```

## Arquivos do projeto

O repositório inclui os scripts Python, este README, o catálogo em `fontes/doist.json` e os testes com dados sintéticos. O catálogo contém links, títulos e descrições próprias. A cópia local completa do inventário, com as legendas originais, fica em `dados/doist/inventario.json`.

O Git ignora `dados/` e os caches do Python. A amostra, as capturas, o JSONL com mensagens e autores, os inventários de anexos, os relatórios e os checkpoints ficam na cópia local. A autorização para redistribuir esses materiais ainda precisa ser verificada. Os termos do Todoist reservam direitos sobre conteúdo editorial e gráfico. Os termos do Zulip preservam os direitos dos autores e citam um espelho público aprovado pelos responsáveis pela organização como exemplo de redistribuição. [Termos do Todoist, seções 8 e 10](https://www.todoist.com/terms-of-service) · [Termos do Zulip](https://zulip.com/policies/terms)
