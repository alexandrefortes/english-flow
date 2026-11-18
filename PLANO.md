# Plano de curadoria e busca da wiki

O aluno poderá pedir um exemplo em português ou em inglês, ler a conversa em que ele aparece e salvar a referência no caderno. A busca, a leitura, a citação e o acesso pelo caderno deverão funcionar offline com o texto da wiki.

## Ponto de partida

O plugin 0.3.0 usa `search_graph` para buscar mensagens do Zulip e capturas da Doist. No grafo, 31 fontes têm pelo menos uma ligação `curado`. Outras 26.674 têm apenas ligações `candidato`. Uma ligação `curado` indica que o trecho foi conferido para aquele uso didático.

O pacote em `nuvem/` contém as transcrições das 46 capturas da Doist, as conversas do Zulip, 28.455 páginas de anexos, os índices e o grafo. A wiki também tem 16 páginas didáticas. A edição inclui 1.816 transcrições já revisadas. A revisão visual em massa está pausada. Para a curadoria na nuvem, basta o texto disponível no repositório.

## 1. Preparar o trabalho na nuvem

Use Python 3.11 ou superior. Os comandos abaixo usam o terminal Linux do Codex na nuvem.

1. Abra o terminal na **pasta do projeto**. É a pasta que contém `PLANO.md` e `preparar_nuvem.py`.
2. Restaure a wiki com o comando abaixo. Ele descompacta o acervo em `wiki/local/` e verifica a integridade dos arquivos.

   ```sh
   python -B preparar_nuvem.py
   ```

3. No mesmo terminal, defina a **pasta do projeto** como o caminho que o servidor MCP deve usar. O comando abaixo grava o caminho absoluto dessa pasta na variável `INGLEST_PROJECT_DIR` para os processos iniciados nesse terminal. O MCP procura o grafo em `$INGLEST_PROJECT_DIR/wiki/local/grafo.sqlite3`.

   ```sh
   export INGLEST_PROJECT_DIR="$PWD"
   ```

### Executar os testes

1. Instale as dependências de desenvolvimento.

   ```sh
   python -m pip install -r requirements-dev.txt
   ```

2. Execute os testes de regressão. Eles usam dados sintéticos.

   ```sh
   python -B -X utf8 -m unittest discover -s testes
   ```

## 2. Ampliar a busca do MCP

Preserve as ferramentas existentes. A busca única deve cobrir os materiais abaixo.

| Material | O que a busca deve encontrar |
| --- | --- |
| Mensagens e tópicos | O trecho da conversa em que a expressão aparece. |
| Capturas da Doist | O texto da transcrição e a página local da captura. |
| Anexos | O nome e o texto extraído de imagens, GIFs, áudios, vídeos, PDFs, planilhas, código e logs. Um anexo sem texto pode ser encontrado pelo nome ou pela mensagem de origem. |
| Material didático | O conteúdo dos guias, dos casos e das comparações de formulações. |
| Índices e catálogos | O nome e a função de cada índice ou catálogo. |

1. Implemente a busca com filtros por tipo de material, fonte, tema, situação, texto e estado da curadoria.
2. Indique o que gerou cada resultado (texto, contexto ou rótulo).
3. Identifique o material didático escrito pelo projeto.
4. Registre a qualidade da transcrição em um campo próprio. O estado da curadoria indica o uso didático conferido.
5. Retorne o ID estável, o tipo de material, o título, o trecho, a página local e o vínculo com a fonte quando houver.
6. Permita abrir a página local de cada resultado.
7. Permita salvar a referência do resultado no caderno.
8. Atualize a busca quando uma página mudar ou for removida.

### Conferir a busca offline

Use uma cópia da wiki sem os arquivos originais.

1. Busque uma expressão que apareça apenas na transcrição de um anexo.
2. Busque outra expressão que apareça apenas em uma página didática.
3. Abra a página local de cada resultado.
4. Siga o vínculo local do anexo até a mensagem de origem.
5. Salve cada referência no caderno.
6. Reabra cada referência pelo caderno.

## 3. Refinar a busca na conversa

O próprio assistente faz as tentativas. Todas as consultas devem respeitar as restrições do aluno, como “só Doist” ou “só exemplos conferidos”.

1. Faça a primeira consulta com a situação e os filtros pedidos pelo aluno.
2. A cada tentativa, confira a situação no contexto do trecho. Uma palavra no nome do arquivo pode ser insuficiente.
3. Se o contexto mostrar o uso pedido, cite o trecho. Essa é a última consulta.
4. Se o resultado for insuficiente, faça uma segunda consulta com outra formulação, como uma expressão provável em inglês.
5. Se o resultado continuar insuficiente, faça uma terceira consulta com um filtro opcional mais amplo, se houver.
6. Se faltar um exemplo adequado, explique a lacuna ao aluno.

Para uma transcrição parcial, cite apenas o trecho legível. Indique a lacuna quando ela afetar o exemplo.

### Conferir as tentativas

| Caso de teste | Resultado esperado |
| --- | --- |
| A primeira consulta encontra um bom exemplo. | O assistente cita o trecho após conferir o contexto. A busca termina na primeira consulta. |
| A primeira consulta volta vazia. | O assistente reformula a consulta. |
| A expressão aparece apenas no nome do arquivo. | O assistente confere o conteúdo antes de aceitar o exemplo. |
| O aluno pede “Como peço mais tempo para entregar um relatório?” ou “How can I ask for more time to finish a report?” | Cada pedido encontra um exemplo de negociação de prazo. |

Registre as consultas de cada caso. Para cada ajuste, anote o motivo. Para cada exemplo escolhido, anote o ID.

## 4. Fazer a curadoria de todo o acervo

1. Liste cada item da wiki por tipo e ID estável. Inclua todas as capturas da Doist, cada mensagem e cada tópico do Zulip, todos os anexos, as páginas didáticas, os índices e os catálogos. A lista inclui os itens que ainda não têm rótulo no grafo.
2. Avalie cada item com o texto e o contexto disponíveis. Para as capturas da Doist, aproveite a análise didática existente quando ela corresponder ao ID. Para anexos com transcrição parcial, use apenas o trecho legível.
3. Registre uma decisão para cada ID conforme a tabela abaixo. Para um anexo sem texto, a mensagem de origem pode justificar seu uso como material de apoio.
4. Associe cada exemplo conferido aos temas e às situações que o trecho sustenta. Para mensagens e capturas, registre as ligações em [curadoria.json](wiki/curadoria.json). Nos anexos, diferencie o que se aprende com a transcrição do que se aprende com a mensagem de origem.
5. Agrupe os exemplos conferidos por situação e função da frase. Em uma negociação de prazo, por exemplo, distinga o pedido, a contraproposta, a recusa e a confirmação.
6. Teste os exemplos com pedidos de aula.

| Decisão | O que registrar |
| --- | --- |
| Exemplo conferido | O trecho que demonstra o uso do inglês no contexto. |
| Material de apoio | A função do item, como explicar uma regra, situar uma conversa ou localizar uma fonte. |
| Sem uso didático identificado | O motivo da decisão, como texto insuficiente para entender a interação. |

### Conferir a cobertura da curadoria

1. Compare os IDs avaliados com os IDs do inventário completo, por tipo de material. Cada mensagem precisa de uma decisão própria, mesmo quando o tópico já foi avaliado.
2. Informe os totais por tipo de material e por decisão.
3. Conte os exemplos conferidos por situação.

A curadoria termina quando cada ID do inventário tem uma decisão registrada e o total de IDs pendentes é zero.

## 5. Gerar a edição compacta

1. Gere a edição compacta em outra pasta com as páginas didáticas, as fontes selecionadas, o contexto das conversas e as transcrições dos anexos citados. Cada página deve manter o texto, o ID, o cabeçalho YAML, a origem e o estado da transcrição, quando aplicável.
2. Gere os índices da seleção.
3. Gere o grafo da seleção.
4. Compare o tamanho da edição compacta com o da edição completa. A referência do plano é 655 MB para a edição completa.
5. Verifique os links locais em uma cópia offline da edição compacta.
6. Repita nessa cópia os testes de [busca offline](#conferir-a-busca-offline), inclusive a reabertura das referências pelo caderno.

### Manter os originais na máquina da coleta

Mantenha os arquivos originais em `dados/`. A regra `/dados/` do [.gitignore](.gitignore) mantém essa pasta fora do índice do Git. A edição compacta usa as transcrições da wiki.
