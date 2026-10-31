# -*- coding: utf-8 -*-
"""Agente Publicador: escreve o briefing do dia em JSON e em Markdown."""
from __future__ import annotations

import os

from .roteiro import imprimir as imprimir_roteiro
from .util import RAIZ, agora_br, escrever_json, log

DIR_SAIDA = os.path.join(RAIZ, "saida")

MEDALHA = {0: "1º", 1: "2º", 2: "3º"}


def _barra(valor: float, largura: int = 10) -> str:
    cheio = int(round(valor * largura))
    return "█" * cheio + "·" * (largura - cheio)


def montar_markdown(radar: dict) -> str:
    cfg = radar["config"]
    L = []
    dia = radar["dia"]
    hora = radar["gerado_em"][11:16]
    L.append(f"# Radar de Notícias — {dia}")
    L.append(f"*Fechado às {hora} (horário de Brasília) · "
             f"{radar['metricas']['itens_coletados']} matérias lidas · "
             f"{radar['metricas']['pautas_identificadas']} pautas identificadas · "
             f"{radar['metricas']['fontes_ativas']} fontes ativas*\n")

    L.append("## Pauta do dia\n")
    if radar["roteiros"]:
        L.append("*Ordenada por valor jornalístico. A fila de gravação (🎬) segue outra "
                 "ordem: a de potencial de vídeo curto.*\n")
    else:
        L.append("*Ordenada por valor jornalístico.*\n")
    for i, p in enumerate(radar["pautas"]):
        marca = " 🎬" if p.get("virou_roteiro") else ""  # vazio com roteiros off
        L.append(f"**{i+1}. {p['titulo']}**{marca}  ")
        com_reels = bool(radar["roteiros"])
        nota_reels = f"reels `{p['score_reels']:.0f}` · " if com_reels else ""
        L.append(f"notícia `{p['score_noticia']:.0f}` · {nota_reels}"
                 f"{p['editoria']} · {'Brasil' if p['pais']=='BR' else 'Mundo'} · "
                 f"{p['n_fontes']} veículo{'s' if p['n_fontes']>1 else ''} · "
                 f"{p['fonte_principal']}  ")
        if p.get("resumo"):
            L.append(f"{p['resumo'][:260]}  ")
        L.append(f"*Por que entrou:* {p['explicacao']}  ")
        if com_reels:
            L.append(f"*Para vídeo:* {p['explicacao_reels']}  ")
        comp = p["componentes"]
        sinais = [f"corroboração {_barra(comp['corroboracao'])}",
                  f"recência {_barra(comp['recencia'])}",
                  f"calor {_barra(comp['calor'])}"]
        if com_reels:
            sinais.append(f"reels {_barra(comp['potencial_reels'])}")
        L.append("*Sinais:* " + " · ".join(sinais) + "  ")
        if p.get("riscos"):
            for r in p["riscos"]:
                L.append(f"> ⚠️ {r['aviso']}  ")
        if p.get("url"):
            L.append(f"[Ler na fonte]({p['url']})  ")
        if p.get("n_itens", 1) > 1:
            vistas: dict[str, dict] = {}
            for m in p["materias"]:
                alvo = vistas.setdefault(m["fonte"], {"n": 0, "url": m.get("url")})
                alvo["n"] += 1
            partes = []
            for fonte, d in list(vistas.items())[:6]:
                rotulo = fonte + (f" ({d['n']})" if d["n"] > 1 else "")
                partes.append(f"[{rotulo}]({d['url']})" if d["url"] else rotulo)
            L.append("Cobertura: " + " · ".join(partes) + "  ")
        L.append("")

    if radar["roteiros"]:
        L.append("## Roteiros para gravar hoje\n")
    for i, r in enumerate(radar["roteiros"]):
        L.append(f"#### Reels {i+1} — {MEDALHA.get(i, str(i+1)+'º')} da fila\n")
        L.append(imprimir_roteiro(r))
        L.append("\n---\n")

    if radar.get("reservas"):
        L.append("## Reserva (não entrou hoje)\n")
        for p in radar["reservas"][:8]:
            motivo = p.get("motivo_descarte", "ficou fora do corte")
            L.append(f"- `{p['score_noticia']:.0f}` {p['titulo'][:95]} — *{motivo}*")
        L.append("")

    if radar.get("descartadas"):
        L.append("## Já foi pauta nos últimos dias\n")
        for p in radar["descartadas"][:6]:
            L.append(f"- {p['titulo'][:95]} — *{p.get('motivo_descarte','')}*")
        L.append("")

    diag = radar.get("diagnostico", [])
    falhas = [d for d in diag if d.get("erro")]
    if falhas:
        L.append("## Fontes que não responderam\n")
        for d in falhas[:14]:
            L.append(f"- {d['fonte']}: `{d['erro']}`")
        L.append("")

    L.append("---")
    L.append(f"*Gerado pelo Radar de Notícias v{radar['versao']} · "
             f"perfil: {cfg['perfil']['nome_canal']} · "
             f"alvo de {cfg['perfil']['duracao_alvo_s']}s por reels*")
    return "\n".join(L)


def publicar(radar: dict) -> dict:
    dia = radar["dia"]
    pasta = os.path.join(DIR_SAIDA, dia)
    os.makedirs(pasta, exist_ok=True)

    caminho_json = os.path.join(pasta, "radar.json")
    caminho_md = os.path.join(pasta, "briefing.md")
    escrever_json(caminho_json, radar)
    with open(caminho_md, "w", encoding="utf-8") as fh:
        fh.write(montar_markdown(radar))

    # copia estavel para o painel e para a leitura rapida
    escrever_json(os.path.join(DIR_SAIDA, "ultimo.json"), radar)
    with open(os.path.join(DIR_SAIDA, "ultimo.md"), "w", encoding="utf-8") as fh:
        fh.write(montar_markdown(radar))

    log(f"publicador: {caminho_md}", "ok")
    return {"json": caminho_json, "markdown": caminho_md,
            "ultimo_json": os.path.join(DIR_SAIDA, "ultimo.json"),
            "ultimo_md": os.path.join(DIR_SAIDA, "ultimo.md")}
