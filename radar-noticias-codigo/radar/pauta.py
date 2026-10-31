"""Agente Curador: junta materias que falam da mesma coisa em uma pauta.

Clusterizacao por ligacao simples (single-link) com similaridade hibrida:
titulo (jaccard de tokens) + entidades (nomes proprios/siglas) + numeros em comum.
Sem dependencia externa - roda em qualquer python 3.9+.
"""
from __future__ import annotations

import re
from datetime import timedelta

from .util import (agora_br, canonizar, entidades_canon, hash_id, jaccard, log,
                   overlap, parse_data, slug, tokens_canon)

LEXICO_EDITORIA = {
    "politica": ["congresso", "senado", "camara", "stf", "ministro", "presidente", "deputado",
                 "senador", "governo", "eleicao", "eleicoes", "votacao", "emenda", "pec",
                 "tse", "partido", "cpi", "impeachment", "posse", "planalto", "urna",
                 "candidato", "turno", "marcotemporal", "julgamento", "lei", "sancao",
                 "president", "senate", "congress", "election", "parliament", "court"],
    "economia": ["dolar", "euro", "ibovespa", "inflacao", "ipca", "selic", "juros", "pib",
                 "imposto", "tributaria", "mercado", "bolsa", "banco", "copom", "focus",
                 "salario", "emprego", "desemprego", "gasolina", "petroleo", "safra",
                 "divida", "orcamento", "fiscal", "receita", "inss", "fgts", "pix",
                 "inflation", "fed", "rate", "rates", "market", "markets", "stocks", "tariff",
                 "tariffs", "economy", "economic", "jobs", "bank", "banks", "banking",
                 "exports", "imports", "trade", "growth", "deficit", "budget", "gdp",
                 "stimulus", "retail", "consumer", "investors", "factory", "billion"],
    "mundo": ["guerra", "ucrania", "russia", "gaza", "israel", "china", "estados unidos",
              "eua", "otan", "onu", "venezuela", "argentina", "uniao europeia", "papa",
              "trump", "putin", "war", "ukraine", "nato", "summit", "sanctions", "border"],
    "tecnologia": ["inteligencia artificial", "ia", "chatgpt", "openai", "google", "apple",
                   "meta", "microsoft", "aplicativo", "app", "celular", "iphone", "android",
                   "chip", "nvidia", "dados", "hacker", "golpe", "cibernetico", "startup",
                   "software", "robo", "algoritmo", "ai", "chatbot", "cloud", "semiconductor"],
    "ciencia": ["estudo", "pesquisa", "pesquisadores", "cientistas", "nasa", "espaco",
                "vacina", "descoberta", "fossil", "clima", "aquecimento", "especie",
                "study", "research", "scientists", "space", "telescope"],
    "saude": ["saude", "sus", "hospital", "doenca", "surto", "epidemia", "dengue", "gripe",
              "anvisa", "medicamento", "remedio", "obesidade", "cancer", "mental",
              "health", "outbreak", "virus", "fda"],
    "esporte": ["futebol", "selecao", "copa", "brasileirao", "libertadores", "flamengo",
                "palmeiras", "corinthians", "gol", "titulo", "olimpiadas", "formula 1",
                "neymar", "jogo", "final", "campeonato", "league", "cup", "match"],
    "cultura": ["filme", "serie", "netflix", "show", "turne", "album", "musica", "oscar",
                "grammy", "livro", "festival", "cantor", "cantora", "ator", "atriz",
                "novela", "bbb", "film", "album", "tour"],
    "meio-ambiente": ["amazonia", "desmatamento", "cop", "clima", "queimada", "seca",
                      "enchente", "chuva", "temporal", "poluicao", "sustentabilidade",
                      "carbono", "climate", "flood", "wildfire", "drought"],
    "cotidiano": ["policia", "acidente", "morte", "morreu", "preso", "operacao", "crime",
                  "transito", "incendio", "roubo", "assalto", "violencia", "feminicidio",
                  "police", "crash", "killed", "arrested"],
}

_RE_NUM = re.compile(r"\b\d[\d.,]*\s?(?:%|mil|milhao|milhoes|bilhao|bilhoes|r\$|us\$)?", re.I)


def _assinatura(item: dict) -> dict:
    base = f"{item['titulo']} {item.get('resumo','')[:220]}"
    return {
        "tok": tokens_canon(item["titulo"]),
        "tok_amplo": tokens_canon(base),
        "ent": entidades_canon(item["titulo"]),
        "num": set(re.findall(r"\d[\d.,]{1,}", item["titulo"])),
        # O agente pode declarar que matérias são do mesmo fato ("grupo"),
        # quando o léxico não basta (ex.: "fugiu", "deixou o país", "passaporte").
        "grupo": item.get("grupo"),
    }


def similaridade(a: dict, b: dict) -> float:
    """0 a 1. Mistura sobreposicao de radicais, jaccard e entidades em comum.

    A sobreposicao (nao o jaccard puro) carrega o peso maior porque manchete de
    agencia e manchete de portal tem tamanhos muito diferentes para a mesma pauta.
    """
    if a.get("grupo") and a.get("grupo") == b.get("grupo"):
        return 1.0
    s = (0.50 * overlap(a["tok"], b["tok"])
         + 0.20 * jaccard(a["tok"], b["tok"])
         + 0.22 * overlap(a["ent"], b["ent"])
         + 0.08 * overlap(a["tok_amplo"], b["tok_amplo"]))
    if a["num"] & b["num"]:
        s += 0.05
    # Dois nomes proprios em comum no titulo quase sempre indicam a mesma pauta.
    if len(a["ent"] & b["ent"]) >= 2:
        s += 0.07
    return min(s, 1.0)


def classificar_editoria(texto: str, padrao: str = "geral") -> str:
    """Editoria por lexico. Checa o texto original e o canonizado (pega sigla e ingles)."""
    from .util import normalizar
    t = " " + normalizar(texto) + " " + canonizar(texto) + " "
    placar: dict[str, int] = {}
    for ed, palavras in LEXICO_EDITORIA.items():
        n = 0
        for p in palavras:
            if f" {p} " in t or t.startswith(p + " ") or f" {p}" in t[-len(p) - 1:]:
                n += 1
        if n:
            placar[ed] = n
    if not placar:
        return padrao
    return max(placar.items(), key=lambda kv: kv[1])[0]


def agrupar(itens: list[dict], limiar: float = 0.34) -> list[dict]:
    """Agrupa itens em pautas. Single-link: entra no grupo se parecer com qualquer membro."""
    assinaturas = [_assinatura(i) for i in itens]

    # Palavra que está em boa parte das matérias do dia não diferencia pauta
    # nenhuma (num dia pós-eleição, "lula" e "vitória" estão em quase tudo) e
    # só serve para encadear assuntos diferentes. Sai da comparação.
    if len(itens) >= 12:
        from collections import Counter
        freq = Counter()
        for a in assinaturas:
            freq.update(a["tok"] | a["ent"])
        teto = max(3, int(len(itens) * 0.15))
        comuns = {t for t, n in freq.items() if n > teto}
        if comuns:
            log(f"curador: ignorando termos onipresentes hoje: {', '.join(sorted(comuns))}", "info")
            for a in assinaturas:
                a["tok"] = a["tok"] - comuns
                a["ent"] = a["ent"] - comuns
                a["tok_amplo"] = a["tok_amplo"] - comuns

    grupos: list[list[int]] = []
    for idx in range(len(itens)):
        destino = None
        melhor = 0.0
        for g, grupo in enumerate(grupos):
            s = max(similaridade(assinaturas[idx], assinaturas[j]) for j in grupo)
            if s >= limiar and s > melhor:
                melhor, destino = s, g
        if destino is None:
            grupos.append([idx])
        else:
            grupos[destino].append(idx)

    pautas = [_montar_pauta([itens[j] for j in g]) for g in grupos]
    log(f"curador: {len(itens)} itens -> {len(pautas)} pautas", "agente")
    return pautas


def _montar_pauta(membros: list[dict]) -> dict:
    """Monta a pauta a partir das materias agrupadas.

    O titulo de referencia sai da fonte de maior peso; empate, a materia com data
    mais nova; sem data, a que veio primeiro na coleta - feed e busca entregam em
    ordem inversa de publicacao, entao posicao baixa e proxy de "mais recente".
    """
    # Fallback fixo: calcular agora_br() dentro da chave dava um datetime
    # diferente por chamada e o desempate caia nos microssegundos.
    SEM_DATA = agora_br() - timedelta(days=3650)

    PRECISAO = {"fonte": 2, "inferida": 1, "url": 1}

    def chave(i):
        dt = parse_data(i.get("publicado_em"))
        return (round(i.get("peso_fonte", 0.5), 2),
                PRECISAO.get(i.get("data_origem"), 2 if dt else 0),
                dt or SEM_DATA,
                -i.get("ordem", 0))

    principal = max(membros, key=chave)
    fontes = sorted({m["fonte"] for m in membros})
    datas = [parse_data(m.get("publicado_em")) for m in membros]
    datas = [d for d in datas if d]
    primeira = min(datas) if datas else None
    ultima = max(datas) if datas else None
    texto_todo = " ".join(m["titulo"] for m in membros) + " " + (principal.get("resumo") or "")
    # Se quem coletou declarou a editoria (agente que leu a materia), ela manda;
    # o lexico so decide quando ninguem declarou nada.
    declaradas = [m.get("editoria_declarada") for m in membros if m.get("editoria_declarada")]
    if declaradas:
        editoria = max(set(declaradas), key=declaradas.count)
    else:
        editoria = classificar_editoria(texto_todo, principal.get("editoria_fonte", "geral"))
    paises = {m.get("pais", "BR") for m in membros}
    pais = "BR" if "BR" in paises else "MUNDO"

    # Com menos de duas datas conhecidas nao da para medir ritmo: fica indefinido,
    # e o score trata isso como sinal neutro em vez de inventar uma velocidade alta.
    horas = None
    velocidade = None
    if len(datas) >= 2:
        horas = max((ultima - primeira).total_seconds() / 3600.0, 0.5)
        # Ritmo medido so sobre os itens que tem data - misturar os sem data
        # inflaria a velocidade.
        velocidade = len(datas) / horas

    return {
        "slug": slug(principal["titulo"]),
        "id": hash_id(*sorted(m["id"] for m in membros)),
        "titulo": principal["titulo"],
        "resumo": principal.get("resumo", "")[:420],
        "url": principal.get("url"),
        "fonte_principal": principal["fonte"],
        "fontes": fontes,
        "n_fontes": len(fontes),
        "n_itens": len(membros),
        "editoria": editoria,
        "pais": pais,
        "idioma": principal.get("idioma", "pt"),
        "primeira_publicacao": primeira.isoformat(timespec="seconds") if primeira else None,
        "ultima_publicacao": ultima.isoformat(timespec="seconds") if ultima else None,
        "janela_horas": round(horas, 2) if horas else None,
        "velocidade": round(velocidade, 2) if velocidade else None,
        "datas_conhecidas": len(datas),
        "traduzido_de": principal.get("traduzido_de"),
        "titulo_original": principal.get("titulo_original"),
        "materias": [{"titulo": m["titulo"], "fonte": m["fonte"], "url": m.get("url"),
                      "publicado_em": m.get("publicado_em"), "pais": m.get("pais"),
                      "traduzido_de": m.get("traduzido_de")}
                     for m in sorted(membros, key=chave, reverse=True)],
    }
