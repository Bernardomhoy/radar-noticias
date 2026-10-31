"""Carrega o registro de fontes e permite filtros por pais/editoria."""
from __future__ import annotations

import os

from .util import RAIZ, ler_json, log

CAMINHO_FONTES = os.path.join(RAIZ, "config", "fontes.json")
CAMINHO_CONFIG = os.path.join(RAIZ, "config", "config.json")
CAMINHO_PREFS = os.path.join(RAIZ, "config", "preferencias.json")
CAMINHO_REGIOES = os.path.join(RAIZ, "config", "regioes.json")


def carregar_config() -> dict:
    cfg = ler_json(CAMINHO_CONFIG)
    if not cfg:
        raise SystemExit(f"config nao encontrada em {CAMINHO_CONFIG}")
    return cfg


def carregar_fontes(pais: str | None = None, so_ids: list[str] | None = None) -> list[dict]:
    reg = ler_json(CAMINHO_FONTES) or {}
    fontes = [f for f in reg.get("fontes", []) if f.get("ativo", True)]
    if not fontes:
        raise SystemExit(f"nenhuma fonte em {CAMINHO_FONTES}")
    if pais:
        fontes = [f for f in fontes if f["pais"] == pais.upper()]
    if so_ids:
        alvo = set(so_ids)
        fontes = [f for f in fontes if f["id"] in alvo]
    return fontes


def carregar_preferencias() -> dict:
    """Interesses do leitor. Ausente ou vazio = radar padrao."""
    p = ler_json(CAMINHO_PREFS) or {}
    return {"temas": [t.lower() for t in p.get("temas") or []],
            "regioes": [r.lower() for r in p.get("regioes") or []],
            "peso": float(p.get("peso", 0.35)),
            "atualizado_em": p.get("atualizado_em")}


def carregar_regioes() -> dict[str, list[str]]:
    return (ler_json(CAMINHO_REGIOES) or {}).get("regioes", {})


def mapa_fontes() -> dict[str, dict]:
    return {f["id"]: f for f in carregar_fontes()}


def dominios_confiaveis() -> list[str]:
    """Dominios usados para restringir busca na web (camada do agente)."""
    extras = ["g1.globo.com", "folha.uol.com.br", "estadao.com.br", "uol.com.br",
              "agenciabrasil.ebc.com.br", "cnnbrasil.com.br", "poder360.com.br",
              "infomoney.com.br", "valor.globo.com", "exame.com", "nexojornal.com.br",
              "bbc.com", "reuters.com", "apnews.com", "theguardian.com",
              "aljazeera.com", "elpais.com", "nytimes.com", "techcrunch.com",
              "theverge.com", "arstechnica.com", "nature.com", "cnbc.com",
              "gov.br", "bcb.gov.br", "ibge.gov.br"]
    return extras
