# Plano de curadoria e busca da wiki

O aluno deve poder pedir exemplos em português ou em inglês, ler a conversa em que aparecem e guardar a referência no caderno. A edição de estudo deve funcionar offline. As etapas abaixo são trabalho proposto para o Codex na nuvem.

O plugin final usa o conteúdo transcrito. Buscar, abrir, citar e salvar um exemplo deve funcionar sem o print, o áudio, o vídeo ou o documento original. A página conserva a procedência e o estado da transcrição. Quando a leitura for parcial, o assistente indica a lacuna e usa somente o texto disponível.

## Ponto de partida

O plugin 0.3.0 pesquisa mensagens do Zulip e capturas da Doist com `search_graph`. Há 31 fontes com alguma ligação `curado` e 26.674 apenas com ligações `candidato`. A wiki também reúne 28.455 páginas de anexos e 16 páginas didáticas. As 1.816 transcrições já revistas integram a edição local. A revisão visual em massa está pausada.

O repositório privado contém os scripts, os testes, o plugin, as páginas didáticas e a edição textual para curadoria em `nuvem/`. Ela restaura as transcrições das 46 capturas da Doist, as páginas do Zulip, o grafo, os índices e os vínculos em `wiki/local/`. As imagens originais, a coleta bruta, os 11,8 GB de anexos originais do Zulip, os registros de execução do OCR e o caderno pessoal permanecem na máquina de origem.

## 1. Preparar o trabalho na nuvem

Usar Python 3.11 ou superior. Na raiz do checkout, restaurar a edição e apontar o MCP para ela. Para executar os testes, instalar as dependências de desenvolvimento.

```sh
python -B preparar_nuvem.py
export INGLEST_PROJECT_DIR="$PWD"
python -m pip install -r requirements-dev.txt
python -B -X utf8 -m unittest discover -s testes
```

A curadoria usa a edição completa desde o primeiro checkout. O pacote já inclui as transcrições publicadas, inclusive as revisadas e as parciais. O campo `mascaramento` de `nuvem/acervo.json` informa em quantos arquivos e campos a exportação omitiu padrões de credencial. Os originais locais são preservados. A suíte usa dados sintéticos para os testes de regressão.

## 2. Ampliar a busca do MCP

- Oferecer uma busca única em mensagens, tópicos, capturas, anexos e material didático. Incluir guias, casos e comparações de formulações. Os índices e catálogos devem ser localizáveis por nome e função. Preservar as ferramentas existentes.
- Permitir filtros por tipo, fonte, tema, situação, texto e curadoria. Para capturas, pesquisar a transcrição e devolver a página local com sua referência de origem. Para anexos, pesquisar o nome e o texto extraído de prints, GIFs, áudios, vídeos, PDFs, planilhas, código e logs. Anexos sem texto continuam localizáveis pelo nome ou pela mensagem de origem.
- Mostrar de onde veio a correspondência: texto, contexto ou rótulo. Identificar materiais escritos pelo projeto. Manter campos próprios para a qualidade da transcrição e para a curadoria pedagógica.
- Devolver ID estável, tipo, título, trecho, página local e vínculo com a fonte. Permitir abrir o conteúdo e guardar a referência no caderno. Atualizar a busca quando uma página mudar ou sair da edição.

**Aceite.** Em um checkout sem os arquivos originais, localizar uma expressão exclusiva de um anexo e outra exclusiva de uma aula. Abrir cada resultado offline, seguir o vínculo de origem quando aplicável e reabrir a referência no caderno.

## 3. Refinar a busca na própria conversa

O assistente começa pela intenção e pelos filtros explícitos do aluno. Lê os trechos e verifica se mostram a situação pedida. Um resultado também pode ser fraco quando a palavra aparece apenas no nome do arquivo.

Se necessário, testar até duas novas consultas. Na primeira, trocar a formulação ou buscar uma expressão provável em inglês. Na segunda, ampliar um filtro opcional, como o tipo de material. Preservar exigências como “só Doist” e “só exemplos conferidos”. Ler o contexto antes de citar. Se a fonte continuar insuficiente, explicar a lacuna ao aluno.

**Aceite.** Testar uma busca vazia, outra com coincidência irrelevante e uma com bom resultado inicial. Registrar a consulta, o motivo do ajuste e o ID escolhido. A busca bem-sucedida encerra as tentativas. O próprio assistente faz o refinamento, sem iniciar outro agente.

Verificar também se “Como peço mais tempo para entregar um relatório?” e “How can I ask for more time to finish a report?” levam a exemplos de negociação de prazo. O aluno pode fazer qualquer um dos pedidos diretamente no idioma que preferir.

## 4. Ampliar a curadoria por valor didático

Começar pelas 40 capturas da Doist que já têm análise nas páginas de estudo e faltam no filtro de curadoria. Conciliar os IDs e registrar as relações sustentadas pelo texto de cada caso. Depois, agrupar os candidatos por situação e função da frase. Na negociação de prazo, por exemplo, considerar pedido, contraproposta, recusa e confirmação.

Priorizar exemplos legíveis, com contexto suficiente e que acrescentem uma formulação ou resposta. Medir a cobertura por situação e testar os exemplos com pedidos de aula. Conservar o restante para triagem futura.

## 5. Gerar a edição compacta

Gerar uma saída separada com as páginas didáticas, as fontes escolhidas, o contexto necessário e as transcrições dos anexos citados. Preservar texto, IDs e YAML. Incluir índices e grafo referentes à seleção.

Comparar o tamanho com os 655 MB da edição completa. Em uma cópia offline, verificar links, repetir as buscas de aceite e reabrir fontes do caderno. Para os originais que mais ocupam espaço, inventariar os arquivos, verificar a cópia arquivada por hash e testar a restauração. Apresentar a economia medida e o impacto de cada remoção antes de decidir o que apagar.
