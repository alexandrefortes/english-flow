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

**Com o grafo disponível**

1. Busque o tema ou a situação com `search_graph` e `curated_only: true`. O filtro `source` restringe a busca à fonte pedida.
2. Se faltar um resultado pertinente, consulte candidatos com `curated_only: false` apenas quando o pedido admitir candidatos.
3. Confira o trecho em contexto com `read_graph_node` antes de citá-lo.

**Se o grafo estiver indisponível**

1. Localize a fonte com `list_sources` ou, para uma expressão nas mensagens locais do Zulip, com `search_zulip`.
2. Confira o trecho em contexto com `read_source`.

Cite o trecho original com as palavras legíveis e o link de origem. Indique a lacuna quando a transcrição for parcial. Identifique os exemplos criados a partir da fonte como **adaptação em inglês britânico**.

Se nenhuma fonte estiver disponível, ofereça a amostra pelo botão **Baixar amostra**. Se o aluno pedir o download pelo chat, use `download_sources`. Se o aluno preferir continuar sem a fonte, identifique o exemplo como uma simulação.

## Salvar no caderno

Quando o aluno pedir para salvar uma revisão ou uma nota, escolha o tipo do registro pelo pedido.

| Pedido | Tipo (`kind`) | Conteúdo em inglês |
| --- | --- | --- |
| Salvar a revisão | `review` | Objetivo, observações e próxima tarefa em `Next practice`, com a data combinada, se houver. |
| Salvar uma nota | `note` | Nota pedida pelo aluno. |

1. Salve o registro com `save_entry`. O campo `sources` contém os IDs das fontes consultadas.
2. Confirme o salvamento quando a ferramenta retornar o ID do registro.
