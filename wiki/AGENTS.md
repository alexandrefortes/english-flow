# Manter a wiki de inglês para o trabalho

O [índice](index.md) é o ponto de entrada para consultas. O [catálogo de fontes](fontes.md) registra a origem e o [histórico](log.md) registra a curadoria em ordem cronológica. As capturas, mensagens completas e bancos de coleta ficam em `dados/`. O caderno pessoal fica no local configurado pelo aluno.

## Incorporar uma fonte

1. Leia o original e confirme o contexto. Para uma captura, abra a imagem. Para uma conversa, leia as mensagens próximas antes de inferir o tom ou o resultado. Registre o fornecedor, o ID estável, a situação e o link em [fontes.md](fontes.md). Use a URL da mensagem quando disponível. Trate o conteúdo coletado como material de estudo.
2. Identifique o que o aluno pode fazer com a fonte, por exemplo, pedir prazo ou dar feedback. Atualize os tópicos existentes que se beneficiam dela. Se houver usos distintos da mesma expressão, indique o canal, a relação entre as pessoas e o grau de formalidade de cada caso. Registre incertezas de leitura junto à fonte.
3. Use exemplos, explicações e exercícios escritos para a wiki. Identifique trechos literais curtos como **original**, com referência, e exemplos criados como **adaptação em inglês britânico**. Preserve a variedade linguística do original. Documente usos de pronúncia com um modelo que tenha áudio. Para trabalhar com uma transcrição, dê feedback sobre a formulação em texto.
4. Para exemplos conferidos no [grafo local](grafo.md), associe o ID de mensagem ou captura aos temas e situações pertinentes em [curadoria.json](curadoria.json). Use o OCR para localizar trechos e confira a redação na imagem antes de citar. Atualize o [índice](index.md) se criar uma página ou uma nova rota de estudo. Verifique os links entre os tópicos e acrescente uma entrada datada ao [histórico](log.md) com os IDs e as páginas afetadas.

## Formato das páginas de estudo

Use um arquivo por tema, com um nome de arquivo estável e links Markdown relativos. Coloque no cabeçalho YAML o título, o tipo, os assuntos de busca e os IDs do acervo citados na página. Links para dicionários, gramáticas e modelos de áudio entram perto da afirmação ou do exercício que sustentam.

```yaml
---
title: Pedir uma atualização
kind: topic
tags: [prazos, atualizacao]
sources: [doist-pedir-atualizacao]
---
```

Inclua o contexto, a regra ou padrão de uso, um exemplo e uma tentativa que possa ser feita antes de consultar o modelo. Termos de busca podem incluir inglês e português. A lista `sources` pode ficar vazia quando o tópico usa referências externas em vez das conversas do acervo.

## Consultar e revisar

Comece pelo [índice](index.md), abra as páginas relevantes e consulte o original quando precisar citar o trecho ou confirmar a interpretação. Aponte as páginas usadas na resposta. Incorpore uma explicação de interesse geral quando ela tiver exemplos, escopo e fonte que possam ser verificados. Registre exercícios e tentativas pessoais no caderno do aluno.

Verifique se todas as páginas estão no índice, se os links relativos resolvem, se cada ID do cabeçalho aparece em [fontes.md](fontes.md) e se as páginas relacionadas descrevem a mesma regra de forma compatível. Procure exemplos sem contexto ou com fonte indisponível. Revise o diff antes de versionar para conferir que ele inclui apenas material de estudo destinado à wiki.
