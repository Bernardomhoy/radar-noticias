#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Radar de Notícias — orquestrador dos agentes.

  python3 radar.py rodar                      # coleta RSS + curadoria + roteiros
  python3 radar.py rodar --ingest itens.json  # usa itens levantados pelo agente
  python3 radar.py rodar --sem-rss --ingest x.json   # só o que o agente trouxe
  python3 radar.py painel                     # regenera o painel HTML do último radar
  python3 radar.py stats                      # o que já passou pelo radar
  python3 radar.py testar                     # suíte de calibração
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from radar import __version__
from radar.armazem import Armazem
from radar.coleta import coletar
from radar.editor import selecionar
from radar.fontes import (carregar_config, carregar_fontes, carregar_preferencias,
                          carregar_regioes)
from radar.pauta import agrupar
from radar.roteiro import montar_varios
from radar.score import pontuar
from radar.util import agora_br, log


def _pesos_por_nome(fontes: list[dict]) -> dict[str, float]:
    return {f["nome"]: f.get("peso", 0.7) for f in fontes}


def rodar(args) -> int:
    inicio = agora_br()
    cfg = carregar_config()
    if args.pautas:
        cfg["selecao"]["pautas_por_dia"] = args.pautas
    if args.roteiros:
        cfg["selecao"]["roteiros_por_dia"] = args.roteiros

    fontes = carregar_fontes(pais=args.pais)
    itens: list[dict] = []
    diagnostico: list[dict] = []
    feeds_ok = feeds_total = 0

    if not args.sem_rss:
        resultado = coletar(fontes, cfg["selecao"]["janela_horas"])
        itens += resultado["itens"]
        diagnostico = resultado["diagnostico"]
        feeds_ok, feeds_total = resultado["feeds_ok"], resultado["feeds_total"]

    if args.ingest:
        from radar.ingest_agente import carregar_arquivo
        itens += carregar_arquivo(args.ingest)

    if cfg["selecao"].get("somente_portugues"):
        from radar.util import parece_portugues
        aceita = cfg["selecao"].get("aceitar_traducao", True)
        antes = len(itens)
        itens = [i for i in itens
                 if parece_portugues(i["titulo"]) and (aceita or not i.get("traduzido_de"))]
        if antes - len(itens):
            log(f"idioma: {antes - len(itens)} matérias fora por não estarem em português", "info")

    from radar.coleta import filtrar_janela
    janela = cfg["selecao"]["janela_horas"]
    exigir = cfg["selecao"].get("exigir_data", False)
    descartes: dict = {}
    lidos = len(itens)
    fontes_lidas = len({i["fonte"] for i in itens})
    itens = filtrar_janela(itens, janela, exigir, descartes)
    log(f"janela de {janela}h: {len(itens)} de {lidos} itens ficam "
        f"({descartes.get('fora_da_janela', 0)} antigos, "
        f"{descartes.get('sem_data', 0)} sem data)", "info")

    if not itens:
        log("nenhum item coletado — nada a publicar. Veja as fontes que falharam acima.", "erro")
        if diagnostico:
            for d in diagnostico[:6]:
                log(f"  {d['fonte']}: {d.get('erro')}", "aviso")
        return 2

    armazem = Armazem()
    armazem.reidratar(os.path.join(os.path.dirname(os.path.abspath(__file__)), "saida"))
    novos = armazem.registrar_itens(itens)
    log(f"memória: {novos} itens inéditos de {len(itens)} coletados", "info")

    pautas = agrupar(itens, cfg.get("limiar_cluster", 0.40))
    pesos = _pesos_por_nome(fontes)
    for p in pautas:
        pontuar(p, cfg, pesos)

    recentes = armazem.pautas_recentes(cfg["selecao"]["dias_anti_repeticao"])
    prefs = carregar_preferencias()
    if prefs["temas"] or prefs["regioes"]:
        log(f"interesses do painel: temas={prefs['temas'] or '—'} "
            f"regiões={prefs['regioes'] or '—'}", "info")
    escolha = selecionar(pautas, cfg, recentes, prefs)
    if cfg.get("roteiros", {}).get("ativo", True):
        roteiros = montar_varios(escolha["para_roteiro"], cfg)
    else:
        roteiros = []
        log("roteiros desligados em config.json (roteiros.ativo = false)", "info")

    dia = inicio.date().isoformat()
    radar = {
        "versao": __version__,
        "dia": dia,
        "gerado_em": inicio.isoformat(timespec="seconds"),
        "config": cfg,
        "pautas": escolha["pautas"],
        "roteiros": roteiros,
        "reservas": escolha["reservas"],
        "descartadas": escolha["descartadas"],
        "preferencias": escolha["preferencias_aplicadas"],
        "regioes": carregar_regioes(),
        "diagnostico": diagnostico,
        "metricas": {
            "itens_coletados": len(itens),
            "itens_lidos": lidos,
            "fontes_lidas": fontes_lidas,
            "janela_horas": janela,
            "descartados_antigos": descartes.get("fora_da_janela", 0),
            "descartados_sem_data": descartes.get("sem_data", 0),
            "itens_ineditos": novos,
            "pautas_identificadas": len(pautas),
            "pautas_selecionadas": len(escolha["pautas"]),
            "roteiros_gerados": len(roteiros),
            "fontes_ativas": len({i["fonte"] for i in itens}),
            "feeds_ok": feeds_ok,
            "feeds_total": feeds_total,
            "distribuicao_editoria": escolha["distribuicao_editoria"],
            "origem_itens": {o: sum(1 for i in itens if i.get("origem") == o)
                             for o in {i.get("origem", "rss") for i in itens}},
        },
    }

    from radar.briefing import publicar
    caminhos = publicar(radar)

    from radar.painel import gerar_painel
    caminhos["painel"] = gerar_painel(radar)

    armazem.registrar_pautas(escolha["pautas"], dia)
    armazem.registrar_roteiros(roteiros, dia)
    armazem.registrar_execucao({
        "iniciado_em": radar["gerado_em"], "itens": len(itens),
        "pautas": len(escolha["pautas"]), "roteiros": len(roteiros),
        "feeds_ok": feeds_ok, "feeds_total": feeds_total,
    })
    armazem.fechar()

    log(f"pronto em {(agora_br()-inicio).total_seconds():.1f}s", "ok")
    print("\n".join(f"{k}: {v}" for k, v in caminhos.items()))
    return 0


def painel(args) -> int:
    from radar.painel import gerar_painel
    from radar.util import ler_json
    caminho = args.arquivo or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "saida", "ultimo.json")
    radar = ler_json(caminho)
    if not radar:
        log(f"não achei radar em {caminho}. Rode `python3 radar.py rodar` primeiro.", "erro")
        return 2
    print(gerar_painel(radar))
    return 0


def stats(_args) -> int:
    a = Armazem()
    e = a.estatisticas()
    print(f"itens na memória:   {e['itens']}")
    print(f"pautas registradas: {e['pautas']}")
    print(f"roteiros gerados:   {e['roteiros']}")
    print(f"execuções:          {e['execucoes']}")
    recentes = a.pautas_recentes(7)
    if recentes:
        print("\núltimos 7 dias:")
        for r in recentes[:20]:
            marca = "🎬" if r["virou_roteiro"] else "  "
            print(f"  {r['dia']} {marca} {r['score']:5.1f} {r['titulo'][:70]}")
    a.fechar()
    return 0


def testar(_args) -> int:
    import subprocess
    raiz = os.path.dirname(os.path.abspath(__file__))
    return subprocess.call([sys.executable, os.path.join(raiz, "testes", "test_cluster.py")])


def main() -> int:
    ap = argparse.ArgumentParser(description="Radar de Notícias (Brasil + mundo)")
    sub = ap.add_subparsers(dest="cmd")

    r = sub.add_parser("rodar", help="roda o ciclo completo")
    r.add_argument("--ingest", help="JSON com itens levantados pelo agente")
    r.add_argument("--sem-rss", action="store_true", help="não tenta os feeds RSS")
    r.add_argument("--pais", choices=["BR", "MUNDO"], help="limita as fontes a um escopo")
    r.add_argument("--pautas", type=int, help="quantas pautas no briefing")
    r.add_argument("--roteiros", type=int, help="quantos roteiros gerar")
    r.set_defaults(func=rodar)

    p = sub.add_parser("painel", help="regenera o painel HTML")
    p.add_argument("arquivo", nargs="?", help="radar.json específico")
    p.set_defaults(func=painel)

    sub.add_parser("stats", help="histórico do radar").set_defaults(func=stats)
    sub.add_parser("testar", help="suíte de calibração").set_defaults(func=testar)

    args = ap.parse_args()
    if not getattr(args, "func", None):
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
