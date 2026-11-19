# Plano de curadoria e busca da wiki

O aluno pede um exemplo em português ou em inglês. O agente segue as instruções da skill para buscar o exemplo pelo MCP, conferir a conversa e citar a fonte. Quando o aluno pedir para guardar o exemplo, o agente salva a referência no caderno pelo MCP. Essas ações devem funcionar offline com o texto da wiki.

## Ponto de partida

O plugin 0.3.0 usa `search_graph` para buscar mensagens do Zulip e capturas da Doist. No grafo, 31 fontes têm pelo menos uma ligação `curado`. Outras 26.674 têm apenas ligações `candidato`. Uma ligação `curado` indica que o trecho foi conferido para aquele uso didático.

O pacote em `plugins/ingles-para-o-trabalho/acervo/` contém as transcrições das 46 capturas da Doist, as conversas do Zulip, 28.455 páginas de anexos, os índices e o grafo. A wiki também tem 16 páginas didáticas. A edição inclui 1.816 transcrições já revisadas. A revisão visual em massa está pausada. Para a curadoria na nuvem, basta o texto disponível no repositório.

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
| Anexos | O nome do arquivo, a transcrição disponível e a mensagem de origem. Mesmo sem transcrição, o agente pode localizar o anexo pelo nome ou a partir da mensagem que o menciona. Se a frase de estudo aparecer nessa mensagem, o agente cita a mensagem como fonte. |
| Material didático | O conteúdo dos guias, dos casos e das comparações de formulações. |
| Índices e catálogos | O nome e a função de cada índice ou catálogo. |

1. Implemente a busca com filtros por tipo de material, fonte, tema, situação, texto e estado da curadoria.
2. Indique o que gerou cada resultado (texto, contexto, nome do arquivo ou rótulo).
3. Identifique o material didático escrito pelo projeto.
4. Registre a qualidade da transcrição em um campo próprio. O estado da curadoria indica o uso didático conferido.
5. Retorne cada ocorrência uma vez, com ID estável, tipo de material, título, trecho, página local e vínculo com a fonte quando houver. Na busca de exemplos, reúna as correspondências que apontam para a mesma frase da mesma mensagem.
6. Permita abrir a página local de cada resultado.
7. Permita salvar a referência do resultado no caderno.
8. Atualize a busca quando uma página mudar ou for removida.

### Conferir a busca offline

Use a wiki restaurada no checkout da nuvem. Para os testes de salvamento, aponte `INGLEST_NOTEBOOK_DIR` para o caderno temporário do teste antes de iniciar o MCP.

1. Busque uma expressão que apareça apenas na transcrição de um anexo.
2. Busque outra expressão que apareça apenas em uma página didática.
3. Abra a página local de cada resultado.
4. Siga o vínculo local do anexo até a mensagem de origem.
5. Salve cada referência no caderno.
6. Reabra cada referência pelo caderno.

## 3. Refinar a busca na conversa

Atualize a instrução [Consultar uma fonte](plugins/ingles-para-o-trabalho/skills/revisar-caderno/SKILL.md#consultar-uma-fonte), usada pelas três skills, para orientar o agente a usar a busca ampliada do MCP. O agente faz as tentativas a partir do pedido do aluno. Todas as consultas devem respeitar as restrições do aluno, como “só Doist” ou “só exemplos conferidos”.

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

Nos testes, confira as chamadas ao MCP, os filtros e o ID escolhido. Em caso de falha, mostre a consulta e o resultado na saída do teste.

## 4. Fazer a curadoria de todo o acervo

1. Identifique cada item por tipo e ID estável a partir das páginas, índices e catálogos existentes. Inclua todas as capturas da Doist, cada mensagem e cada tópico do Zulip, todos os anexos, as páginas didáticas e os próprios índices e catálogos, inclusive os itens sem rótulo no grafo.
2. Avalie cada item com o texto e o contexto disponíveis. Para as capturas da Doist, aproveite a análise didática existente quando ela corresponder ao ID. Para anexos com transcrição parcial, use apenas o trecho legível.
3. Registre uma decisão para cada ID conforme a tabela abaixo. Para um anexo sem texto, a mensagem de origem pode justificar seu uso como material de apoio.
4. Associe cada exemplo conferido aos temas e às situações que o trecho sustenta. Para mensagens e capturas, registre as ligações em [curadoria.json](wiki/curadoria.json). Nos anexos, diferencie o que se aprende com a transcrição do que se aprende com a mensagem de origem.
5. Agrupe os exemplos conferidos por situação e função da frase. Em uma negociação de prazo, por exemplo, distinga o pedido, a contraproposta, a recusa e a confirmação.
6. Teste a seleção de exemplos com pedidos que representem as situações de trabalho. Confira o trecho escolhido e seu contexto. O teste termina antes da geração de uma aula.

| Decisão | O que registrar |
| --- | --- |
| Exemplo conferido | A referência ao trecho da página de origem que demonstra o uso do inglês no contexto. |
| Material de apoio | Uma função curta, como “localizar uma fonte”. Reutilize o termo para itens com a mesma função. |
| Sem uso didático identificado | Um motivo curto, como “texto insuficiente”. Acrescente um detalhe apenas quando ele explicar a decisão. |

### Conferir a cobertura da curadoria

1. Compare os IDs avaliados com os IDs do inventário completo, por tipo de material. Cada mensagem precisa de uma decisão própria, mesmo quando o tópico já foi avaliado.
2. Informe os totais por tipo de material e por decisão.
3. Conte os exemplos conferidos por situação.

A curadoria termina quando cada ID do inventário tem uma decisão registrada e o total de IDs pendentes é zero.

## 5. Integrar a curadoria à wiki existente

1. Vincule cada decisão de curadoria ao ID do item na wiki. As transcrições e as conversas permanecem nas páginas em que já estão.
2. Atualize os índices e o grafo existentes com essas decisões. A busca geral cobre todo o acervo. O filtro de exemplos conferidos abre as mesmas páginas pelo ID.
3. Garanta que um clone novo recupere a curadoria junto com a wiki pelo procedimento de preparo da etapa 1.
4. Confira se o mesmo exemplo tem o mesmo ID e abre a mesma página na busca geral e na busca com o filtro de exemplos conferidos.
5. Execute os testes de [busca offline](#conferir-a-busca-offline), incluindo a reabertura da referência pelo caderno.

### Manter os originais na máquina da coleta

Mantenha os arquivos originais em `dados/`. A regra `/dados/` do [.gitignore](.gitignore) mantém essa pasta fora do índice do Git.
