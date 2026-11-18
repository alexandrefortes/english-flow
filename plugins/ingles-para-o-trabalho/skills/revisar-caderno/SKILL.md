---
name: revisar-caderno
description: Use para abrir o caderno, explicar aulas anteriores, praticar de memória ou consultar o acervo de inglês para o trabalho.
---

Use `open_notebook` para consultar os registros e `read_entry` para obter a aula escolhida. Se o pedido mencionar um identificador de registro, use esse registro. Explique em português do Brasil por padrão e mantenha as frases de estudo em inglês.

**Rever a explicação.** Quando o aluno pedir resumo, releitura ou explicação, recapitule a regra e mostre um exemplo. Para rever desde o início, siga a ordem das aulas. Preserve o formato expositivo quando for a preferência expressa.

**Praticar sem consultar.** Quando o aluno pedir revisão ativa, retomar uma prática ou testar a memória, siga uma pergunta por vez.

1. Escolha a aula solicitada ou a habilidade indicada no último registro pertinente, incluindo a seção `Next practice` quando houver.
2. Apresente um contexto curto e peça uma frase ou decisão em inglês. Espere a tentativa antes de mostrar a regra ou a resposta. Se o aluno travar, dê uma pista e espere antes de mostrar um modelo.
3. Diga se a resposta comunica a intenção e ofereça uma correção de maior impacto em português. Peça outra tentativa com uma pequena mudança na situação. Por exemplo, passe de confirmar um prazo com um colega a confirmá-lo com um fornecedor.
4. Proponha uma retomada em alguns dias. Ao encontrar um registro anterior pertinente, reapresente a habilidade em um contexto novo. Quando o aluno pedir para guardar a revisão, use `save_entry` com `kind: review`, objetivo e observações em inglês. Registre a próxima tarefa em `Next practice`. Inclua uma data se ela for combinada.

Para encontrar exemplos por tema ou situação, use `search_graph` com `curated_only: true`. Leia o texto e as ligações do exemplo com `read_graph_node` antes de citá-lo. Se a busca vier vazia, você pode procurar candidatos e conferir o trecho no contexto. Se a wiki estiver indisponível, consulte as fontes locais com `list_sources`, `read_source` ou `search_zulip`.

Informe o contexto e forneça o link original. Preserve as palavras da fonte e identifique separadamente as versões em inglês britânico. Para salvar uma nota, use `save_entry` com `kind: note` e conteúdo em inglês.
