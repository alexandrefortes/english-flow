# Workplace English Practice

Pratique inglês profissional com exemplos reais de comunicação escrita. As capturas publicadas pela Doist mostram pedidos, feedback e atualizações no contexto em que apareceram. Os tópicos públicos da comunidade Zulip permitem acompanhar uma discussão técnica por várias mensagens, da proposta inicial até o que foi decidido ou ficou em aberto.

## Wiki de inglês para o trabalho

Para trabalhar na nuvem, clone o repositório privado e execute `python -B preparar_nuvem.py` na raiz. O comando restaura o acervo de curadoria em `wiki/local/` e confere os hashes SHA-256. Os dados vêm do próprio checkout, sem Git LFS, downloads externos ou nova transcrição. A edição reúne texto, estados de leitura, contexto e referências. As mídias originais permanecem na máquina da coleta. Para usar o MCP, defina `INGLEST_PROJECT_DIR` como a raiz do checkout. O [plano de trabalho](PLANO.md) descreve a curadoria e as próximas mudanças na busca.

Abra o [índice da wiki](wiki/index.md) e escolha um tema ou um [caso de trabalho](wiki/conversas/index.md). As páginas mostram o que aconteceu nas trocas da Doist e do Zulip, explicam as formulações em inglês e propõem exercícios. A edição de curadoria guarda as conversas completas e o texto extraído das imagens na própria wiki.

A wiki é uma adaptação de [LLM Wiki, de Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Versionamos as páginas de estudo, os metadados de aprendizagem, os scripts e a edição de curadoria compactada em `nuvem/`. Depois de restaurá-la, copie a pasta `wiki/` inteira para estudar offline. [Gerar e usar a edição local](wiki/grafo.md) · [Incorporar novas fontes](wiki/AGENTS.md)

## Usar o plugin no Codex

O [plugin local](plugins/ingles-para-o-trabalho) lê o acervo, abre o caderno e inicia aulas, práticas e revisões. Instale as dependências no Python que o Codex usa e registre o marketplace local. Na raiz do repositório, rode:

```powershell
python -m pip install -r .\plugins\ingles-para-o-trabalho\requirements.txt
codex plugin marketplace add .
codex plugin add ingles-para-o-trabalho@workplace-english-local
```

Por padrão, o plugin usa `Inglês para o Trabalho` na sua pasta pessoal. Para usar uma coleta existente, defina `INGLEST_PROJECT_DIR` com o caminho da pasta que contém `dados` e `caderno de estudos`. Para abrir pelo app do Windows, você pode configurar a variável no seu perfil antes de reiniciar o app:

```powershell
[Environment]::SetEnvironmentVariable('INGLEST_PROJECT_DIR', (Get-Location).Path, 'User')
```

Se as aulas já estiverem em outra pasta, configure `INGLEST_NOTEBOOK_DIR` com o caminho exato do caderno. Isso permite usar os dados deste repositório com as aulas que você já salvou. O caderno na raiz deste repositório fica em uma pasta ignorada pelo Git.

Com a edição completa em `wiki/local/` dentro de `INGLEST_PROJECT_DIR`, peça ao plugin “Busque exemplos conferidos da Doist sobre negociar um prazo”. O MCP consulta o grafo SQLite offline. `search_graph` combina tema, situação, fonte e texto. Com `curated_only: true`, cada tema ou situação solicitado deve ter uma ligação conferida. `read_graph_node` lê o texto e as ligações pelo ID e indica a página local correspondente quando disponível. Use os IDs das mensagens e capturas para salvar a fonte no caderno. O download da amostra fornece material para as aulas mesmo sem a edição completa.

Abra uma conversa local no Codex, selecione **Inglês para o Trabalho** e peça “Abra meu caderno de estudos”. No painel, use **Baixar amostra** para começar. Os comandos da seção [Baixar e abrir a coleta](#baixar-e-abrir-a-coleta) ampliam a coleção deste checkout. O painel usa os resultados locais quando `INGLEST_PROJECT_DIR` aponta para ele.

Peça “explique em português” para uma aula expositiva, “simule uma conversa em inglês” para praticar ou “revise sem mostrar a resposta” para testar o que você lembra. O caderno salva o corpo em inglês, em Markdown com cabeçalho YAML. Para voz ao vivo, abra o controle de voz do ChatGPT. O microfone de ditado insere texto editável. Se o cliente de voz não tiver acesso ao MCP local, volte ao chat do Codex para salvar e reabrir a aula. [Voz no ChatGPT](https://help.openai.com/en/articles/20001274-chatgpt-voice)

## Começar pela amostra

No PowerShell, na raiz do repositório, use Python 3.11 ou superior e acesso à internet.

```powershell
python .\baixar_conversas.py --amostra
```

Abra `dados/fontes.md`. Ele liga três capturas da Doist e dois recortes do Zulip às fontes originais. As capturas mostram um pedido de atualização, feedback num rascunho e uma negociação de prazo. Os recortes do Zulip estão disponíveis em texto para leitura e em JSON para processamento.

## Ideias para praticar

| Exercício | Como usar a base |
| --- | --- |
| Ler para encontrar a decisão | Pegue um tópico curto do Zulip. Separe o que alguém sugeriu, o que o grupo aceitou e o que ficou em aberto. Aponte as mensagens que sustentam sua leitura. |
| Prever a próxima resposta | Leia até o primeiro pedido de ajuda ou a primeira objeção de um tópico. Escreva ou diga como você responderia. Depois, revele a resposta real e compare as duas abordagens. |
| Pedir uma atualização | Observe como a captura da Doist sobre a newsletter faz a pergunta e oferece ajuda. Adapte a estrutura para pedir o estado de uma avaliação, sugerir ajuda e combinar quando haverá uma resposta. |
| Dar feedback e discordar | Compare o feedback no rascunho da Doist com a discussão de design do Zulip. Escreva um comentário com uma observação concreta, seu impacto e uma sugestão. Faça outra versão para uma decisão mais urgente. |
| Negociar um prazo | Leia a troca sobre a imagem do Todoist e identifique o que foi pedido e o que foi confirmado. Em voz, negocie uma entrega com uma dependência incerta e termine dizendo quem fará o quê e quando. |
| Revisar uma proposta | Escolha uma conversa com duas opções técnicas. Resuma a vantagem de cada uma, diga qual prefere e explique que evidência faria você mudar de opinião. Repita em voz com uma objeção do interlocutor. |
| Comunicar um risco | Use um tópico sobre um problema técnico como ponto de partida. Escreva uma atualização de três frases com o que se sabe, o impacto possível e quando haverá nova informação. Reescreva para alguém que não leu o tópico. |
| Conduzir uma reunião | Transforme uma discussão do Zulip em uma reunião fictícia de cinco minutos. Abra com a decisão necessária, peça a opinião de duas pessoas e feche com um acordo ou uma pendência explícita. Envie um resumo por escrito. |
| Comparar registros e criar cartões | Reúna exemplos das duas fontes para a mesma ação, como fazer um pedido ou discordar. Anote para quem a frase funciona e em que contexto. No cartão, use o contexto como pergunta e tente produzir a frase antes de ver sua versão revista. |
| Usar o mesmo cenário em três modalidades | Leia um recorte, faça uma atualização oral de um minuto e escreva uma mensagem curta para quem perdeu a conversa. Compare o que precisou explicitar em cada versão. |

### Uma sessão de 20 minutos

1. Em **4 minutos**, leia um recorte e diga o que a outra pessoa precisa saber ou fazer.
2. Em **6 minutos**, faça uma primeira tentativa em voz ou por escrito. Se usar um assistente, peça que interprete o interlocutor e espere o fim da rodada para corrigir.
3. Em **5 minutos**, peça feedback sobre uma escolha de comunicação e uma escolha de inglês. Peça que cite suas frases e aponte onde o pedido, o risco ou o prazo poderia ficar mais claro. Para pronúncia, use o áudio ouvido.
4. Em **5 minutos**, repita sem consultar a resposta modelo. Mude o público, o prazo ou a objeção. Anote o que quer tentar de novo na próxima sessão.

Para a primeira rodada, use a captura `pedido-atualizacao-newsletter`. Identifique o pedido, a oferta de ajuda e quando a pessoa promete confirmar o envio. Em seguida, simule uma conversa sobre a avaliação de um modelo. Abaixo está um pedido criado para a simulação, em inglês britânico. [Publicação original da Doist](https://async.twist.com/when-to-take-real-time-meetings-async/#moving-work-forward)

> Could you let me know by Thursday lunchtime whether the evaluation is still on track for Friday? I can help with the dataset review if that's what's holding things up.

Para uma segunda rodada, leia o recorte `zulip-combinar-proximos-passos`. Identifique a mudança proposta na documentação, quem se oferece para abrir o PR e qual decisão fica em aberto. Depois, escreva o encerramento de uma discussão fictícia. [Tópico original do Zulip](https://chat.zulip.org/#narrow/channel/378-api-design/topic/events.20for.20deactivated.20channels.20and.20groups/near/2499678)

> I'll update the guidance and open a pull request by Thursday. Could we leave the issue open until we've reviewed the wording?

Mantenha o original intacto. Ao adaptar um exemplo para inglês britânico, registre o que mudou, como o vocabulário, o tom ou o contexto. Marque diálogos em voz e cenários inventados como simulações. A base mostra comunicação escrita e oferece padrões para praticar. Ela não contém gravações de fala nem descreve as práticas internas de um futuro empregador.

Para retomar em outro dia, guarde um diário pessoal fora do repositório público. Anote a data, o objetivo, a modalidade, o link e o ID da fonte, uma frase antes e depois do feedback e o próximo exercício. Comece a sessão seguinte refazendo o ponto pendente com uma variação.

## Baixar e abrir a coleta

```powershell
python .\baixar_conversas.py
```

O comando baixa as capturas elegíveis, percorre as mensagens públicas do Zulip e verifica o acesso anônimo aos anexos referenciados. Os arquivos ficam em `dados/`, ao lado do script. Se interromper com `Ctrl+C` ou uma etapa falhar, execute o mesmo comando para retomar. O código de saída `3` indica que o JSONL de mensagens foi exportado e o relatório registrou ressalvas de cobertura.

- **Doist.** Abra `dados/doist/index.html` no navegador. O índice agrupa as capturas por publicação e liga cada item à seção e ao arquivo original.
- **Zulip.** Rode `python .\ler_zulip.py` e abra [o leitor local](http://127.0.0.1:8765/). Escolha um canal e filtre pelo título do tópico. As mensagens mostram autor, data UTC, texto original e link para o Zulip. Use `Ctrl+C` para fechar o leitor.
- **Piloto do Zulip.** Se tiver a cópia local do piloto, abra com `python .\ler_zulip.py --dados .\dados\zulip-piloto`. Para criar uma coleta pequena nessa pasta, use `python .\baixar_zulip.py --diretorio .\dados\zulip-piloto --max-paginas 2 --exportar-piloto`. O limite vale por execução.

## Estrutura dos dados

O Git contém o catálogo [`fontes/doist.json`](fontes/doist.json), os scripts e os testes com dados sintéticos. A pasta `dados/` é ignorada pelo Git. Os arquivos aparecem conforme a etapa da coleta.

### Doist

| Arquivo | Estrutura e conteúdo |
| --- | --- |
| `fontes/doist.json` | Catálogo versionado. Inclui `data_da_verificacao`, `escopo`, `cobertura`, `criterios`, `sitemap`, `publicacoes`, `itens` e `contagem`. |
| `dados/doist/capturas/<id>.<ext>` | Uma imagem por item elegível baixado. O nome vem do campo `id` do catálogo. O coletor aceita PNG, JPEG e WebP. O texto original está na imagem. |
| `dados/doist/coleta.json` | Registro de downloads, indexado pelo `id` da captura. Cada entrada guarda `url_original`, `data_utc` e `estado`. Em caso de sucesso, guarda também `arquivo`, `bytes` e `sha256`. Em caso de falha, guarda `erro`. |
| `dados/doist/index.html` | Índice gerado a partir do catálogo e dos downloads locais. Mostra capturas disponíveis, itens sem download e referências examinadas. |
| `dados/doist/inventario.json` | Cópia expandida do inventário original, quando presente no checkout. Inclui legendas de origem e, onde disponível, o nome de arquivo usado no inventário. O coletor usa o catálogo versionado e não gera essa cópia. |

Em `publicacoes`, cada entrada guarda URL, endereço consultado, título, data de publicação, estado e nota. Em `itens`, cada entrada tem `id`, `titulo`, `publicacao`, `secao`, `url_secao`, `url_original`, `equipe`, `estado` e `evidencia`. Alguns itens apontam para uma `republicacao_integral`. Ligue `itens[].publicacao` a `publicacoes[].url` para recuperar os dados do artigo.

O catálogo registra 71 endereços e referências, incluindo 49 do sitemap do Async Newsletter. Das 105 capturas candidatas, 46 capturas distintas de 17 publicações foram consideradas elegíveis. `estado` e `evidencia` registram por que um item entrou ou ficou de fora, incluindo duplicatas, exemplos ilustrativos e origem incerta. Algumas páginas estavam indisponíveis ou só exibiam prévias.

### Zulip

| Arquivo em `dados/zulip/` | Estrutura e conteúdo |
| --- | --- |
| `coleta.sqlite3` | Banco de retomada e fonte do leitor local. A tabela `mensagens` usa `id` como chave e tem índice por `stream_id`, `topic` e `id`. A tabela `paginas` guarda âncora, horário da coleta, limites de IDs, contagens e sinalizadores da API. |
| `mensagens.jsonl` | UTF-8, um objeto JSON por linha, em ordem decrescente de `id`. É exportado ao chegar ao início retornado pela API ou ao usar `--exportar-piloto`. Leia linha a linha. |
| `inventario-inicial.json` | Retrato dos canais públicos no começo da execução. Inclui endpoint, horário UTC, versão do servidor e metadados dos canais. |
| `canais.json` | Uma entrada por canal encontrado nos inventários ou nas mensagens. Inclui ID, nome, contagens de mensagens e tópicos, datas extremas, estado de arquivamento quando disponível e a comparação do menor ID observado com o `first_message_id` da API. |
| `coleta.json` | Relatório com filtro, limite da coleta, datas, totais, sequência de páginas, SHA-256 do JSONL quando exportado e lista de ressalvas em `issues`. |
| `erro.json` | Horário UTC e último erro registrado pelo coletor, quando há falha ou interrupção capturada. |
| `anexos.sqlite3` | Cache de verificações por URL. Permite retomar a etapa de anexos. |
| `anexos.jsonl` | Um objeto por URL de upload do Zulip citada no JSONL, com `url`, referências em `mensagens` e `status`. Quando houve consulta, inclui código HTTP, horário UTC e outros metadados da verificação. |
| `anexos-resumo.json` | Hash e contagem do JSONL de origem, número de URLs e referências, totais por estado e pendências. |

Cada registro de `mensagens.jsonl` tem os mesmos campos da tabela `mensagens`.

| Campos | Significado |
| --- | --- |
| `id` | ID numérico da mensagem no Zulip. |
| `stream_id`, `channel`, `topic` | ID e nome do canal, e título do tópico. O título pode ser vazio. Use `stream_id` e `topic` juntos para localizar a conversa. |
| `content` | Corpo em Markdown bruto, que pode incluir menções, citações, código e links. |
| `sender_id`, `sender_full_name` | ID e nome público do autor conforme retornados pela API. |
| `timestamp`, `datetime_utc` | O mesmo instante de envio em segundos Unix e em texto UTC. |
| `url` | Link direto para a mensagem original. |

Em `anexos.jsonl`, cada referência dentro de `mensagens` contém `id`, `stream_id`, `channel`, `topic` e `url` da mensagem que citou o upload. Os estados possíveis são `publico`, `indisponivel`, `sem_acesso_anonimo`, `pendente` e `nao_verificado`. Os arquivos dos anexos ficam no Zulip.

Na amostra, os arquivos `dados/zulip-*.json` usam outro formato. Cada arquivo contém `fonte`, `topico` e uma lista `mensagens` com `id`, `autor`, `data_utc` e `texto`. Os arquivos `.txt` apresentam os mesmos recortes para leitura. O piloto em `dados/zulip-piloto/` usa a estrutura da coleta maior.

## Cobertura e verificações

A coleta do Zulip usa o filtro `channels=web-public` em `chat.zulip.org`. `cutoff_utc` e `cutoff_id` identificam o corte do primeiro lote. `found_oldest` indica que a API chegou ao início do histórico retornado pelo filtro. Consulte também `page_chain_verified`, `coverage_verified` e `issues`. Arquivamento, mudanças de visibilidade, exclusões e retenção podem afetar o histórico retornado. Lacunas numéricas de ID são esperadas. [Acesso público do Zulip](https://zulip.com/help/public-access-option) · [API de mensagens](https://zulip.com/api/get-messages)

Na coleta de 14 de novembro de 2026, as 46 capturas elegíveis da Doist estavam disponíveis. O piloto do Zulip reuniu 1.500 mensagens em 22 canais. A execução maior exportou 493.370 mensagens em 26 canais, de dezembro de 2015 a novembro de 2026. A API confirmou `found_oldest=true` e a sequência das 494 páginas foi validada. A cobertura ficou com ressalva porque quatro canais apresentaram diferença entre o menor ID coletado e o `first_message_id` declarado pelo servidor. Consulte os relatórios locais para o estado de sua própria coleta e dos anexos.

Consulte os termos das fontes antes de redistribuir as capturas, as mensagens ou outros materiais baixados. Ao compartilhar um exercício, prefira o link para o original e sua própria adaptação. [Termos do Todoist](https://www.todoist.com/terms-of-service) · [Termos do Zulip](https://zulip.com/policies/terms)

### Testes sem rede

```powershell
python -B -m unittest discover -s testes -v
```
