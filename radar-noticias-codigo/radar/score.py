"""Agente Curador (parte 2): pontua cada pauta e explica a nota.

Cinco sinais, todos de 0 a 1, combinados com os pesos de config.json:

  corroboracao    quantos veiculos distintos cobriram (sinal de que a pauta e real)
  peso_fonte      credibilidade media dos veiculos que publicaram
  recencia        quao fresca e a materia mais nova
  calor           ritmo de publicacao (materias por hora) - pauta em ebulicao
  potencial_reels afinidade com video curto (bolso, utilidade, conflito, espanto, numero)

O score final e 0-100 e vem sempre acompanhado de `explicacao`, para a escolha
nunca ser uma caixa-preta.
"""
from __future__ import annotations

import math
import re

from .util import agora_br, canonizar, normalizar, parse_data

# ---------------------------------------------------------------- lexicos de reels
# Peso de cada familia de gancho. Deliberadamente abaixo de 1.0: os bonus
# (percentual, dinheiro, pauta nacional) e que diferenciam pautas do mesmo tipo.
# Com familia valendo 1.0, tudo que mexia no bolso empatava no teto.
GANCHOS = {
    "bolso": (0.82, ["dolar", "inflacao", "juros", "imposto", "impostorenda", "salariominimo",
                     "salario", "gasolina", "combustivel", "energia", "conta", "preco",
                     "precos", "aumento", "reajuste", "tarifa", "inss", "fgts", "pix",
                     "beneficio", "bolsa familia", "aposentadoria", "cesta basica",
                     "financiamento", "credito", "divida", "taxa", "isencao", "desconto",
                     "custo", "mercado", "emprego", "vaga", "vagas", "concurso"]),
    "utilidade": (0.76, ["muda", "mudanca", "passa a valer", "nova regra", "regra", "prazo",
                         "comeca", "termina", "calendario", "direito", "como", "quem tem",
                         "quem pode", "liberado", "liberada", "cadastro", "inscricao",
                         "aprovado", "sancionada", "lei", "obrigatorio", "proibido",
                         "vai custar", "passa a", "entra em vigor"]),
    "espanto": (0.72, ["inedito", "recorde", "primeira vez", "maior", "pior", "historico",
                       "surpresa", "inesperado", "revela", "descoberta", "estudo", "nunca",
                       "pela primeira", "disparou", "despencou", "triplicou", "dobrou",
                       "bateu", "alerta", "raro", "gigante", "misterio"]),
    "conflito": (0.68, ["crise", "acusa", "denuncia", "renuncia", "demite", "demissao",
                        "protesto", "greve", "guerra", "ataque", "conflito", "operacao",
                        "prisao", "preso", "investigacao", "cpi", "escandalo", "polemica",
                        "briga", "rompe", "veta", "derrota", "pressao", "tensao",
                        "sancao", "retaliacao", "bloqueio"]),
    # "meta" (empresa) e "dados" ficaram de fora de proposito: casavam com
    # "meta de inflacao" e "dados do TSE" e jogavam pauta de economia/politica
    # para a familia de tecnologia.
    "tecnologia": (0.66, ["ia", "openai", "chatgpt", "gemini", "google", "apple", "nvidia",
                          "robo", "aplicativo", "app", "celular", "smartphone", "golpe",
                          "hacker", "vazamento de dados", "automacao", "chip", "software",
                          "rede social", "tiktok", "instagram", "whatsapp", "deepfake",
                          "meta plataformas", "inteligencia artificial"]),
    "humano": (0.60, ["familia", "crianca", "mae", "pai", "idoso", "mulher", "jovem",
                      "estudante", "trabalhador", "aposentado", "morador", "vitima",
                      "sobrevivente", "resgate", "heroi", "emocionante"]),
    "cultura_pop": (0.56, ["show", "turne", "filme", "serie", "netflix", "album", "cantor",
                           "cantora", "ator", "atriz", "novela", "bbb", "oscar", "grammy",
                           "viral", "influenciador", "youtuber", "selecao", "copa",
                           "final", "titulo", "neymar"]),
}

# Pautas que rendem pouco em video curto.
FREIOS = [
    (0.55, ["agenda do dia", "nota oficial", "balanco trimestral", "ata do", "errata",
            "veja a lista completa", "confira a programacao", "edital", "licitacao",
            "ranking de", "resultado do sorteio", "previsao do tempo para"]),
    (0.75, ["entrevista exclusiva", "artigo", "opiniao", "coluna", "analise", "editorial",
            "obituario", "morre aos", "escalacao", "provaveis times", "onde assistir",
            "classificacao da rodada"]),
]

# Pautas que exigem cuidado editorial explicito no roteiro.
RISCOS = {
    "tragedia": ["morte", "morreu", "morrem", "mortos", "vitimas", "acidente", "desastre",
                 "tragedia", "assassinato", "feminicidio", "chacina", "suicidio", "killed"],
    "saude_mental": ["suicidio", "automutilacao", "depressao", "transtorno"],
    "menores": ["crianca", "criancas", "adolescente", "menor de idade", "bebe", "aluno"],
    "judicial": ["investigado", "acusado", "suspeito", "indiciado", "reu", "denunciado",
                 "preso", "operacao"],
    "eleitoral": ["eleicao", "candidato", "urna", "turno", "campanha", "pesquisa eleitoral"],
    "saude_publica": ["vacina", "surto", "epidemia", "medicamento", "tratamento", "cura"],
    "mercado": ["acao", "acoes", "investimento", "cripto", "bitcoin", "renda fixa"],
}

AVISOS_RISCO = {
    "tragedia": "Pauta com vítimas: tom sóbrio, sem trilha animada e sem close em dor alheia.",
    "saude_mental": "Tema sensível: não detalhe método e deixe o CVV 188 na tela.",
    "menores": "Envolve menores: não exponha rosto nem nome.",
    "judicial": "Há investigação em curso: fale \"suspeito de\", \"segundo a polícia\" — "
                "nunca afirme culpa.",
    "eleitoral": "Conteúdo eleitoral: cite a fonte do dado, separe fato de opinião e "
                 "evite propaganda.",
    "saude_publica": "Saúde: cite o órgão (Anvisa, Ministério da Saúde) e não dê "
                     "recomendação médica.",
    "mercado": "Financeiro: não é recomendação de investimento — diga isso na tela.",
}

# Fator aplicado ao potencial de reels em pautas sensiveis (contencao editorial).
CONTENCAO = {"tragedia": 0.62, "saude_mental": 0.45, "menores": 0.70}

_RE_NUMERO = re.compile(r"\d")
_RE_PERCENT = re.compile(r"\d[\d.,]*\s?%")
_RE_DINHEIRO = re.compile(r"(r\$|us\$|€)\s?\d|(\d[\d.,]*\s?(mil|milh|bilh|tri))", re.I)
_RE_FIM_PONTUACAO = re.compile(r"[.,;:]+$")


def _contem(texto: str, termos: list[str]) -> list[str]:
    """Casa por palavra inteira (ou frase inteira), nunca por pedaco de palavra.

    Sem isso, "escalacao" casaria com "acao" e viraria pauta de mercado.
    """
    palavras = set(texto.split())
    achados = []
    for t in termos:
        if " " in t:
            if f" {t} " in texto:
                achados.append(t)
        elif t in palavras:
            achados.append(t)
    return achados


def potencial_reels(pauta: dict) -> tuple[float, dict]:
    """0-1 de afinidade com video curto, com os motivos."""
    base = f"{pauta['titulo']} {pauta.get('resumo', '')}"
    t = " " + normalizar(base) + " " + canonizar(base) + " "

    familias: dict[str, list[str]] = {}
    for nome, (_peso, termos) in GANCHOS.items():
        achados = _contem(t, termos)
        if achados:
            familias[nome] = achados[:4]

    # A familia mais forte define a base; cada familia extra soma pouco (evita inflar).
    if familias:
        pesos_achados = sorted((GANCHOS[n][0] for n in familias), reverse=True)
        nota = pesos_achados[0] + sum(p * 0.10 for p in pesos_achados[1:])
    else:
        nota = 0.0
    nota = min(nota, 1.0)

    bonus = {}
    if _RE_PERCENT.search(base):
        nota += 0.08
        bonus["percentual"] = True
    elif _RE_NUMERO.search(pauta["titulo"]):
        nota += 0.05
        bonus["numero_no_titulo"] = True
    if _RE_DINHEIRO.search(base):
        nota += 0.07
        bonus["valor_em_dinheiro"] = True
    if pauta.get("pais") == "BR":
        nota += 0.05
        bonus["pauta_nacional"] = True
    if len(pauta["titulo"]) > 120:
        nota -= 0.05
        bonus["titulo_longo"] = True

    freio_aplicado = None
    for fator, termos in FREIOS:
        achados = _contem(t, termos)
        if achados:
            nota *= fator
            freio_aplicado = {"fator": fator, "termos": achados[:3]}
            break

    # Pauta sensivel nao deve liderar a fila de reels so por estar quente.
    # Ela continua no briefing; o que cai e a prioridade de virar video.
    sensiveis = [r["tipo"] for r in riscos(pauta) if r["tipo"] in CONTENCAO]
    if sensiveis:
        fator = min(CONTENCAO[s_] for s_ in sensiveis)
        nota *= fator
        freio_aplicado = {"fator": fator, "termos": sensiveis,
                          "motivo": "contencao editorial"}

    nota = max(0.0, min(nota, 1.0))
    return nota, {"familias": familias, "bonus": bonus, "freio": freio_aplicado}


def riscos(pauta: dict) -> list[dict]:
    base = " " + normalizar(f"{pauta['titulo']} {pauta.get('resumo','')}") + " "
    out = []
    for nome, termos in RISCOS.items():
        if _contem(base, termos):
            out.append({"tipo": nome, "aviso": AVISOS_RISCO[nome]})
    return out


def _recencia(pauta: dict) -> float:
    """1.0 agora; ~0.6 em 6h; ~0.3 em 18h. Sem data informada vira 0.5 (neutro)."""
    dt = parse_data(pauta.get("ultima_publicacao"))
    if not dt:
        return 0.50
    horas = max((agora_br() - dt).total_seconds() / 3600.0, 0.0)
    return max(0.0, min(1.0, math.exp(-horas / 12.0)))


def _corroboracao(pauta: dict) -> float:
    n = pauta.get("n_fontes", 1)
    return min(1.0, math.log(1 + n) / math.log(6))  # 1 fonte=0.39, 3=0.77, 5+=1.0


def _peso_fonte(pauta: dict, pesos_por_fonte: dict[str, float]) -> float:
    vals = [pesos_por_fonte.get(m["fonte"], 0.7) for m in pauta.get("materias", [])]
    if not vals:
        return 0.7
    return max(vals) * 0.6 + (sum(vals) / len(vals)) * 0.4


def _calor(pauta: dict) -> float:
    """Quanto a pauta esta fervendo: volume de materias e, quando da, o ritmo.

    Volume pesa mais que ritmo de proposito: tres materias em doze horas e uma
    pauta real; uma materia sozinha nao e, mesmo que tenha acabado de sair.
    """
    n = pauta.get("n_itens", 1)
    volume = min(1.0, math.log(1 + n) / math.log(5))
    vel = pauta.get("velocidade")
    if vel is None:
        ritmo = 0.40  # sem datas suficientes para medir ritmo
    else:
        ritmo = min(1.0, math.log(1 + vel) / math.log(5))
    return 0.62 * volume + 0.38 * ritmo


def pontuar(pauta: dict, cfg: dict, pesos_por_fonte: dict[str, float]) -> dict:
    """Calcula os dois scores da pauta e deixa a conta explicada.

    score_noticia -> importancia jornalistica (ordena o briefing)
    score_reels   -> o que rende video curto (ordena a fila de gravacao)
    """
    comp = {
        "corroboracao": round(_corroboracao(pauta), 3),
        "peso_fonte": round(_peso_fonte(pauta, pesos_por_fonte), 3),
        "recencia": round(_recencia(pauta), 3),
        "calor": round(_calor(pauta), 3),
    }
    pr, detalhe = potencial_reels(pauta)
    comp["potencial_reels"] = round(pr, 3)

    pn = cfg["pesos_noticia"]
    pandr = cfg["pesos_reels"]
    score_noticia = sum(comp[k] * w for k, w in pn.items()) * 100
    score_reels = sum(comp[k] * w for k, w in pandr.items()) * 100

    pauta["score_noticia"] = round(score_noticia, 1)
    pauta["score_reels"] = round(score_reels, 1)
    pauta["score"] = pauta["score_noticia"]  # ordenacao padrao: valor jornalistico
    pauta["componentes"] = comp
    pauta["reels_detalhe"] = detalhe
    pauta["riscos"] = riscos(pauta)
    pauta["explicacao"] = explicar(pauta, comp, detalhe, pn)
    pauta["explicacao_reels"] = explicar_reels(pauta, comp, detalhe)
    return pauta


def _rotulo_recencia(pauta: dict, v: float) -> str:
    if not pauta.get("ultima_publicacao"):
        return "sem data informada pela fonte"
    if v > 0.8:
        return "publicada nas últimas horas"
    if v > 0.45:
        return "ainda fresca"
    return "já esfriando"


def _rotulo_calor(pauta: dict) -> str:
    n = pauta.get("n_itens", 1)
    if n <= 1:
        return "matéria isolada, sem repercussão ainda"
    datadas = pauta.get("datas_conhecidas", 0)
    if pauta.get("velocidade") and datadas >= n:
        return f"{n} matérias em {pauta.get('janela_horas')}h"
    return f"{n} matérias sobre o mesmo fato"


def _rotulo_fontes(pauta: dict) -> str:
    n = pauta.get("n_fontes", 1)
    if n == 1:
        return f"só {pauta.get('fonte_principal','um veículo')} publicou"
    return f"{n} veículos cobrindo"


def explicar(pauta: dict, comp: dict, detalhe: dict, pesos: dict) -> str:
    """Explica o score jornalístico pelos três sinais que mais pesaram."""
    rotulos = {
        "corroboracao": lambda v: _rotulo_fontes(pauta),
        "peso_fonte": lambda v: f"peso de fonte alto ({pauta.get('fonte_principal','?')})"
        if v > 0.85 else f"fonte {pauta.get('fonte_principal','?')}",
        "recencia": lambda v: _rotulo_recencia(pauta, v),
        "calor": lambda v: _rotulo_calor(pauta),
        "potencial_reels": lambda v: "rende reels: " + ", ".join(detalhe["familias"].keys())
        if detalhe["familias"] else "pouco apelo de vídeo curto",
    }
    ordenado = sorted(((k, v) for k, v in comp.items() if k in pesos),
                      key=lambda kv: kv[1] * pesos[kv[0]], reverse=True)
    return "; ".join(rotulos[k](v) for k, v in ordenado[:3])


def explicar_reels(pauta: dict, comp: dict, detalhe: dict) -> str:
    """Explica por que (ou por que não) a pauta rende vídeo curto."""
    fam = list(detalhe["familias"].keys())
    if fam:
        base = "gancho de " + ", ".join(fam)
    else:
        base = "sem gancho claro de vídeo curto"
    extras = []
    b = detalhe.get("bonus", {})
    if b.get("percentual"):
        extras.append("tem percentual para o primeiro frame")
    elif b.get("numero_no_titulo"):
        extras.append("tem número no título")
    if b.get("valor_em_dinheiro"):
        extras.append("tem valor em dinheiro")
    if b.get("pauta_nacional"):
        extras.append("pauta nacional")
    fr = detalhe.get("freio")
    if fr:
        motivo = fr.get("motivo") or f"termo \"{fr['termos'][0]}\""
        extras.append(f"freio de {fr['fator']:.2f} ({motivo})")
    return base + ("; " + "; ".join(extras) if extras else "")
