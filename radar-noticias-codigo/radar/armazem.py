"""Memoria do radar: SQLite com historico de itens, pautas e roteiros.

Serve a dois propositos: evitar repetir pauta que ja virou reels nos ultimos
dias e permitir medir "calor" (quantas materias novas a pauta ganhou por hora).
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import timedelta

from .util import RAIZ, agora_br, iso, log, parse_data

CAMINHO_BANCO = os.path.join(RAIZ, "dados", "radar.db")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS itens (
  id TEXT PRIMARY KEY, titulo TEXT NOT NULL, url TEXT, fonte_id TEXT, fonte TEXT,
  pais TEXT, publicado_em TEXT, coletado_em TEXT, visto_em TEXT, dados TEXT
);
CREATE INDEX IF NOT EXISTS ix_itens_visto ON itens(visto_em);
CREATE TABLE IF NOT EXISTS pautas (
  slug TEXT, dia TEXT, titulo TEXT, score REAL, editoria TEXT, pais TEXT,
  virou_roteiro INTEGER DEFAULT 0, dados TEXT, PRIMARY KEY (slug, dia)
);
CREATE INDEX IF NOT EXISTS ix_pautas_dia ON pautas(dia);
CREATE TABLE IF NOT EXISTS roteiros (
  id TEXT PRIMARY KEY, dia TEXT, slug TEXT, titulo TEXT, duracao_s REAL, dados TEXT
);
CREATE TABLE IF NOT EXISTS execucoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, iniciado_em TEXT, itens INTEGER,
  pautas INTEGER, roteiros INTEGER, feeds_ok INTEGER, feeds_total INTEGER, dados TEXT
);
"""


class Armazem:
    def __init__(self, caminho: str = CAMINHO_BANCO):
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        self.con = sqlite3.connect(caminho)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)
        self.con.commit()

    # ---------- itens ----------
    def registrar_itens(self, itens: list[dict]) -> int:
        """Grava itens novos. Devolve quantos eram ineditos."""
        agora = iso(agora_br())
        novos = 0
        for i in itens:
            cur = self.con.execute("SELECT 1 FROM itens WHERE id = ?", (i["id"],))
            if cur.fetchone():
                continue
            self.con.execute(
                "INSERT INTO itens (id,titulo,url,fonte_id,fonte,pais,publicado_em,coletado_em,visto_em,dados)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (i["id"], i["titulo"], i.get("url"), i.get("fonte_id"), i.get("fonte"),
                 i.get("pais"), i.get("publicado_em"), i.get("coletado_em"), agora,
                 json.dumps(i, ensure_ascii=False)))
            novos += 1
        self.con.commit()
        return novos

    def ids_conhecidos(self, itens: list[dict]) -> set[str]:
        if not itens:
            return set()
        marcas = ",".join("?" * len(itens))
        cur = self.con.execute(f"SELECT id FROM itens WHERE id IN ({marcas})",
                               [i["id"] for i in itens])
        return {r["id"] for r in cur.fetchall()}

    # ---------- pautas ----------
    def pautas_recentes(self, dias: int) -> list[dict]:
        """Pautas dos ultimos N dias, sem contar o dia de hoje.

        Hoje fica de fora de proposito: rodar o radar duas vezes na mesma manha
        tem de devolver o mesmo briefing, e nao um briefing esvaziado porque a
        primeira rodada ja tinha "usado" as pautas.
        """
        hoje = agora_br().date().isoformat()
        corte = (agora_br() - timedelta(days=dias)).date().isoformat()
        cur = self.con.execute(
            "SELECT slug,dia,titulo,score,editoria,virou_roteiro FROM pautas"
            " WHERE dia >= ? AND dia < ? ORDER BY dia DESC", (corte, hoje))
        return [dict(r) for r in cur.fetchall()]

    def registrar_pautas(self, pautas: list[dict], dia: str) -> None:
        for p in pautas:
            self.con.execute(
                "INSERT OR REPLACE INTO pautas (slug,dia,titulo,score,editoria,pais,virou_roteiro,dados)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (p["slug"], dia, p["titulo"], p.get("score", 0), p.get("editoria"),
                 p.get("pais"), 1 if p.get("virou_roteiro") else 0,
                 json.dumps(p, ensure_ascii=False)))
        self.con.commit()

    def registrar_roteiros(self, roteiros: list[dict], dia: str) -> None:
        for r in roteiros:
            self.con.execute(
                "INSERT OR REPLACE INTO roteiros (id,dia,slug,titulo,duracao_s,dados)"
                " VALUES (?,?,?,?,?,?)",
                (r["id"], dia, r["slug"], r["titulo_pauta"], r.get("duracao_s"),
                 json.dumps(r, ensure_ascii=False)))
        self.con.commit()

    def registrar_execucao(self, resumo: dict) -> None:
        self.con.execute(
            "INSERT INTO execucoes (iniciado_em,itens,pautas,roteiros,feeds_ok,feeds_total,dados)"
            " VALUES (?,?,?,?,?,?,?)",
            (resumo.get("iniciado_em"), resumo.get("itens", 0), resumo.get("pautas", 0),
             resumo.get("roteiros", 0), resumo.get("feeds_ok", 0),
             resumo.get("feeds_total", 0), json.dumps(resumo, ensure_ascii=False)))
        self.con.commit()

    def reidratar(self, dir_saida: str) -> int:
        """Reconstroi a memoria de pautas a partir dos radar.json ja publicados.

        O banco nao viaja entre execucoes em maquinas diferentes (container novo
        a cada manha, por exemplo). Os briefings, sim - eles ficam versionados.
        Sem isso, a anti-repeticao de 5 dias nunca pegaria nada.
        """
        import glob

        if self.con.execute("SELECT COUNT(*) FROM pautas").fetchone()[0]:
            return 0
        recuperadas = 0
        for caminho in sorted(glob.glob(os.path.join(dir_saida, "*", "radar.json"))):
            try:
                with open(caminho, "r", encoding="utf-8") as fh:
                    radar = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            dia = radar.get("dia")
            pautas = radar.get("pautas") or []
            if not dia or not pautas:
                continue
            self.registrar_pautas(pautas, dia)
            recuperadas += len(pautas)
        if recuperadas:
            log(f"memória: {recuperadas} pautas recuperadas dos briefings anteriores", "info")
        return recuperadas

    def estatisticas(self) -> dict:
        def um(sql):
            return self.con.execute(sql).fetchone()[0]
        return {
            "itens": um("SELECT COUNT(*) FROM itens"),
            "pautas": um("SELECT COUNT(*) FROM pautas"),
            "roteiros": um("SELECT COUNT(*) FROM roteiros"),
            "execucoes": um("SELECT COUNT(*) FROM execucoes"),
        }

    def fechar(self):
        self.con.close()
