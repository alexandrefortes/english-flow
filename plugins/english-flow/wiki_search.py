from contextlib import closing
import re

from wiki_index import connect


def referencia(wiki, item):
    ancora = "#" + item["id"] if item["tipo"] == "mensagem" else ""
    return {"id": item["id"], "tipo": item["tipo"], "titulo": item["titulo"], "fonte": item["fonte"],
            "pagina_local": (wiki / item["pagina"]).as_posix() + ancora, "url": item["url"]}


def previas(db, wiki, sql, argumentos):
    return [referencia(wiki, r) for r in db.execute(sql, argumentos)]


def origens(db, wiki, item):
    if item["tipo"] == "anexo":
        return previas(db, wiki, "SELECT i.* FROM backlinks b JOIN itens i ON i.id=b.mensagem "
                       "WHERE b.anexo=? ORDER BY i.id", (item["id"],))
    if item["pai"]:
        return previas(db, wiki, "SELECT * FROM itens WHERE id=?", (item["pai"],))
    return []


def evidencias(db, chave):
    return [{"trecho": r[0], "funcao": r[1], "usos": r[2].split()}
            for r in db.execute("SELECT trecho,funcao,usos FROM evidencias WHERE id=? ORDER BY rowid", (chave,))]


def recortar(texto, expressao, tamanho=320):
    padrao = r"\s+".join(re.escape(s) for s in expressao.split())
    m = re.search(padrao, texto, re.I) if padrao else None
    inicio = max(0, m.start() - 65) if m else 0
    return texto[inicio:inicio + tamanho].strip(), inicio


def resumo(db, wiki, item):
    refs = origens(db, wiki, item)
    dados = {**referencia(wiki, item), "estado": item["estado"], "motivo": item["motivo"],
             "qualidade_transcricao": item["qualidade"], "origens": refs}
    if item["tipo"] == "anexo":
        usos = db.execute("SELECT do_texto,do_contexto FROM usos_anexo WHERE id=?", (item["id"],)).fetchone()
        dados["learning_from_text"] = usos[0].split() if usos else []
        dados["learning_from_context"] = usos[1].split() if usos else []
        if refs:
            dados["url"] = refs[0]["url"]
    return dados


def abrir(db, wiki, chave, offset=0, limit=9000):
    item = db.execute("SELECT * FROM inventario WHERE id=?", (chave,)).fetchone()
    if item is None:
        raise ValueError(f'Wiki item not found: {chave}')
    dados = resumo(db, wiki, item)
    tipo = item["tipo"]
    if tipo in ("catalogo", "indice", "guia", "topico", "didatica"):
        with (wiki / item["pagina"]).open(encoding="utf-8-sig") as pagina:
            restantes = offset
            while restantes:
                bloco = pagina.read(min(restantes, 65536))
                if not bloco:
                    break
                restantes -= len(bloco)
            trecho = pagina.read(limit + 1)
    else:
        trecho = item["texto"][offset:offset + limit + 1]
    dados.update(assinatura=item["assinatura"], texto=trecho[:limit], offset=offset,
                 next_offset=offset+limit if len(trecho) > limit else None,
                 evidencias=evidencias(db, chave) if item["estado"] == "conferido" else [])
    if tipo == "mensagem":
        dados["contexto"] = []
        for operador, ordem in (("<", "DESC"), (">", "ASC")):
            vizinhos = db.execute(f"SELECT * FROM itens WHERE pai=? AND ordem {operador} ? ORDER BY ordem {ordem} LIMIT 2",
                                  (item["pai"], item["ordem"])).fetchall()
            for vizinho in reversed(vizinhos) if operador == "<" else vizinhos:
                dados["contexto"].append({**referencia(wiki, vizinho), "trecho": vizinho["texto"][:1000]})
        dados["anexos"] = previas(db, wiki, "SELECT i.* FROM backlinks b JOIN itens i ON i.id=b.anexo "
                                  "WHERE b.mensagem=? ORDER BY i.id", (chave,))
    return dados


def filtros(kind, source, curation, topic, situation, function):
    clausulas, args = [], {}
    for campo, valor in (("tipo", kind), ("fonte", source), ("estado", curation)):
        if valor:
            clausulas.append(f"i.{campo}=:{campo}")
            args[campo] = valor
    criterios = []
    for campo, valor in (("tema", topic), ("situacao", situation), ("funcao", function)):
        if not valor:
            continue
        args[campo] = valor
        condicao = "e.funcao=:funcao" if campo == "funcao" else f"instr(' '||e.usos||' ', ' '||:{campo}||' ')"
        if function or curation == "conferido":
            criterios.append(condicao)
        else:
            clausulas.append(f"(instr(' '||i.rotulos||' ', ' '||:{campo}||' ') OR (i.estado='conferido' AND "
                             f"EXISTS (SELECT 1 FROM evidencias e WHERE e.id=i.id AND {condicao})))")
    if criterios:
        clausulas.append("(i.estado='conferido' AND EXISTS (SELECT 1 FROM evidencias e WHERE e.id=i.id AND "
                         + " AND ".join(criterios) + "))")
    return " AND ".join(clausulas) or "1", args


UPLOAD = re.compile(r"!?\[[^\]\n]*\]\((?:https?://[^/ )]+)?/user_uploads/[^)\n]+\)"
                    r"|(?:https?://[^/\s]+)?/user_uploads/[^\s)]+", re.I)


QUOTATION = re.compile(r"\[[^\]\n]+\]\(https://chat\.zulip\.org/[^)\s]*/near/(\d+)\)[:：]?[ \t]*\n"
                     r"(?:[ \t]*\n)*(`{3,}|~{3,})quote[ \t]*\n")
REFERENCE = re.compile(r"(?:#|/)((?:zulip-msg-\d+|doist-[\w-]+))(?=\)|\.md\))")


def cited_source(tipo, texto, termo):
    if tipo == "mensagem" and "/near/" in texto:
        partes = []
        for abertura in QUOTATION.finditer(texto):
            fim = re.compile(r"^" + re.escape(abertura[2]) + r"[ \t]*$", re.M).search(texto, abertura.end())
            if fim:
                partes.append((abertura.end(), fim.start(), "zulip-msg-" + abertura[1]))
        partes.sort(key=lambda parte: parte[1] - parte[0])
    elif tipo == "didatica":
        partes = []
        for linha in re.finditer(r"[^\n]+", texto):
            ids = set(REFERENCE.findall(linha[0]))
            if len(ids) == 1:
                origem = ids.pop()
                partes.extend((linha.start() + m.start(1), linha.start() + m.end(1), origem)
                              for m in re.finditer(r"“([^”]+)”", linha[0]))
    else:
        return None
    origens = set()
    for m in re.finditer(r"\s+".join(re.escape(s) for s in termo.split()), texto, re.I):
        chave = next((i for inicio, fim, i in partes if inicio <= m.start() and m.end() <= fim), None)
        if not chave:
            return None
        origens.add(chave)
    return origens.pop() if len(origens) == 1 else None


def searchable_text(campo):
    return (f"replace(CASE WHEN {campo}.tipo='mensagem' AND instr({campo}.texto,'/user_uploads/') "
            f"THEN remover_uploads({campo}.texto) ELSE {campo}.texto END,char(10),' ')")


def buscar(db, wiki, *, kind=None, source=None, topic=None, situation=None, text=None,
           curation=None, function=None, limit=10, offset=0):
    where, args = filtros(kind, source, curation, topic, situation, function)
    termo = " ".join((text or "").split())
    args.update(termo=termo, tipo_busca=kind, padrao="%" + termo.casefold().replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%",
                limite=limit+1, pular=offset)
    def contem(campo):
        if " " in termo:
            campo = f"normalizar_espacos({campo})"
        if not termo.isascii():
            campo = f"minusculas({campo})"
        return f"{campo} LIKE :padrao ESCAPE '!'"

    db.create_function("normalizar_espacos", 1, lambda s: " ".join((s or "").split()), deterministic=True)
    db.create_function("minusculas", 1, lambda campo: (campo or "").casefold(), deterministic=True)
    db.create_function("sem_links", 1, lambda campo: re.sub(r"!?\[[^\]\n]*\]\([^)\n]+\)", "", campo),
                       deterministic=True)
    db.create_function("remover_uploads", 1, lambda texto: UPLOAD.sub(" ", texto), deterministic=True)
    corpo = searchable_text("i")
    if termo:
        rotulo_automatico = contem("i.rotulos") if curation != "conferido" and not function else "0"
        rotulo_conferido = [f"({contem('e.funcao')} OR {contem('e.usos')})"]
        if curation == "conferido" or function:
            for campo in ("tema", "situacao"):
                if campo in args:
                    rotulo_conferido.append(f"instr(' '||e.usos||' ', ' '||:{campo}||' ')")
            if function:
                rotulo_conferido.append("e.funcao=:funcao")
        classe = f"""CASE
            WHEN i.tipo NOT IN ('indice','catalogo','topico') AND {contem(corpo)} THEN 'texto'
            WHEN i.tipo IN ('indice','catalogo') AND {contem("sem_links(i.texto)")} THEN 'texto'
            WHEN i.tipo='anexo' AND {contem('i.titulo')} THEN 'arquivo'
            WHEN (i.tipo!='mensagem' OR :tipo_busca='mensagem') AND
              ({contem('i.titulo')} OR (i.tipo!='mensagem' AND {contem('i.pagina')})) THEN 'contexto'
            WHEN i.tipo IN ('indice','catalogo','guia') AND {contem('i.motivo')} THEN 'contexto'
            WHEN {rotulo_automatico} OR (i.estado='conferido' AND EXISTS
              (SELECT 1 FROM evidencias e WHERE e.id=i.id AND {" AND ".join(rotulo_conferido)})) THEN 'rotulo'
            END"""
    else:
        classe = "'rotulo'" if any((topic, situation, function)) else "'contexto'"
    sql = f"""SELECT i.id, i.id AS citar, i.estado, {classe} AS via FROM inventario i WHERE {where}"""
    if not termo and (topic or situation) and not function and curation != "conferido" and kind in (None, "anexo"):
        campos = [campo for campo in ("tema", "situacao") if campo in args]
        do_texto = " AND ".join(f"instr(' '||u.do_texto||' ', ' '||:{campo}||' ')" for campo in campos)
        da_mensagem = " AND ".join(f"instr(' '||m.rotulos||' ', ' '||:{campo}||' ')" for campo in campos)
        usos_conferidos = " AND ".join(f"instr(' '||e.usos||' ', ' '||:{campo}||' ')" for campo in campos)
        conferido = ("(i.estado='conferido' AND EXISTS (SELECT 1 FROM evidencias e WHERE e.id=i.id AND "
                     + usos_conferidos + "))")
        sql += f""" AND (i.tipo!='anexo' OR {conferido} OR EXISTS (SELECT 1 FROM usos_anexo u WHERE u.id=i.id AND {do_texto}))
            UNION ALL SELECT i.id,m.id,i.estado,'rotulo' FROM inventario i JOIN usos_anexo u ON u.id=i.id
            JOIN backlinks b ON b.anexo=i.id JOIN itens m ON m.id=b.mensagem
            WHERE {where} AND NOT {conferido} AND NOT ({do_texto}) AND {da_mensagem}"""
    if termo:
        db.create_function("origem_citada", 3, cited_source, deterministic=True)
        validacao = ""
        if curation == "conferido":
            condicoes = ["e.id=coalesce(o.id,d.id)", contem("replace(e.trecho,char(10),' ')")]
            for campo in ("tema", "situacao"):
                if campo in args:
                    condicoes.append(f"instr(' '||e.usos||' ', ' '||:{campo}||' ')")
            if function:
                condicoes.append("e.funcao=:funcao")
            validacao = ("WHERE d.via!='texto' OR EXISTS (SELECT 1 FROM evidencias e JOIN inventario v ON v.id=e.id "
                         "WHERE v.estado='conferido' AND " + " AND ".join(condicoes) + ")")
        sql = f"""
            WITH diretos AS MATERIALIZED ({sql}),
            citados AS MATERIALIZED (
                SELECT d.*, CASE WHEN d.via='texto' AND i.tipo='anexo' THEN (
                    SELECT m.id FROM backlinks b JOIN itens m ON m.id=b.mensagem
                    WHERE b.anexo=i.id AND {contem(searchable_text("m"))} ORDER BY m.id LIMIT 1)
                    WHEN d.via='texto' THEN origem_citada(i.tipo,i.texto,:termo) END AS alvo
                FROM diretos d JOIN itens i ON i.id=d.id WHERE d.via IS NOT NULL
            )
            SELECT d.id,coalesce(o.id,d.id) AS citar,d.estado,
                   CASE WHEN o.id IS NULL THEN d.via ELSE 'contexto' END AS via
            FROM citados d LEFT JOIN itens o ON o.id=d.alvo AND {contem(searchable_text('o'))}
            {validacao}
        """
    if termo and kind in ("anexo", "topico"):
        vinculo = ("JOIN backlinks b ON b.anexo=i.id JOIN itens m ON m.id=b.mensagem" if kind == "anexo"
                   else "JOIN itens m ON m.pai=i.id")
        filtro_citacao = ""
        if curation == "conferido":
            filtro_citacao = (" AND EXISTS (SELECT 1 FROM inventario origem JOIN evidencias e ON e.id=origem.id "
                              "WHERE origem.id=m.id AND origem.estado='conferido' AND "
                              + " AND ".join(condicoes[1:]) + ")")
        sql += f""" UNION ALL SELECT i.id,m.id,i.estado,'contexto' FROM inventario i {vinculo}
                   WHERE {where} AND {contem(searchable_text("m"))}{filtro_citacao}"""
    query = f"""WITH achados AS ({sql}), unicos AS (
        SELECT *,row_number() OVER (PARTITION BY citar ORDER BY CASE via WHEN 'texto' THEN 0
                   WHEN 'arquivo' THEN 1 ELSE 2 END,(id=citar) DESC,id) AS n FROM achados WHERE via IS NOT NULL)
        SELECT * FROM unicos WHERE n=1 ORDER BY CASE via WHEN 'texto' THEN 0 WHEN 'arquivo' THEN 1
        WHEN 'contexto' THEN 2 ELSE 3 END, (estado='conferido') DESC,id,citar LIMIT :limite OFFSET :pular"""
    rows = db.execute(query, args).fetchall()
    matches = []
    for row in rows[:limit]:
        item = db.execute("SELECT * FROM inventario WHERE id=?", (row["id"],)).fetchone()
        citar = item if item["id"] == row["citar"] else db.execute("SELECT * FROM itens WHERE id=?", (row["citar"],)).fetchone()
        via = row["via"]
        ev = evidencias(db, item["id"]) if item["estado"] == "conferido" else []
        escolhido = next((e for e in ev if all(s in e["usos"] for s in (topic, situation) if s)
                          and (not function or e["funcao"] == function)
                          and (not termo or (via == "rotulo" and any(termo.casefold() in valor.casefold()
                               for valor in (e["funcao"], " ".join(e["usos"])))))), None)
        if via == "arquivo":
            trecho, pos = item["titulo"], 0
        elif escolhido and citar["id"] == item["id"]:
            trecho, pos = escolhido["trecho"], item["texto"].find(escolhido["trecho"])
        elif via == "rotulo" and citar["id"] != item["id"]:
            trecho, pos = recortar(citar["texto"], "")
        elif via == "rotulo":
            trecho, pos = item["rotulos"] or " ".join(e["funcao"] for e in ev), 0
        elif not termo and item["texto"]:
            trecho, pos = recortar(item["texto"], "")
        elif via == "contexto" and item == citar:
            trecho, pos = item["titulo"], 0
            if item["motivo"] and termo and termo.casefold() in item["motivo"].casefold():
                trecho = item["motivo"]
        else:
            trecho, pos = recortar(citar["texto"], termo)
        if via == "texto" and item["tipo"] == "didatica":
            texto_pagina = (wiki / item["pagina"]).read_text(encoding="utf-8-sig")
            pos += max(0, texto_pagina.find(item["texto"]))
        dados = resumo(db, wiki, item)
        dados.update(citar_id=citar["id"], trecho=trecho, correspondencia=via, offset_texto=max(0, pos))
        dados["evidencias"] = ev
        if citar["tipo"] == "mensagem":
            dados["anexos"] = [v[0] for v in db.execute("SELECT anexo FROM backlinks WHERE mensagem=?", (citar["id"],))]
        matches.append(dados)
    return {"matches": matches, "next_offset": offset + limit if len(rows) > limit else None}


def consultar(wiki, operacao, **parametros):
    with closing(connect(wiki)) as db, db:
        return operacao(db, wiki, **parametros)
