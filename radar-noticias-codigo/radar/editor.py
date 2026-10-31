"""Agente Editor-Chefe: escolhe a pauta do dia com diversidade e sem repetir.

Regras (de config.json):
  - no maximo N pautas por dia, com piso de pautas do Brasil e teto de internacionais
  - no maximo X pautas da mesma editoria (nao da um radar so de economia)
  - nada que ja foi pauta nos ultimos D dias (compara radical canonico, nao o slug cru)
"""
from __future__ import annotations

from .fontes import carregar_regioes
from .util import canonizar, log, normalizar, overlap, tokens_canon


def _ja_foi_pauta(pauta: dict, recentes: list[dict], limiar: float = 0.62) -> dict | None:
    alvo = tokens_canon(pauta["titulo"])
    for r in recentes:
        if overlap(alvo, tokens_canon(r["titulo"])) >= limiar:
            return r
    return None


def afinidade(pauta: dict, prefs: dict, regioes: dict) -> tuple[float, list[str]]:
    """0 a 1 de quanto a pauta casa com os interesses declarados no painel.

    Nao mexe no score - entra so na hora de ordenar e escolher, e nunca passa
    por cima do piso de pautas do Brasil.
    """
    if not prefs.get("temas") and not prefs.get("regioes"):
        return 0.0, []
    motivos = []
    nota = 0.0
    if pauta.get("editoria", "").lower() in prefs.get("temas", []):
        nota += 0.6
        motivos.append(f"tema {pauta['editoria']}")
    texto = " " + normalizar(f"{pauta['titulo']} {pauta.get('resumo','')}") + " " \
            + canonizar(f"{pauta['titulo']} {pauta.get('resumo','')}") + " "
    palavras = set(texto.split())
    for regiao in prefs.get("regioes", []):
        termos = regioes.get(regiao, [])
        achou = any((f" {t} " in texto) if " " in t else (t in palavras) for t in termos)
        if achou:
            nota += 0.4
            motivos.append(f"região {regiao}")
            break
    return min(nota, 1.0), motivos


def selecionar(pautas: list[dict], cfg: dict, recentes: list[dict] | None = None,
               prefs: dict | None = None) -> dict:
    sel = cfg["selecao"]
    recentes = recentes or []
    prefs = prefs or {"temas": [], "regioes": [], "peso": 0.0}
    regioes = carregar_regioes() if (prefs.get("temas") or prefs.get("regioes")) else {}
    peso_pref = prefs.get("peso", 0.35)

    for p in pautas:
        nota, motivos = afinidade(p, prefs, regioes)
        p["afinidade"] = round(nota, 2)
        p["afinidade_motivos"] = motivos
        p["prioridade"] = round(p.get("score_noticia", 0) * (1 + peso_pref * nota), 2)

    ordenadas = sorted(pautas, key=lambda p: -p.get("prioridade", 0))

    escolhidas: list[dict] = []
    reservas: list[dict] = []
    descartadas: list[dict] = []
    por_editoria: dict[str, int] = {}
    n_mundo = 0

    for p in ordenadas:
        if len(escolhidas) >= sel["pautas_por_dia"]:
            reservas.append(p)
            continue

        repetida = _ja_foi_pauta(p, recentes)
        if repetida:
            p["motivo_descarte"] = f"ja foi pauta em {repetida['dia']}"
            descartadas.append(p)
            continue

        ed = p.get("editoria", "geral")
        if por_editoria.get(ed, 0) >= sel["max_por_editoria"]:
            p["motivo_descarte"] = f"cota de {ed} cheia"
            reservas.append(p)
            continue
        if p.get("pais") == "MUNDO" and n_mundo >= sel["max_mundo"]:
            p["motivo_descarte"] = "cota de internacionais cheia"
            reservas.append(p)
            continue

        escolhidas.append(p)
        por_editoria[ed] = por_editoria.get(ed, 0) + 1
        if p.get("pais") == "MUNDO":
            n_mundo += 1

    # Piso de pautas nacionais: troca a internacional mais fraca por BR da reserva.
    def n_br(lista):
        return sum(1 for x in lista if x.get("pais") == "BR")

    falta_br = sel["min_br"] - n_br(escolhidas)
    if falta_br > 0:
        candidatas_br = [r for r in reservas if r.get("pais") == "BR"]
        for cand in candidatas_br:
            if falta_br <= 0:
                break
            mundo_fracas = [e for e in escolhidas if e.get("pais") == "MUNDO"]
            if not mundo_fracas:
                break
            fora = min(mundo_fracas, key=lambda x: x.get("prioridade", 0))
            escolhidas.remove(fora)
            fora["motivo_descarte"] = "cedeu lugar para garantir o piso de pautas do Brasil"
            reservas.append(fora)
            escolhidas.append(cand)
            reservas.remove(cand)
            falta_br -= 1

    # Piso da regiao pedida: se voce marcou "Reino Unido" no painel, o dia nao
    # fecha sem nenhuma pauta de la (desde que exista alguma na coleta).
    if prefs.get("regioes"):
        def tem_regiao(p):
            return any(m.startswith("região") for m in p.get("afinidade_motivos", []))

        if not any(tem_regiao(e) for e in escolhidas):
            candidatas = [r for r in reservas if tem_regiao(r)]
            candidatas.sort(key=lambda x: -x.get("prioridade", 0))
            if candidatas:
                cand = candidatas[0]
                descartaveis = [e for e in escolhidas
                                if not tem_regiao(e)
                                and (e.get("pais") != "BR"
                                     or sum(1 for x in escolhidas if x.get("pais") == "BR")
                                     > sel["min_br"])]
                if descartaveis:
                    fora = min(descartaveis, key=lambda x: x.get("prioridade", 0))
                    escolhidas.remove(fora)
                    fora["motivo_descarte"] = "cedeu lugar para a região que você pediu"
                    reservas.append(fora)
                    escolhidas.append(cand)
                    reservas.remove(cand)

    # Piso de internacionais: o radar e sobre o Brasil, mas nao pode fechar o dia
    # sem nenhuma pauta de fora.
    falta_mundo = sel.get("min_mundo", 0) - sum(1 for x in escolhidas if x.get("pais") == "MUNDO")
    if falta_mundo > 0:
        candidatas_mundo = [r for r in reservas if r.get("pais") == "MUNDO"]
        candidatas_mundo.sort(key=lambda x: -x.get("prioridade", 0))
        for cand in candidatas_mundo:
            if falta_mundo <= 0:
                break
            br_fracas = [e for e in escolhidas if e.get("pais") == "BR"]
            if len(br_fracas) <= sel["min_br"]:
                break
            fora = min(br_fracas, key=lambda x: x.get("prioridade", 0))
            escolhidas.remove(fora)
            fora["motivo_descarte"] = "cedeu lugar para a cota mínima de internacionais"
            reservas.append(fora)
            escolhidas.append(cand)
            reservas.remove(cand)
            falta_mundo -= 1

    escolhidas.sort(key=lambda p: -p.get("prioridade", 0))

    # A fila de gravacao e outra ordem: aqui manda o score_reels, nao o jornalistico.
    # Pauta sob contencao editorial forte fica no briefing, mas nao vira video.
    aptas = [p for p in escolhidas
             if p["componentes"]["potencial_reels"] >= 0.35
             and not any(r["tipo"] in ("tragedia", "saude_mental") for r in p.get("riscos", []))]
    aptas.sort(key=lambda p: -p.get("score_reels", 0))
    para_roteiro = (aptas[: sel["roteiros_por_dia"]]
                    if cfg.get("roteiros", {}).get("ativo", True) else [])
    for p in escolhidas:
        p["virou_roteiro"] = any(x["id"] == p["id"] for x in para_roteiro)

    log(f"editor-chefe: {len(escolhidas)} pautas ({n_br(escolhidas)} BR / "
        f"{len(escolhidas)-n_br(escolhidas)} mundo), {len(para_roteiro)} viram roteiro "
        f"(fila por score_reels), {len(descartadas)} descartadas por repeticao", "agente")

    return {"pautas": escolhidas, "para_roteiro": para_roteiro,
            "reservas": reservas[:60], "descartadas": descartadas[:12],
            "distribuicao_editoria": por_editoria,
            "preferencias_aplicadas": {"temas": prefs.get("temas", []),
                                       "regioes": prefs.get("regioes", []),
                                       "peso": peso_pref}}
