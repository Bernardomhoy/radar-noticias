"""Agente Cacador: busca e normaliza itens de feeds RSS/Atom (so stdlib)."""
from __future__ import annotations

import gzip
import io
import os
import socket
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from .util import (agora_br, dominio, hash_id, iso, limpar_html, log, parse_data)

UA = "Mozilla/5.0 (compatible; RadarNoticiasBR/1.0; +agente-de-curadoria)"
TIMEOUT = 20

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rss1": "http://purl.org/rss/1.0/",
}


def _contexto_ssl() -> ssl.SSLContext:
    """Usa o CA bundle do proxy do ambiente quando existir (nunca desliga verificacao)."""
    for caminho in (os.environ.get("RADAR_CA_BUNDLE"), "/root/.ccr/ca-bundle.crt"):
        if caminho and os.path.exists(caminho):
            try:
                return ssl.create_default_context(cafile=caminho)
            except Exception:
                break
    return ssl.create_default_context()


_CTX = _contexto_ssl()


def baixar(url: str, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
        bruto = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip" or bruto[:2] == b"\x1f\x8b":
            try:
                bruto = gzip.GzipFile(fileobj=io.BytesIO(bruto)).read()
            except OSError:
                pass
        return bruto


def _texto(el, *caminhos: str) -> str:
    for c in caminhos:
        achado = el.find(c, NS) if ":" in c or c.startswith(".") else el.find(c)
        if achado is not None:
            if achado.text and achado.text.strip():
                return limpar_html(achado.text)
            href = achado.get("href")
            if href:
                return href.strip()
    return ""


def _link(el) -> str:
    bruto = _texto(el, "link")
    if bruto.startswith("http"):
        return bruto
    for lk in el.findall("atom:link", NS) + el.findall("link", NS):
        rel = lk.get("rel")
        href = lk.get("href")
        if href and rel in (None, "alternate"):
            return href.strip()
    guid = _texto(el, "guid", "id", "atom:id")
    return guid if guid.startswith("http") else bruto


def parse_feed(bruto: bytes, fonte: dict, url_feed: str) -> list[dict]:
    """Extrai itens de RSS 2.0 / RSS 0.91 / RSS 1.0 (RDF) / Atom."""
    try:
        raiz = ET.fromstring(bruto)
    except ET.ParseError:
        # Alguns veiculos servem XML com lixo antes do prologo.
        corte = bruto.find(b"<?xml")
        if corte > 0:
            try:
                raiz = ET.fromstring(bruto[corte:])
            except ET.ParseError as e:
                raise ValueError(f"xml invalido: {e}") from e
        else:
            raise

    itens = (raiz.findall(".//item") or raiz.findall(".//rss1:item", NS)
             or raiz.findall(".//atom:entry", NS) or raiz.findall(".//entry"))
    saida = []
    for posicao, it in enumerate(itens):
        titulo = _texto(it, "title", "atom:title")
        if not titulo:
            continue
        link = _link(it)
        resumo = _texto(it, "description", "atom:summary", "summary", "content:encoded",
                        "atom:content", "content")
        data_txt = _texto(it, "pubDate", "atom:published", "published", "atom:updated",
                          "updated", "dc:date", "date")
        dt = parse_data(data_txt)
        saida.append({
            "id": hash_id(fonte["id"], titulo[:160]),
            "titulo": limpar_html(titulo),
            "resumo": limpar_html(resumo)[:600],
            "url": link,
            "fonte_id": fonte["id"],
            "fonte": fonte["nome"],
            "peso_fonte": fonte.get("peso", 0.7),
            "pais": fonte.get("pais", "BR"),
            "idioma": fonte.get("idioma", "pt"),
            "editoria_fonte": fonte.get("editoria", "geral"),
            "publicado_em": iso(dt) if dt else None,
            "coletado_em": iso(agora_br()),
            "origem": "rss",
            "feed": url_feed,
            "dominio": dominio(link),
            # Feed e lista em ordem inversa de publicacao: a posicao serve de
            # proxy de recencia quando o item vem sem data.
            "ordem": posicao,
        })
    return saida


def coletar_feed(fonte: dict, url: str) -> tuple[list[dict], str | None]:
    try:
        bruto = baixar(url)
        return parse_feed(bruto, fonte, url), None
    except urllib.error.HTTPError as e:
        return [], f"HTTP {e.code}"
    except urllib.error.URLError as e:
        motivo = getattr(e, "reason", e)
        return [], f"rede: {motivo}"
    except (socket.timeout, TimeoutError):
        return [], "timeout"
    except Exception as e:  # xml quebrado, encoding exotico etc
        return [], f"{type(e).__name__}: {e}"


def coletar(fontes: list[dict], janela_horas: int = 30, paralelas: int = 12) -> dict:
    """Roda todos os feeds em paralelo. Devolve itens + diagnostico por fonte."""
    tarefas = [(f, u) for f in fontes for u in f.get("rss", [])]
    itens: list[dict] = []
    diag: list[dict] = []
    log(f"cacador: {len(tarefas)} feeds de {len(fontes)} fontes", "agente")

    with ThreadPoolExecutor(max_workers=paralelas) as pool:
        futuros = {pool.submit(coletar_feed, f, u): (f, u) for f, u in tarefas}
        for fut in as_completed(futuros):
            fonte, url = futuros[fut]
            try:
                achados, erro = fut.result()
            except Exception as e:
                achados, erro = [], f"falha inesperada: {e}"
            diag.append({"fonte": fonte["nome"], "feed": url,
                         "itens": len(achados), "erro": erro})
            if erro:
                log(f"  x {fonte['nome']}: {erro}", "aviso")
            else:
                log(f"  + {fonte['nome']}: {len(achados)} itens", "ok")
            itens.extend(achados)

    for n, it in enumerate(itens):
        it.setdefault("ordem", n)
    ok = sum(1 for d in diag if not d["erro"])
    log(f"cacador: {len(itens)} itens lidos "
        f"({ok}/{len(diag)} feeds responderam)", "agente")
    return {"itens": itens, "diagnostico": diag,
            "feeds_ok": ok, "feeds_total": len(diag)}


def filtrar_janela(itens: list[dict], horas: int, exigir_data: bool = False,
                   relatorio: dict | None = None) -> list[dict]:
    """Mantem so o que foi publicado nas ultimas `horas`.

    Com exigir_data, item sem data fica de fora: sem data nao ha como garantir
    que a materia e atual. `relatorio`, se vier, recebe a contagem dos descartes.
    """
    corte = agora_br() - timedelta(hours=horas)
    out, velhos, sem_data = [], 0, 0
    for i in itens:
        dt = parse_data(i.get("publicado_em"))
        if dt is None:
            if exigir_data:
                sem_data += 1
                continue
            out.append(i)
        elif dt >= corte:
            out.append(i)
        else:
            velhos += 1
    if relatorio is not None:
        relatorio["fora_da_janela"] = relatorio.get("fora_da_janela", 0) + velhos
        relatorio["sem_data"] = relatorio.get("sem_data", 0) + sem_data
    return out
