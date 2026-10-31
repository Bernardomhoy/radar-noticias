# -*- coding: utf-8 -*-
"""Agente Roteirista: transforma pauta em roteiro de reels pronto para gravar.

Nao inventa fato. Tudo que entra na fala vem do material coletado (manchetes e
resumos dos veiculos) ou vai marcado como [CONFERIR: ...] para voce completar.
O que o agente faz e a engenharia de atencao: gancho, ordem dos blocos, tempo de
cada fala, texto na tela, b-roll, CTA - e travar o roteiro no tempo alvo.

Os textos de saida sao escritos em portugues acentuado, porque voce vai ler isso
na hora de gravar.
"""
from __future__ import annotations

import re

from .util import (agora_br, canonizar, entidades_seq, hash_id, limpar_html, log,
                   normalizar, parece_portugues)

_RE_PERCENT = re.compile(r"\d[\d.,]*\s?%")
_RE_DINHEIRO = re.compile(r"(?:R\$|US\$|€)\s?[\d.,]+(?:\s?(?:mil|milh[oõ]es?|bilh[oõ]es?|tri))?",
                          re.IGNORECASE)
_RE_GRANDE = re.compile(r"\b\d[\d.,]*\s?(?:mil|milh[oõ]es?|milh[aã]o|bilh[oõ]es?|bilh[aã]o)\b",
                        re.IGNORECASE)
_RE_NUM = re.compile(r"\b\d[\d.,]*\b")

VERBOS_FORTES = {
    "aprova": "aprovou", "aprovou": "aprovou", "sanciona": "sancionou", "veta": "vetou",
    "cai": "caiu", "sobe": "subiu", "dispara": "disparou", "despenca": "despencou",
    "anuncia": "anunciou", "lanca": "lançou", "confirma": "confirmou", "nega": "negou",
    "suspende": "suspendeu", "proibe": "proibiu", "libera": "liberou", "mantem": "manteve",
    "muda": "mudou", "reduz": "reduziu", "amplia": "ampliou", "adia": "adiou",
    "decide": "decidiu", "julga": "julgou", "prende": "prendeu", "demite": "demitiu",
}

# Marcadores de pendencia: frases assim sao as melhores para o bloco "em aberto".
MARCAS_PENDENCIA = ["ainda não", "ainda nao", "não há definição", "nao ha definicao",
                    "não está claro", "nao esta claro", "falta", "aguarda", "depende",
                    "deve ser definido", "sem previsão", "sem previsao", "pode ser",
                    "ainda será", "ainda sera", "não informou", "nao informou",
                    "não comentou", "nao comentou", "em análise", "em analise",
                    "expectativa", "previsto para", "próximos dias", "proximos dias"]

PONTE = {
    "economia": "o efeito disso chega na sua conta",
    "politica": "isso define regra que vale para todo mundo",
    "mundo": "parece longe, mas encosta no Brasil",
    "tecnologia": "isso muda como você usa o celular todo dia",
    "ciencia": "é o tipo de descoberta que vira política pública depois",
    "saude": "mexe com atendimento e com o que chega na farmácia",
    "esporte": "é o assunto que vai dominar a conversa hoje",
    "cultura": "é o que vai aparecer no feed de todo mundo hoje",
    "cotidiano": "pode acontecer na sua cidade também",
    "meio-ambiente": "clima virou pauta de preço de comida e de conta de luz",
    "geral": "vale entender antes de opinar",
}

TRILHA = {
    "economia": "batida seca e grave, 100-110 bpm, sem melodia — ritmo de noticiário",
    "politica": "percussão minimalista e tensa, sem virada épica",
    "mundo": "pad atmosférico baixo + percussão seca",
    "tecnologia": "eletrônica minimalista, textura de sintetizador, 110 bpm",
    "ciencia": "ambiente curioso, piano pontual",
    "saude": "neutra e discreta, volume baixo",
    "esporte": "batida energética, 120 bpm, corte no pico",
    "cultura": "a própria música do artista, se o direito permitir",
    "cotidiano": "sem trilha, ou pad quase inaudível",
    "meio-ambiente": "som ambiente real (chuva, vento) + pad grave",
    "geral": "batida neutra, 105 bpm, em -18 dB sob a voz",
}

HASHTAGS_BASE = {
    "economia": ["economia", "dinheiro", "financas", "bolso"],
    "politica": ["politica", "brasil", "congresso"],
    "mundo": ["internacional", "mundo", "geopolitica"],
    "tecnologia": ["tecnologia", "inteligenciaartificial", "tech"],
    "ciencia": ["ciencia", "pesquisa", "curiosidades"],
    "saude": ["saude", "bemestar"],
    "esporte": ["esporte", "futebol"],
    "cultura": ["cultura", "entretenimento"],
    "cotidiano": ["noticias", "cidades"],
    "meio-ambiente": ["meioambiente", "clima", "sustentabilidade"],
    "geral": ["noticias", "atualidades"],
}


# ---------------------------------------------------------------- fatos
def extrair_fatos(pauta: dict) -> dict:
    titulo = limpar_html(pauta["titulo"])
    resumo = limpar_html(pauta.get("resumo", ""))
    texto = f"{titulo}. {resumo}"

    percentuais = _RE_PERCENT.findall(texto)
    dinheiro = _RE_DINHEIRO.findall(texto)
    grandes = _RE_GRANDE.findall(texto)
    numeros = _RE_NUM.findall(titulo)

    ents, originais = [], []
    for e in entidades_seq(titulo):
        if e in ents or len(e) <= 2:
            continue
        ents.append(e)
        m = re.search(rf"\b{re.escape(e[:4])}\w*", titulo, re.IGNORECASE)
        originais.append(m.group(0) if m else e)

    verbo = None
    for t in normalizar(titulo).split():
        if t in VERBOS_FORTES:
            verbo = VERBOS_FORTES[t]
            break

    numero_destaque = (percentuais[0] if percentuais else
                       (dinheiro[0] if dinheiro else
                        (grandes[0] if grandes else (numeros[0] if numeros else None))))
    if numero_destaque:
        # "R$ 1.621." viraria "R$ 1.621.. Guarda esse numero" no gancho.
        numero_destaque = re.sub(r"[.,;:]+$", "", numero_destaque.strip())

    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", resumo) if len(f.strip()) > 25]
    return {
        "titulo": titulo, "resumo": resumo, "frases_resumo": frases[:4],
        "percentuais": percentuais[:3], "dinheiro": dinheiro[:3], "numeros": numeros[:4],
        "numero_destaque": numero_destaque, "entidades": originais[:4],
        "entidade_principal": originais[0] if originais else None, "verbo": verbo,
    }


def _encurtar(texto: str, limite: int) -> str:
    t = re.sub(r"\s+", " ", texto or "").strip().rstrip(".")
    if len(t) <= limite:
        return t
    return t[:limite].rsplit(" ", 1)[0] + "..."


def _minuscula(t: str) -> str:
    return (t[0].lower() + t[1:]) if t else t


def _pontuar_fim(t: str, sinal: str = ".") -> str:
    """Fecha a frase sem duplicar pontuacao (titulo que ja termina em ? ou !)."""
    t = (t or "").rstrip()
    return t if t.endswith(("?", "!", ".", "…")) else t + sinal


def _traduzir(texto: str, idioma: str = "pt") -> str:
    """Marca para traducao so o trecho que de fato nao esta em portugues.

    O idioma do veiculo nao basta: o resumo pode ja ter chegado traduzido, e
    marcar texto em portugues como "traduzir" so atrapalha quem vai gravar.
    """
    if parece_portugues(texto):
        return texto
    return f'[TRADUZIR PARA A FALA: "{texto}"]' 


def _frase_pendente(frases: list[str]) -> tuple[str | None, list[str]]:
    """Separa a frase que soa como pendencia das demais."""
    restantes = list(frases)
    for f in frases:
        alvo = f.lower()
        if any(m in alvo for m in MARCAS_PENDENCIA):
            restantes.remove(f)
            return f, restantes
    return None, restantes


def _confirmacao(pauta: dict) -> str:
    n = pauta.get("n_fontes", 1)
    fonte = pauta.get("fonte_principal", "a imprensa")
    if n >= 3:
        return f"Já são {n} veículos publicando a mesma informação."
    if n == 2:
        fontes = pauta.get("fontes", [])
        return f"Quem publicou: {fontes[0]} e {fontes[1]}." if len(fontes) >= 2 else \
               f"A informação é de {fonte}."
    return f"A informação é de {fonte} — e, por enquanto, só esse veículo publicou."


# ---------------------------------------------------------------- ganchos
def _ganchos(pauta: dict, f: dict) -> list[dict]:
    fam = list(pauta.get("reels_detalhe", {}).get("familias", {}).keys())
    ent, num = f["entidade_principal"], f["numero_destaque"]
    idioma = pauta.get("idioma", "pt")
    titulo_curto = _encurtar(f["titulo"], 92)
    out: list[dict] = []

    if num:
        out.append({"arquetipo": "número",
                    "fala": f"{num}. Guarda esse número, porque ele explica a notícia mais "
                            f"importante do dia.",
                    "porque": "número concreto na primeira frase prende mais que adjetivo"})
    if "bolso" in fam:
        out.append({"arquetipo": "bolso",
                    "fala": "Essa mexe direto no seu bolso — e muita gente vai descobrir tarde.",
                    "porque": "consequência financeira pessoal é o gatilho mais forte em vídeo curto"})
    if "utilidade" in fam:
        out.append({"arquetipo": "prazo",
                    "fala": "Mudou a regra. E tem prazo. Trinta segundos para você não perder.",
                    "porque": "utilidade com prazo gera salvamento e compartilhamento"})
    if "espanto" in fam:
        out.append({"arquetipo": "contraste",
                    "fala": "Isso não tinha acontecido antes. E aconteceu hoje.",
                    "porque": "quebra de expectativa segura o espectador nos 3 primeiros segundos"})
    if "conflito" in fam:
        out.append({"arquetipo": "tensão",
                    "fala": f"A disputa em volta de {ent or 'esse assunto'} acabou de subir de nível.",
                    "porque": "conflito claro cria a pergunta implícita: e agora?"})
    if "tecnologia" in fam:
        out.append({"arquetipo": "futuro próximo",
                    "fala": f"O que {ent or 'essa empresa'} acabou de fazer muda o que você faz "
                            f"no celular.",
                    "porque": "liga tecnologia distante a hábito concreto"})
    if "humano" in fam:
        out.append({"arquetipo": "pessoa",
                    "fala": "Tem gente de verdade no meio dessa notícia. E é aí que ela aperta.",
                    "porque": "rosto e consequência humana sustentam retenção até o fim"})

    if parece_portugues(titulo_curto):
        out.append({"arquetipo": "pergunta",
                    "fala": _pontuar_fim(f"Você viu que {_minuscula(titulo_curto)}", "?"),
                    "porque": "pergunta direta funciona quando o fato já surpreende sozinho"})
        out.append({"arquetipo": "direto",
                    "fala": f"{titulo_curto}. Te explico em 30 segundos o que isso significa.",
                    "porque": "gancho seco: entrega a notícia e promete o contexto"})
    else:
        out.append({"arquetipo": "direto",
                    "fala": _traduzir(titulo_curto)
                            + " Te explico em 30 segundos o que isso significa.",
                    "porque": "gancho seco: entrega a notícia e promete o contexto — "
                              "traduza o título antes de gravar, não leia em inglês"})

    vistos, finais = set(), []
    for g in out:
        if g["arquetipo"] in vistos:
            continue
        vistos.add(g["arquetipo"])
        finais.append(g)
    return finais[:3]


# ---------------------------------------------------------------- blocos
def _blocos(pauta: dict, f: dict, perfil: dict) -> list[dict]:
    editoria = pauta.get("editoria", "geral")
    idioma = pauta.get("idioma", "pt")
    ponte = PONTE.get(editoria, PONTE["geral"])
    fato = _traduzir(_pontuar_fim(_encurtar(f["titulo"], 120)), idioma)
    pendente, outras = _frase_pendente(f["frases_resumo"])
    dado = outras[0] if outras else None
    extra = outras[1] if len(outras) > 1 else None

    blocos = [{
        "rotulo": "O QUE ACONTECEU",
        "fala": f"{fato} {_confirmacao(pauta)}",
        "texto_tela": _encurtar(f["titulo"], 56).upper(),
        "b_roll": "você de frente, plano médio, fundo limpo",
        "direcao": "corte seco vindo do gancho; não respire entre as duas frases",
    }]

    if dado:
        blocos.append({
            "rotulo": "O DADO",
            "fala": _traduzir(_pontuar_fim(_encurtar(dado, 190)), idioma),
            "texto_tela": f["numero_destaque"] or "O DADO",
            "b_roll": "print da matéria com o trecho destacado, entrando com motion blur",
            "direcao": "deixa o número 1,5 s parado na tela antes de cortar"})
    else:
        blocos.append({
            "rotulo": "O DADO",
            "fala": f"[CONFERIR: abra {pauta.get('url') or 'a matéria'} e traga aqui o número "
                    f"ou o trecho mais forte — uma frase, no máximo duas.]",
            "texto_tela": "O DADO",
            "b_roll": "print da matéria com o trecho destacado, entrando com motion blur",
            "direcao": "sem número esse bloco cai — não grave antes de preencher"})

    blocos.append({
        "rotulo": "POR QUE IMPORTA",
        "fala": f"E por que isso importa para você: {ponte}. "
                f"[CONFERIR: complete com o efeito concreto — quem ganha, quem perde, "
                f"quanto muda, a partir de quando.]",
        "texto_tela": "POR QUE ISSO TE AFETA",
        "b_roll": "b-roll do cotidiano ligado ao tema (mão no cartão, fila, celular, rua)",
        "direcao": "aqui o ritmo cai um pouco: é o bloco que faz a pessoa ficar"})

    if pendente:
        blocos.append({
            "rotulo": "O QUE AINDA ESTÁ EM ABERTO",
            "fala": _traduzir(_pontuar_fim(_encurtar(pendente, 170)), idioma),
            "texto_tela": "AINDA EM ABERTO",
            "b_roll": "texto na tela sobre fundo escuro, câmera parada",
            "direcao": "tom mais baixo e mais lento — sinaliza que aqui é ressalva"})
    elif extra:
        blocos.append({
            "rotulo": "MAIS UM DADO",
            "fala": _traduzir(_pontuar_fim(_encurtar(extra, 170)), idioma),
            "texto_tela": "E TEM MAIS",
            "b_roll": "segundo print ou gráfico simples, entrada com blur",
            "direcao": "esse bloco é bônus: se o vídeo passar de 60 s, corta ele primeiro"})
    else:
        blocos.append({
            "rotulo": "O QUE AINDA ESTÁ EM ABERTO",
            "fala": "O que ainda não está fechado é como isso vai funcionar na prática. "
                    "E é exatamente isso que vale acompanhar nos próximos dias.",
            "texto_tela": "AINDA EM ABERTO",
            "b_roll": "texto na tela sobre fundo escuro, câmera parada",
            "direcao": "tom mais baixo — honestidade aqui gera confiança e retorno"})

    blocos.append({
        "rotulo": "CTA",
        "fala": perfil.get("assinatura_cta", "Segue para não perder o radar de amanhã."),
        "texto_tela": "RADAR TODO DIA ÀS 6H",
        "b_roll": "volta para o plano de frente, olhando a câmera",
        "direcao": "um pedido só: ou segue, ou salva, ou comenta — nunca os três"})
    return blocos


def _cronometrar(blocos: list[dict], gancho: dict, pps: float) -> tuple[list[dict], float]:
    itens = [{"rotulo": "GANCHO", "fala": gancho["fala"], "texto_tela": "",
              "b_roll": "close, olhando direto na câmera",
              "direcao": "os 3 primeiros segundos sem corte — é exatamente aqui que o "
                         "algoritmo mede"}]
    itens += blocos
    t = 0.0
    for b in itens:
        limpa = re.sub(r"\[CONFERIR:[^\]]*\]", "", b["fala"])
        limpa = re.sub(r"\[TRADUZIR PARA A FALA:\s*", "", limpa).replace('"]', '"')
        palavras = len(limpa.split())
        dur = max(1.6, palavras / pps)
        b["inicio_s"], b["duracao_s"] = round(t, 1), round(dur, 1)
        t += dur
        b["fim_s"] = round(t, 1)
    return itens, round(t, 1)


def _hashtags(pauta: dict) -> list[str]:
    tags = list(HASHTAGS_BASE.get(pauta.get("editoria", "geral"), HASHTAGS_BASE["geral"]))
    for e in entidades_seq(pauta["titulo"])[:3]:
        c = canonizar(e).replace(" ", "")
        if len(c) >= 4 and c not in tags:
            tags.append(c)
    if pauta.get("pais") == "BR" and "brasil" not in tags:
        tags.append("brasil")
    tags.append("radardenoticias")
    return [f"#{t}" for t in tags[:9]]


def _legenda(pauta: dict, f: dict) -> str:
    fontes = ", ".join(pauta.get("fontes", [])[:3]) or pauta.get("fonte_principal", "")
    return (f"{_encurtar(f['titulo'], 150)}\n\n"
            f"O que isso muda na prática está no vídeo. Fontes: {fontes}.\n\n"
            + " ".join(_hashtags(pauta)))


def montar(pauta: dict, cfg: dict) -> dict:
    perfil = cfg["perfil"]
    pps = perfil.get("palavras_por_segundo", 2.6)
    f = extrair_fatos(pauta)
    ganchos = _ganchos(pauta, f)
    roteiro, duracao = _cronometrar(_blocos(pauta, f, perfil), ganchos[0], pps)

    checagem = [f"Abra a fonte antes de gravar: {pauta.get('url') or 'sem link'}"]
    checagem += [r["aviso"] for r in pauta.get("riscos", [])]
    if pauta.get("n_fontes", 1) < 2:
        checagem.append("Só um veículo publicou: fale 'segundo <veículo>', não como fato dado.")
    if any("[TRADUZIR" in b["fala"] for b in roteiro) or \
            any("[TRADUZIR" in g["fala"] for g in ganchos):
        checagem.insert(1, "Trecho em outro idioma: traduza o que está marcado "
                           "[TRADUZIR PARA A FALA] e confira números e nomes próprios.")
    elif pauta.get("idioma") != "pt":
        checagem.insert(1, "Matéria publicada em outro idioma: confira números e "
                           "nomes próprios na fonte original.")
    if any("[CONFERIR:" in b["fala"] for b in roteiro):
        checagem.append("Há trecho [CONFERIR:] no roteiro — preencha antes de gravar.")

    return {
        "id": hash_id("roteiro", pauta["id"]),
        "slug": pauta["slug"],
        "titulo_pauta": pauta["titulo"],
        "editoria": pauta.get("editoria"),
        "pais": pauta.get("pais"),
        "score": pauta.get("score"),
        "score_noticia": pauta.get("score_noticia"),
        "score_reels": pauta.get("score_reels"),
        "duracao_s": duracao,
        "dentro_do_alvo": perfil["duracao_min_s"] <= duracao <= perfil["duracao_max_s"],
        "palavras": sum(len(b["fala"].split()) for b in roteiro),
        "ganchos": ganchos,
        "roteiro": roteiro,
        "trilha": TRILHA.get(pauta.get("editoria", "geral"), TRILHA["geral"]),
        "hashtags": _hashtags(pauta),
        "legenda_sugerida": _legenda(pauta, f),
        "fontes_para_citar": pauta.get("fontes", [])[:4],
        "links": [m.get("url") for m in pauta.get("materias", [])[:4] if m.get("url")],
        "checagem": checagem,
        "producao": {
            "formato": "9:16, 1080x1920",
            "cortes": "troca de plano a cada 2,5 s no máximo; nos cortes, blur de movimento "
                      "curto (120-160 ms)",
            "legenda": "legenda queimada sempre — a maioria assiste sem som",
            "primeiro_frame": "frame 1 com o número ou a palavra-chave gigante na tela",
        },
        "gerado_em": agora_br().isoformat(timespec="seconds"),
    }


def montar_varios(pautas: list[dict], cfg: dict) -> list[dict]:
    out = [montar(p, cfg) for p in pautas]
    log(f"roteirista: {len(out)} roteiros "
        f"({sum(1 for r in out if r['dentro_do_alvo'])} dentro do tempo alvo)", "agente")
    return out


def imprimir(r: dict) -> str:
    L = [f"### {r['titulo_pauta']}",
         f"*{r['editoria']} · {'Brasil' if r['pais'] == 'BR' else 'Mundo'} · "
         f"notícia {r['score_noticia']:.0f} · reels {r['score_reels']:.0f} · "
         f"~{r['duracao_s']:.0f}s · {r['palavras']} palavras*\n",
         "**Ganchos (escolha 1):**"]
    for i, g in enumerate(r["ganchos"], 1):
        L.append(f"{i}. **[{g['arquetipo']}]** “{g['fala']}”")
        L.append(f"   - por que funciona: {g['porque']}")
    L.append("\n**Roteiro cronometrado**\n")
    L.append("| tempo | bloco | fala | texto na tela | imagem |")
    L.append("|---|---|---|---|---|")
    for b in r["roteiro"]:
        L.append(f"| {b['inicio_s']:.0f}–{b['fim_s']:.0f}s | {b['rotulo']} | "
                 f"{b['fala'].replace('|','/')} | {b['texto_tela']} | {b['b_roll']} |")
    L.append(f"\n**Trilha:** {r['trilha']}  ")
    L.append(f"**Produção:** {r['producao']['cortes']}  ")
    L.append(f"**Hashtags:** {' '.join(r['hashtags'])}")
    L.append("\n**Antes de gravar**")
    for c in r["checagem"]:
        L.append(f"- {c}")
    return "\n".join(L)
