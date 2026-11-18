---
name: revisar-caderno
description: Use quando o aluno pedir para abrir o caderno, rever uma aula salva, praticar sem consulta, procurar um exemplo no acervo ou salvar uma nota.
---

## Abrir o caderno

1. Se o aluno indicar o ID de um registro, abra esse registro com `read_entry`.
2. Se o aluno pedir o caderno ou quiser escolher um registro, abra o painel com `open_notebook`.
3. Quando o aluno escolher um título, abra o registro com `read_entry`.

## Rever uma explicação

1. Para uma revisão desde a primeira aula, siga a ordem dos registros do tipo `lesson`.
2. Explique uma regra por vez em português do Brasil, salvo pedido de outro idioma.
3. Ilustre a regra com um exemplo em inglês da aula.

Se o aluno pediu apenas a explicação, encerre após o exemplo.

## Praticar sem consulta

1. Escolha a habilidade pedida ou a próxima tarefa em `Next practice` se o aluno quiser continuar.
2. Peça uma frase em inglês para uma situação nova que exija a mesma habilidade.
3. Espere a tentativa antes de mostrar a regra ou o modelo.
4. Se o aluno precisar de ajuda, dê uma pista.
5. Após a tentativa, diga se a frase comunica a intenção.
6. Explique em português a correção que mais ajuda o aluno.
7. Peça uma nova tentativa.
8. Proponha retomar a habilidade em alguns dias.

## Consultar uma fonte

1. Interprete o pedido em português ou inglês. Use `search_wiki` com a situação e os filtros pedidos. Para “mais tempo para entregar” ou “more time to finish”, procure `situation: negociar-prazo` e `function: pedido`. Prefira exemplos conferidos. Mantenha em todas as tentativas as restrições do aluno, inclusive fonte, tipo e estado.
2. Abra o resultado com `read_wiki_item`. Confira o trecho, quem fala, a mensagem anterior e a resposta quando houver. Se o exemplo satisfizer o pedido, cite-o e encerre a busca. Uma confirmação de entrega tem função diferente de um pedido de prorrogação.
3. Se faltar evidência, faça a segunda consulta com outra expressão provável em inglês, como *extend the deadline*. Se ainda faltar um exemplo, faça a terceira ampliando um filtro escolhido por você, como tema ou função. Se todos os filtros forem exigidos, preserve-os e use outra expressão. Explique a lacuna se as tentativas se esgotarem.
4. Em anexos, confira `correspondencia`, a transcrição e as `origens`. Um nome de arquivo ou rótulo pode localizar o material. Se a frase vier da conversa, abra e cite a mensagem indicada em `citar_id` ou nas origens. Em transcrições parciais, cite só as palavras legíveis e indique a lacuna quando afetar o sentido.
5. Responda no chat com o trecho literal, ID, página local e link de origem disponível. Identifique as páginas didáticas do projeto e suas adaptações em inglês britânico. Se o aluno pedir para guardar o exemplo, use `save_entry` com o ID citado em `sources`. Para rever a fonte, use `read_entry` e abra o ID com `read_wiki_item`.

Se a edição da wiki estiver indisponível, use `search_graph` e `read_graph_node` ou consulte a amostra com `list_sources` e `read_source`. Respeite os mesmos filtros. Ofereça **Baixar amostra** se faltar o acervo e use `download_sources` quando o aluno pedir.

## Salvar no caderno

Quando o aluno pedir para salvar uma revisão ou uma nota, escolha o tipo do registro pelo pedido.

| Pedido | Tipo (`kind`) | Conteúdo em inglês |
| --- | --- | --- |
| Salvar a revisão | `review` | Objetivo, observações e próxima tarefa em `Next practice`, com a data combinada, se houver. |
| Salvar uma nota | `note` | Nota pedida pelo aluno. |

1. Salve o registro com `save_entry`. O campo `sources` contém os IDs das fontes consultadas.
2. Confirme o salvamento quando a ferramenta retornar o ID do registro.
