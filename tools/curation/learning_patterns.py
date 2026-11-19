import re


_DIA = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|tomorrow|today)"
_HORA = r"(?:noon|lunchtime|(?:the\s+)?end\s+of\s+(?:the\s+)?day|\d{1,2}(?::\d{2})?\s*(?:am|pm))"
_APOSTROFO = r"['’]"

_SITUACOES = (
    ("pedir-atualizacao", r"""
        \b(?:any\s+(?:updates|news)|do\s+we\s+have\s+an\s+update)\s+(?:on|about)\b
        |\b(?:are\s+we|is\s+it)\s+(?:still\s+)?on\s+track\b
        |\b(?:just\s+)?check(?:ing)?\s+in\s+(?:on|about|if|to\s+see)\b
        |\b(?:could|can)\s+you\s+(?:share|send|give\s+(?:me|us))\s+(?:a\s+quick\s+|an?\s+)?(?:status\s+)?update\b
        |\bhow(?:'s|’s|\s+is)\s+(?:it|the\s+(?:work|draft|review|project|release))\s+going\b
    """),
    ("negociar-prazo", rf"""
        \b(?:can|could|shall)\s+we\s+(?:move|push|extend|bring\s+forward)\s+
             (?:(?:the|our|this)\s+)?(?:deadline|due\s+date|(?:release|publish(?:ing)?)\s+date)\b
        |\b(?:can|could)\s+we\s+do\s+{_DIA}\s+instead(?:\s+of\s+{_DIA})?\b
        |\b(?:can|could|would)\s+(?:you|we)\s+(?:do|manage|aim\s+for)\s+{_DIA}\s+(?:instead|rather)\b
        |\b(?:need|could\s+use)\s+(?:a\s+bit\s+more\s+time|another\s+(?:day|week))\s+to\b
        |\bwould\s+{_DIA}\s+work(?:\s+for\s+you)?\b
    """),
    ("dar-feedback", r"""
        \b(?:it|this|that)\s+would\s+be\s+(?:clearer|easier\s+to\s+read)\s+(?:if|to)\b
        |\bmy\s+suggestion\s+(?:is|would\s+be)\s+to\b
        |\b(?:looks|sounds)\s+good\s+to\s+me\b
        |\bsounds\s+like\s+a\s+good\s+(?:(?:easy|first|next)\s+)?step\b
        |\b(?:add(?:ing)?|includ(?:e|ing))\s+[^.\r\n!?\x00]{3,50}\s+would\s+be\s+helpful\b
    """),
    ("confirmar-proximos-passos", rf"""
        \b(?:the\s+)?next\s+steps?\s+(?:is|are|will\s+be)\b
        |(?:\bI(?:{_APOSTROFO}ll|\s+will)|(?:^[ \t]*|(?<=[.!?]\x20))will)\s+open\s+(?:a|the)\s+PR\b
        |\bI{_APOSTROFO}ll\s+(?:take\s+(?:this\s+one|care\s+of\s+that)|follow\s+up)\b
        |\b(?:I{_APOSTROFO}ll|I\s+will)\s+(?:send|share|check|review|update|confirm)\s+
              [^.!?\r\n\x00]{{1,48}}?\b(?:by|on|at)\s+(?:{_DIA}|{_HORA})\b
        |\blet{_APOSTROFO}s\s+(?:leave|keep)\s+(?:it|this|the\s+(?:issue|ticket))\s+open\s+(?:for\s+now|until)\b
    """),
    ("se-apresentar", rf"""
        \bI(?:{_APOSTROFO}m|\s+am)\s+new\s+(?:here|to\s+(?:the|this)\s+(?:team|project|community))\b
        |\bmy\s+name\s+is\s+(?-i:[A-Z][a-z]+)(?:\s+(?-i:[A-Z][a-z]+))?\b
        |\bI(?:{_APOSTROFO}m|\s+am)\s+(?-i:[A-Z][a-z]+)\s+from\s+the\s+[a-z]+(?:\s+[a-z]+)?\s+team\b
        |\bI(?:{_APOSTROFO}ve|\s+have)\s+just\s+joined\s+(?:the|this)\s+(?:[a-z]+\s+)?(?:team|project|community)\b
    """),
    ("pedir-ajuda", r"""
        \b(?:could|can)\s+(?:you|anyone|someone)\s+help\s+(?:me|us)\s+(?:with|figure\s+out|understand)\b
        |\bI\s+could\s+use\s+(?:some|a\s+bit\s+of)\s+help\s+with\b
        |\bI\s+need\s+(?:a\s+bit\s+of|some)\s+help\s+with\b
        |\bwould\s+you\s+be\s+able\s+to\s+help\s+(?:me|us)\s+with\b
    """),
    ("esclarecer", r"""
        \b(?:could|can)\s+you\s+clarify\s+[^.!?\r\n\x00]{2,60}
        |\b(?:do|did)\s+you\s+mean\s+[^.!?\r\n\x00]{2,60}\?
        |\bjust\s+to\s+(?:clarify|make\s+sure\s+I\s+understand)\b
        |\bif\s+I\s+understand\s+(?:correctly|you\s+correctly)\b
        |\bwhat\s+do\s+you\s+mean\s+by\s+[^.!?\r\n\x00]{2,60}
    """),
    ("comunicar-risco", rf"""
        \bthere(?:{_APOSTROFO}s|\s+is)\s+a\s+risk\s+(?:that|of)\b
        |\b(?:may|might|could)\s+miss\s+(?:the|our|this)\s+deadline\b
        |\bthis\s+could\s+(?:delay|block)\s+(?:the|our|this)\s+(?:release|launch|review|delivery|rollout)\b
        |\b(?:we|I)\s+(?:may|might)\s+not\s+be\s+able\s+to\s+(?:ship|publish|deliver|finish|meet)\b
        |\bif\s+[^.!?\r\n\x00]{{4,45}},\s*we\s+(?:may|might)\s+have\s+to\s+(?:delay|postpone)\b
    """),
)

_TEMAS = (
    (("gramatica", "dia-a-dia"), r"\bready\s+for\s+(?:review|feedback)\b"),
    (("phrasal-verbs", "linguagem-informal"), r"\bbump(?:ing)?\s+it\s+up\s+a\s+bit\b"),
    ("gramatica", rf"""
        \b(?:could\s+you\s+(?:let\s+(?:me|us)\s+know|tell\s+(?:me|us)|confirm)|do\s+you\s+know)\s+
           (?:whether|if|when|what|where|how)\b
        |\bit\s+would\s+(?:help|be\s+(?:helpful|clearer))\s+if\s+(?:we|you|they|it)\s+[a-z]+\b
        |\b(?:we|I)\s+should\s+(?:probably\s+)?(?:add|change|check|confirm|mention|review|update)\s+(?:it|this|the)\b
        |\bready\s+(?:to\s+(?:be\s+(?:reviewed|published)|send|publish|ship|share)|for\s+publication)\b
        |^[ \t]*(?:reviewing|adding|changing|keeping)\s+[^.!?\r\n\x00]{{3,40}}\s+
            (?:takes|makes|helps|sounds)\b
    """),
    ("conversacao", rf"""
        \bi\s+see\s+your\s+point\b
        |\bwhat\s+do\s+you\s+think\s+(?:of|about)\b
        |\bhow\s+does\s+that\s+sound\b
        |\blet\s+me\s+know\s+what\s+works\s+for\s+you\b
        |\blet\s+me\s+know\s+if\s+there{_APOSTROFO}s\s+anything\s+I\s+can\s+help\s+with\b
    """),
    ("vocabulario", r"""
        \b(?:first|second|final|rough)\s+draft\b
        |\b(?:meet|miss|extend|move|push\s+back)\s+(?:the|our|this)\s+deadline\b
        |\b(?:still|back)\s+on\s+track\b
        |\b(?:give|share|get|some|any)\s+(?:me\s+|us\s+)?(?:some\s+)?feedback\s+on\b
        |\b(?:open|submit|merge|review)\s+(?:a|the|this)\s+(?:PR|pull\s+request)\b
    """),
    ("phrasal-verbs", r"""
        \bsend\s+(?:(?:it|them|the\s+(?:update|report|briefing|newsletter))\s+out|out\s+(?:the|an?)\s+(?:update|report|briefing|newsletter))\b
        |\bcheck\s+out\s+(?:the|this|a|an)\s+(?:new\s+|updated\s+|Twist\s+)?(?:intro(?:duction)?|draft|layout|proposal|screenshot|slides)\b
        |\bbump(?:ing)?\s+(?:it|the\s+(?:limit|contrast|opacity|value|version))\s+up\b
        |\bget\s+back\s+(?:to\s+(?:you|me|us|them)|with\s+(?:a|an|the|our)\s+(?:proposal|estimate|update|answer))\b
        |\b(?:look\s+into|follow\s+up\s+on)\s+(?:it|this|that|the\s+(?:issue|report|request))\b
    """),
    ("linguagem-informal", r"""
        \b(?:FYI|BTW)\b
        |\bno\s+worries\b
        |\bquick\s+heads[ -]up\b
        |^[ \t]*(?:yeah(?=[,\s.!?])|cheers(?=[,.!\s]|$))
    """),
    ("dia-a-dia", r"""
        \b(?:I\s+can|happy\s+to)\s+help\s+with\s+(?:the|this|that)\b
        |\bthanks\s+for\s+(?:the\s+update|checking)\b
        |\b(?:could|can)\s+you\s+(?:share|send)\s+(?:me\s+)?the\s+(?:draft|slides|agenda|figures)\b
    """),
    ("pronuncia", r"""
        \bhow\s+(?:to|do\s+you|should\s+I|would\s+you)\s+pronounce\s+[^.!?\r\n\x00]{1,40}
        |\bhow\s+is\s+[^.!?\r\n\x00]{1,35}\s+pronounced\b
        |\bpronunciation\s+(?:of|guide|example|dictionary)\b
        |\b(?:stress\s+the|stress\s+falls\s+on\s+the)\s+(?:first|second|third|last|final)\s+syllable\b
    """),
)

_MASCARA_MARKDOWN = re.compile(
    r"^[ \t]*(?P<fence>\x60{3,}|~{3,})[^\r\n]*\r?\n[\s\S]*?"
    r"(?:^[ \t]*(?P=fence)[\x60~]*[ \t]*\r?(?=\n|\Z)|\Z)"
    r"|^[ \t]*>[^\r\n]*"
    r"|(?P<code>\x60+)[^\r\n]*?(?P=code)"
    r"|<(?P<tag>blockquote|pre|code)\b[^>]*>[\s\S]*?</(?P=tag)\s*>"
    r"|https?://[^\s<>]+",
    re.IGNORECASE | re.MULTILINE,
)


def _compile_patterns(regras):
    alternativas = (f"(?P<r{i}>{expressao}\n)" for i, (_, expressao) in enumerate(regras))
    return re.compile(r"(?=\b|^)(?:" + "|".join(alternativas) + ")", re.IGNORECASE | re.MULTILINE | re.VERBOSE)


_PADRAO_SITUACOES = _compile_patterns(_SITUACOES)
_PADRAO_TEMAS = _compile_patterns(_TEMAS)


def classify(texto: str) -> list[tuple[str, str]]:
    corpo = texto
    if "\x60" in corpo or ">" in corpo or "~~~" in corpo or "http" in corpo:
        corpo = _MASCARA_MARKDOWN.sub(lambda match: "\x00" + "\n" * match[0].count("\n"), corpo)

    acertos = {}
    for regras, padrao in ((_SITUACOES, _PADRAO_SITUACOES), (_TEMAS, _PADRAO_TEMAS)):
        for trecho in padrao.finditer(corpo):
            rotulo = regras[int(trecho.lastgroup[1:])][0]
            slugs = (rotulo,) if isinstance(rotulo, str) else rotulo
            evid = (trecho.start(), trecho[0].strip()[:120])
            if regras is _SITUACOES:
                slugs = (*slugs, "dia-a-dia", "conversacao")
            for slug in slugs:
                if slug not in acertos or evid[0] < acertos[slug][0]:
                    acertos[slug] = evid

    return [(slug, trecho) for slug, (_, trecho) in sorted(acertos.items(), key=lambda item: (item[1][0], item[0]))]
