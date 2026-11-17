---
title: "Zulip: comunicar risco e esclarecer o que foi entendido"
kind: topic
tags: [zulip, riscos, perguntas, esclarecimento]
learning_uses: [comunicar-risco, esclarecer, gramatica, conversacao]
learning_by_source:
  zulip-msg-1327548: [comunicar-risco, gramatica]
  zulip-msg-2531120: [comunicar-risco, dar-feedback]
  zulip-msg-1143250: [esclarecer, gramatica]
  zulip-msg-1203947: [esclarecer, pedir-ajuda]
sources: [zulip-msg-1326659, zulip-msg-1326912, zulip-msg-1326943, zulip-msg-1327540, zulip-msg-1327548, zulip-msg-2530004, zulip-msg-2530135, zulip-msg-2531120, zulip-msg-1143250, zulip-msg-1143749, zulip-msg-1203590, zulip-msg-1203947, zulip-msg-1203948, zulip-msg-1203977, zulip-msg-1204058, zulip-msg-1204059]
---

# Zulip: comunicar risco e esclarecer o que foi entendido

[Índice](../index.md) · [Conversas do Zulip](zulip.md) · [Situações de trabalho](../situacoes.md)

<a id="zulip-msg-1327548"></a>
## Dizer o que pode falhar e em que condição

**backend, fevereiro de 2022.** Ao revisar uma mudança, uma pessoa encontra dados de autoria ausentes em emojis personalizados importados do Slack. Outra abre uma proposta de correção. Surge uma sugestão de teste, seguida de uma pergunta sobre se esse código pode receber o mesmo tratamento de rotinas verificadas manualmente. A última resposta admite essa possibilidade se o código chamado estiver bem testado e aponta uma condição em que o comportamento pode quebrar. O tópico não confirma a decisão sobre o teste. [Problema 1326659](../local/zulip/canal-3/zulip-topico-3bddea53f8ad3a38257c0a0a.md#zulip-msg-1326659) · [Proposta 1326912](../local/zulip/canal-3/zulip-topico-3bddea53f8ad3a38257c0a0a.md#zulip-msg-1326912) · [Teste 1326943](../local/zulip/canal-3/zulip-topico-3bddea53f8ad3a38257c0a0a.md#zulip-msg-1326943) · [Pergunta 1327540](../local/zulip/canal-3/zulip-topico-3bddea53f8ad3a38257c0a0a.md#zulip-msg-1327540) · [Risco 1327548](../local/zulip/canal-3/zulip-topico-3bddea53f8ad3a38257c0a0a.md#zulip-msg-1327548)

**Original.** “that could be ok” e “this could break in a refactor”. O primeiro *could* sinaliza aceitação condicionada. O segundo apresenta um possível problema. A expressão *in a refactor* diz em que momento esse problema poderia aparecer.

**Prática.** Um relatório pode passar na conferência atual e falhar se o formato da planilha mudar. Diga qual é a condição e proponha uma verificação. **Adaptação em inglês britânico.** *This could break if the spreadsheet layout changes. Could we check it against a second template?*

<a id="zulip-msg-2531120"></a>
## Explicar o impacto de uma mudança sobre quem usa o produto

**design, setembro de 2026.** Uma pessoa pergunta se há inconveniente em copiar mensagens como Markdown quando a opção deveria entregar texto simples. Outra diz que Markdown continua legível, mas reconhece a mudança para quem espera só texto e pontuação. Uma terceira aponta que já existe uma forma de copiar Markdown e que trocar o comportamento eliminaria uma opção usada por outras pessoas. O tópico registra o risco à rotina de uso. A escolha final não aparece nele. [Pergunta 2530004](../local/zulip/canal-101/zulip-topico-61ded17f89c1d3e75bf5160c.md#zulip-msg-2530004) · [Consideração 2530135](../local/zulip/canal-101/zulip-topico-61ded17f89c1d3e75bf5160c.md#zulip-msg-2530135) · [Risco 2531120](../local/zulip/canal-101/zulip-topico-61ded17f89c1d3e75bf5160c.md#zulip-msg-2531120)

**Original.** “I'm not sure if that's a drawback” e “This could break workflows.” A primeira frase abre espaço para avaliação. A segunda identifica um possível impacto. O restante da resposta explica qual opção as pessoas perderiam.

**Prática.** A equipe quer remover uma coluna que Finanças usa. Avise sobre o impacto e diga como confirmar antes da mudança. **Adaptação em inglês britânico.** *This could affect the Finance team's monthly checks. I'll ask whether they still need the column before we remove it.*

<a id="zulip-msg-1143250"></a>
## Pedir confirmação de uma hipótese

**learning, março de 2021.** Uma pessoa pergunta se testes cujo nome começa com sublinhado são ignorados e indica um exemplo do código. No dia seguinte, a própria pessoa informa que estava confusa. O tópico termina sem enunciar a regra que motivou a pergunta. [Pergunta 1143250](../local/zulip/canal-92/zulip-topico-e1f7bb99f83664f7c0ce1f74.md#zulip-msg-1143250) · [Retorno 1143749](../local/zulip/canal-92/zulip-topico-e1f7bb99f83664f7c0ce1f74.md#zulip-msg-1143749)

**Original.** “Just to confirm” e “I was just confused.” A primeira expressão sinaliza que quem pergunta quer verificar uma interpretação. A segunda reconhece o equívoco, mas deixa a explicação de fora. Se o tópico for consultado mais tarde, vale escrever também o que você descobriu.

**Prática.** Confirme se uma revisão exclui anexos. Depois, escreva uma frase que registre o que você entendeu da resposta. **Adaptação em inglês britânico.** *Just to confirm, does the review include the attachments? Thanks. I understand we're checking the report and leaving the attachments for Friday.*

<a id="zulip-msg-1203947"></a>
## Confirmar o referente antes de orientar alguém

**production help, junho de 2021.** Uma pessoa pergunta como restaurar backups incrementais e descreve os arquivos com que está trabalhando. Quem responde confere se ela fala de um sistema específico e indica a ferramenta pertinente para esse caso. A primeira pessoa confirma o sistema e pergunta onde ler o processo. A resposta confirma a referência e sugere que a documentação do projeto poderia registrar um exemplo mais simples. O tópico mostra o encaminhamento, sem confirmar a restauração. [Pedido 1203590](../local/zulip/canal-31/zulip-topico-53fc1e5523e674a6802a2bc5.md#zulip-msg-1203590) · [Esclarecimento 1203947](../local/zulip/canal-31/zulip-topico-53fc1e5523e674a6802a2bc5.md#zulip-msg-1203947) · [Orientação 1203948](../local/zulip/canal-31/zulip-topico-53fc1e5523e674a6802a2bc5.md#zulip-msg-1203948) · [Confirmação 1203977](../local/zulip/canal-31/zulip-topico-53fc1e5523e674a6802a2bc5.md#zulip-msg-1203977) · [Retorno 1204058](../local/zulip/canal-31/zulip-topico-53fc1e5523e674a6802a2bc5.md#zulip-msg-1204058) · [Ideia para a documentação 1204059](../local/zulip/canal-31/zulip-topico-53fc1e5523e674a6802a2bc5.md#zulip-msg-1204059)

**Original.** “by incremental backups, do you mean the `wal-g` system?” A estrutura *By X, do you mean Y?* repete as palavras da outra pessoa e propõe uma interpretação concreta. Ela ajuda quando o próximo passo depende da resposta.

**Prática.** Alguém pede “the final figures”. Descubra se a pessoa quer os números do Reino Unido ou o total consolidado antes de encaminhar uma planilha. **Adaptação em inglês britânico.** *By the final figures, do you mean the UK figures or the group total?*
