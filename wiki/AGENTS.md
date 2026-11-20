# Manter a wiki de inglês para o trabalho

O [índice](index.md) é o ponto de entrada para consultas. As [páginas de conversas](conversas/index.md) contêm a síntese de estudo. A [edição em texto](local/index.md) reúne as mensagens, as transcrições e as referências aos anexos. O [catálogo de fontes](fontes.md) indica a origem dos exemplos. O caderno pessoal fica no local configurado pelo aluno.

## Incorporar uma fonte

Para avaliar um item que já está na wiki, use a página e o ID existentes. Registre o trecho literal, a função e os usos conferidos em [curadoria.json](curadoria.json). Consulte o [procedimento por ID](grafo.md#decisões-por-id) para retomar a avaliação e conferir a cobertura. As instruções abaixo se aplicam à inclusão de fontes ou à edição de páginas didáticas.

1. Confira o contexto da fonte na edição publicada. Use as mensagens próximas para interpretar uma conversa. Leia a transcrição da captura ou do anexo e confira o estado de leitura.
2. Quando a interação for nova, inclua seu texto original na edição local. Para capturas, preserve a transcrição e as incertezas de leitura. Os originais ficam na máquina da coleta.
3. Ao editar uma página didática, aproveite o exemplo que já demonstra o uso. Acrescente outro quando ele ensinar uma diferença concreta, como o efeito de trocar *by Friday* por *on Friday*. Identifique trechos literais curtos como **original**, com referência, e exemplos criados como **adaptação em inglês britânico**. Preserve a variedade linguística do original. Documente usos de pronúncia com um modelo que tenha áudio. Com uma transcrição, dê feedback sobre a formulação em texto.
4. Se uma página didática citar uma fonte que ainda falta em [fontes.md](fontes.md), acrescente ao catálogo o fornecedor, o ID, a situação e a URL de origem.
5. Atualize o [índice](index.md) quando criar uma página ou uma rota de estudo.

## Formato das páginas de estudo

Use nomes de arquivo estáveis e links Markdown relativos dentro da wiki. Toda página com material ingerido tem um cabeçalho YAML com `learning_uses`. Use os identificadores de temas e situações do grafo, como `gramatica`, `pedir-atualizacao` ou `negociar-prazo`. Use `leitura-contextual` quando for possível estudar o contexto da conversa sem identificar um padrão específico. Preserve os IDs nos nomes dos arquivos e nas âncoras das mensagens.

Nos anexos, use apenas `learning_uses`, `learning_from_text` e `learning_from_context` no YAML. Em `## backlinks`, ligue às mensagens de origem. Em `## Content`, preserve o texto extraído, inclusive erros e quebras de linha. Omita seções vazias. Guarde o método de extração e as notas de revisão no [registro de extração](local/anexos/extracao.json).

```yaml
---
title: Pedir uma atualização
kind: topic
tags: [prazos, atualizacao]
learning_uses: [gramatica, pedir-atualizacao]
sources: [doist-pedir-atualizacao]
---
```

Na página didática, explique o padrão de uso no contexto do exemplo. Inclua um exercício quando a página servir para prática. Termos de busca podem incluir inglês e português. A lista `sources` pode ficar vazia quando o tópico usa referências externas em vez das conversas do acervo.

## Consultar e revisar

Responda a consultas no chat com o trecho pertinente e a referência à página de origem. Quando o aluno pedir para salvar uma prática, revisão ou nota, use o caderno pessoal. Ao preparar material didático para a wiki, atualize a página que já trata do tema. Crie uma página quando houver um objetivo de estudo que as existentes ainda não atendem.

Verifique se as páginas aparecem no índice, se os links internos resolvem sob `wiki/` e se os cabeçalhos de aprendizagem estão preenchidos. Confira os IDs citados nas páginas de estudo em [fontes.md](fontes.md) ou na edição restaurada. Use links externos para registrar a procedência. Os arquivos originais de coleta ficam apenas na máquina coletora do mantenedor. O repositório e os pacotes distribuem a edição em texto.
