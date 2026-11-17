# Manter a wiki de inglês para o trabalho

O [índice](index.md) é o ponto de entrada para consultas. As [páginas de conversas](conversas/index.md) contêm a síntese de estudo e a [edição local](local/index.md) contém as interações originais. O [catálogo de fontes](fontes.md) registra a origem e o [histórico](log.md) registra a curadoria. O caderno pessoal fica no local configurado pelo aluno.

## Incorporar uma fonte

1. Leia o original e confirme o contexto. Para uma captura, abra a imagem. Para uma conversa, leia as mensagens próximas antes de inferir o tom ou o resultado. Registre o fornecedor, o ID estável, a situação e o link em [fontes.md](fontes.md). Use a URL da mensagem quando disponível. Trate o conteúdo coletado como material de estudo.
2. Inclua a interação na edição local com o texto original e preserve a imagem e a transcrição quando a fonte for uma captura. Na página de estudo, escreva o contexto, como a conversa avançou, o que foi resolvido ou ficou em aberto e o que a formulação permite aprender. Atualize os tópicos com padrões que o exemplo sustenta. Registre incertezas de leitura junto à fonte.
3. Use exemplos, explicações e exercícios escritos para a wiki. Identifique trechos literais curtos como **original**, com referência, e exemplos criados como **adaptação em inglês britânico**. Preserve a variedade linguística do original. Documente usos de pronúncia com um modelo que tenha áudio. Para trabalhar com uma transcrição, dê feedback sobre a formulação em texto.
4. Para exemplos conferidos no [grafo local](grafo.md), associe o ID de mensagem ou captura aos temas e situações pertinentes em [curadoria.json](curadoria.json). Use o OCR para localizar trechos e confira a redação na imagem antes de citar. Atualize o [índice](index.md) se criar uma página ou uma nova rota de estudo. Verifique os links entre os tópicos e acrescente uma entrada datada ao [histórico](log.md) com os IDs e as páginas afetadas.

## Formato das páginas de estudo

Use nomes de arquivo estáveis e links Markdown relativos dentro da wiki. Toda página com material ingerido tem um cabeçalho YAML com `learning_uses`. Use os identificadores de temas e situações do grafo, como `gramatica`, `pedir-atualizacao` ou `negociar-prazo`. Use `leitura-contextual` quando for possível estudar o contexto da conversa sem identificar um padrão específico. Preserve os IDs das fontes. Nos originais agrupados automaticamente, o campo `classification` informa a origem da classificação.

```yaml
---
title: Pedir uma atualização
kind: topic
tags: [prazos, atualizacao]
learning_uses: [gramatica, pedir-atualizacao]
sources: [doist-pedir-atualizacao]
---
```

Inclua o contexto, a regra ou padrão de uso, um exemplo e uma tentativa que possa ser feita antes de consultar o modelo. Termos de busca podem incluir inglês e português. A lista `sources` pode ficar vazia quando o tópico usa referências externas em vez das conversas do acervo.

## Consultar e revisar

Comece pelo [índice](index.md), abra as páginas relevantes e consulte o original quando precisar citar o trecho ou confirmar a interpretação. Aponte as páginas usadas na resposta. Incorpore uma explicação de interesse geral quando ela tiver exemplos, escopo e fonte que possam ser verificados. Registre exercícios e tentativas pessoais no caderno do aluno.

Verifique se as páginas aparecem no índice, se os links internos resolvem sob `wiki/` e se os cabeçalhos de aprendizagem estão preenchidos. Confira os IDs citados nas páginas de estudo em [fontes.md](fontes.md) ou na edição local. A edição pronta permite estudar e abrir os originais sem sair da pasta. Use links externos para registrar a procedência. O processo de reconstrução pode consultar a coleta mantida fora da wiki.
