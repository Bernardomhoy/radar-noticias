# -*- coding: utf-8 -*-
"""Entrada alternativa de materia: itens levantados pelo agente (busca na web).

Serve para dois casos:
  1. a rede do ambiente bloqueia os feeds RSS dos veiculos;
  2. o agente achou algo que nao estava em feed nenhum.

Formato esperado (JSON, lista ou {"itens": [...]}):
  [{"titulo": "...", "fonte": "g1", "url": "https://...",
    "resumo": "...", "publicado_em": "2026-10-26T07:00:00-03:00", "pais": "BR"}]

So "titulo" e "fonte" sao obrigatorios. O resto o modulo completa, e o peso da
fonte vem do registro de fontes quando o nome bate.
"""
from __future__ import annotations

import re

from .fontes import carregar_fontes
from .util import agora_br, dominio, hash_id, iso, limpar_html, log

# Padroes de data em URL de veiculo: /2026/10/25/, -26102026/, /2026-10-25/.
# So aceita dia completo - mes sozinho (ex.: /2026-10/) nao basta para a janela.
_URL_DATAS = [
    (re.compile(r"/(20\d\d)/(\d{1,2})/(\d{1,2})/"), ("a", "m", "d")),
    (re.compile(r"/(20\d\d)-(\d{2})-(\d{2})(?:/|$)"), ("a", "m", "d")),
    (re.compile(r"[-/](\d{2})(\d{2})(20\d\d)(?:-\d+)?/?$"), ("d", "m", "a")),
]


def data_pela_url(url: str) -> str | None:
    for padrao, ordem in _URL_DATAS:
        m = padrao.search(url or "")
        if not m:
            continue
        partes = dict(zip(ordem, (int(g) for g in m.groups())))
        if 1 <= partes["m"] <= 12 and 1 <= partes["d"] <= 31:
            # meio-dia de Brasilia: sem hora na URL, evita empurrar a materia
            # para o dia anterior ou seguinte na conversao de fuso
            return f"{partes['a']:04d}-{partes['m']:02d}-{partes['d']:02d}T12:00:00-03:00"
    return None


def _indice_fontes() -> dict[str, dict]:
    idx = {}
    for f in carregar_fontes():
        idx[f["id"].lower()] = f
        idx[f["nome"].lower()] = f
    return idx


def normalizar_itens(brutos: list[dict]) -> list[dict]:
    idx = _indice_fontes()
    saida, ignorados = [], 0
    for posicao, b in enumerate(brutos):
        titulo = limpar_html(b.get("titulo") or b.get("title") or "")
        nome_fonte = (b.get("fonte") or b.get("source") or "").strip()
        if not titulo or not nome_fonte:
            ignorados += 1
            continue
        ref = idx.get(nome_fonte.lower(), {})
        url = b.get("url") or b.get("link") or ""
        publicado = b.get("publicado_em") or data_pela_url(url)
        saida.append({
            "id": hash_id(ref.get("id", nome_fonte), titulo[:160]),
            "titulo": titulo,
            "resumo": limpar_html(b.get("resumo") or b.get("summary") or "")[:600],
            "url": url,
            "fonte_id": ref.get("id", nome_fonte.lower().replace(" ", "_")),
            "fonte": ref.get("nome", nome_fonte),
            "peso_fonte": b.get("peso_fonte", ref.get("peso", 0.70)),
            "pais": b.get("pais", ref.get("pais", "BR")).upper(),
            "idioma": b.get("idioma", ref.get("idioma", "pt")),
            "editoria_fonte": b.get("editoria", ref.get("editoria", "geral")),
            # Sem data informada nem deduzivel pela URL fica None: data inventada
            # viraria "recencia" falsa.
            "publicado_em": publicado or None,
            # Precisao da data: so "fonte" traz horario de verdade. URL e inferencia
            # dao o dia, com hora convencional - nao podem vencer horario real.
            "data_origem": ("inferida" if b.get("data_inferida")
                            else "fonte" if b.get("publicado_em")
                            else "url" if publicado else "sem data"),
            # Editoria escolhida por quem leu a materia vale mais que o lexico.
            "editoria_declarada": b.get("editoria"),
            "grupo": b.get("grupo"),
            # Traducao feita pelo agente: o titulo exibido e o portugues, o
            # original fica guardado para conferencia.
            "titulo_original": b.get("titulo_original"),
            "traduzido_de": b.get("traduzido_de"),
            "data_inferida": b.get("data_inferida"),
            "coletado_em": iso(agora_br()),
            "origem": "agente",
            "feed": "busca-agente",
            "dominio": dominio(url),
            "ordem": posicao,
        })
    if ignorados:
        log(f"ingest: {ignorados} item(ns) sem titulo ou fonte foram ignorados", "aviso")
    log(f"ingest: {len(saida)} itens vindos do agente", "agente")
    return saida


def carregar_arquivo(caminho: str) -> list[dict]:
    from .util import ler_json
    dados = ler_json(caminho)
    if dados is None:
        raise SystemExit(f"arquivo de ingestao nao encontrado: {caminho}")
    if isinstance(dados, dict):
        dados = dados.get("itens", [])
    if not isinstance(dados, list):
        raise SystemExit("formato invalido: esperava lista de itens ou {'itens': [...]}")
    return normalizar_itens(dados)
