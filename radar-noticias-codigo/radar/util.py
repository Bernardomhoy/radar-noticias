"""Utilidades compartilhadas: texto, datas, log e io."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUSO_BR = timezone(timedelta(hours=-3))

# Palavras sem valor semantico para dedupe/cluster (pt + en + es).
STOPWORDS = set("""
a ao aos as à às até com como da das de dela dele deles do dos e em entre era eram essa esse esta este eu foi for foram
ha isso isto ja la lhe lo mais mas me mesmo meu minha muito na nao nas nem no nos nossa num numa o os ou para pela pelas
pelo pelos per pode por porque qual quando que quem se sem ser seu sua suas seus so sobre sua tambem te tem tinha um uma
umas uns vai vao ver vez voce apos contra desde ante sob sobre tras durante segundo mediante salvo exceto
the a an and or of to in for on at by with from as is are was were be been being this that these those it its has have
had will would can could should may might do does did not no nor but if then than there their them they he she his her
el la los las de del y o en para por con sin sobre que se al un una es son fue fueron
diz dizem apos agora hoje ontem amanha ainda vai nova novo novos novas apenas deve teve
""".split())

# Pistas de entidade: palavras com inicial maiuscula que nao sao inicio de frase.
_RE_TAG = re.compile(r"<[^>]+>")
_RE_ESPACO = re.compile(r"\s+")
_RE_NAO_PALAVRA = re.compile(r"[^0-9a-zà-ÿ ]", re.IGNORECASE)


def agora_br() -> datetime:
    return datetime.now(FUSO_BR)


def iso(dt: datetime) -> str:
    return dt.astimezone(FUSO_BR).isoformat(timespec="seconds")


def limpar_html(texto: str) -> str:
    if not texto:
        return ""
    import html as _html

    t = _RE_TAG.sub(" ", texto)
    t = _html.unescape(t)
    return _RE_ESPACO.sub(" ", t).strip()


def sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """minusculas, sem acento, sem pontuacao - base para comparacao."""
    t = sem_acento(limpar_html(texto or "")).lower()
    t = _RE_NAO_PALAVRA.sub(" ", t)
    return _RE_ESPACO.sub(" ", t).strip()


def tokens(texto: str, min_len: int = 3) -> list[str]:
    return [p for p in normalizar(texto).split() if len(p) >= min_len and p not in STOPWORDS]


def tokens_uteis(texto: str) -> set[str]:
    """Tokens relevantes: inclui numeros com 2+ digitos (datas, valores, placares)."""
    brutos = normalizar(texto).split()
    out = set()
    for p in brutos:
        if p in STOPWORDS:
            continue
        if p.isdigit() and len(p) >= 2:
            out.add(p)
        elif len(p) >= 4:
            out.add(p)
    return out


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


def entidades_seq(titulo: str) -> list[str]:
    """Nomes proprios aproximados, na ordem em que aparecem (preserva 'Sao Paulo')."""
    bruto = limpar_html(titulo)
    palavras = re.findall(r"[A-ZÀ-Ý][\wÀ-ÿ'-]{2,}|\b[A-Z]{2,6}\b", bruto)
    out = []
    for p in palavras:
        n = sem_acento(p).lower()
        if n in STOPWORDS or len(n) < 2:
            continue
        out.append(n)
    return out


def entidades(titulo: str) -> set[str]:
    return {e for e in entidades_seq(titulo) if len(e) >= 3}


def hash_id(*partes: str) -> str:
    h = hashlib.sha1("||".join(partes).encode("utf-8", "replace")).hexdigest()
    return h[:16]


def slug(texto: str, limite: int = 60) -> str:
    s = normalizar(texto).replace(" ", "-")
    return s[:limite].strip("-") or "pauta"


def parse_data(valor: str | None) -> datetime | None:
    if not valor:
        return None
    valor = valor.strip()
    try:
        d = parsedate_to_datetime(valor)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.strptime(valor.replace("Z", "+0000") if fmt.endswith("%z") else valor, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d
        except Exception:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", valor)
    if m:
        return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
    return None


def dominio(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return (m[1].lower().replace("www.", "") if m else "")


def ler_json(caminho: str, padrao=None):
    try:
        with open(caminho, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return padrao
    except json.JSONDecodeError as e:
        log(f"json invalido em {caminho}: {e}", "erro")
        return padrao


def escrever_json(caminho: str, dados) -> None:
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, ensure_ascii=False, indent=2)


_CORES = {"info": "\033[36m", "ok": "\033[32m", "aviso": "\033[33m", "erro": "\033[31m", "agente": "\033[35m"}


def log(msg: str, nivel: str = "info") -> None:
    cor = _CORES.get(nivel, "")
    fim = "\033[0m" if cor else ""
    hora = agora_br().strftime("%H:%M:%S")
    print(f"{cor}[{hora}] {msg}{fim}", file=sys.stderr)


# --------------------------------------------------------------------------
# Canonicalizacao e radicais: fazem "IR" casar com "Imposto de Renda" e
# "fechou" casar com "fecha" sem precisar de embeddings.
# --------------------------------------------------------------------------
_SINONIMOS: dict | None = None


def _sinonimos() -> dict:
    global _SINONIMOS
    if _SINONIMOS is None:
        caminho = os.path.join(RAIZ, "config", "sinonimos.json")
        dados = ler_json(caminho, {}) or {}
        _SINONIMOS = {"frases": dados.get("frases", {}), "termos": dados.get("termos", {})}
    return _SINONIMOS


def canonizar(texto: str) -> str:
    """Texto normalizado com frases e termos equivalentes trocados pelo canonico."""
    t = " " + normalizar(texto) + " "
    sin = _sinonimos()
    for frase, canon in sin["frases"].items():
        if frase in t:
            t = t.replace(frase, canon)
    palavras = []
    termos = sin["termos"]
    for p in t.split():
        palavras.append(termos.get(p, p))
    return " ".join(palavras)


def radical(palavra: str) -> str:
    """Radical aproximado para portugues/ingles: corta em 6 e tira vogal final."""
    if palavra.isdigit():
        return palavra
    p = palavra
    if len(p) > 4 and p.endswith("s"):
        p = p[:-1]
    p = p[:6]
    while len(p) > 4 and p[-1] in "aeiou":
        p = p[:-1]
    return p


def tokens_canon(texto: str) -> set[str]:
    """Conjunto de radicais canonicos - base da comparacao entre materias."""
    out = set()
    for p in canonizar(texto).split():
        if p in STOPWORDS:
            continue
        if p.isdigit():
            if len(p) >= 2 or p in {"5", "4", "6"}:
                out.add(p)
            continue
        if len(p) >= 3:
            out.add(radical(p))
    return out


def entidades_canon(titulo: str) -> set[str]:
    """Entidades canonizadas em sequencia: 'Sao Paulo' vira um token so."""
    seq = " ".join(entidades_seq(titulo))
    out = set()
    for parte in canonizar(seq).split():
        if parte and parte not in STOPWORDS and len(parte) >= 2:
            out.add(radical(parte))
    return out


def overlap(a: set, b: set) -> float:
    """Coeficiente de sobreposicao - tolera titulos de tamanhos bem diferentes."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# Palavras de funcao usadas para decidir o idioma de um trecho curto. Nao e um
# detector de idioma de verdade - e o suficiente para manchete e linha de resumo.
_FUNC_PT = {"de", "que", "do", "da", "em", "para", "nao", "com", "uma", "por", "no",
            "na", "dos", "das", "ao", "aos", "mais", "ja", "sobre", "sera", "deve",
            "foi", "apos", "entre", "pelo", "pela", "seu", "sua", "como", "ate",
            "quem", "sem", "disse", "ainda", "cada", "onde", "nesta", "neste"}
_FUNC_EN = {"the", "of", "to", "in", "and", "for", "is", "are", "on", "says", "said",
            "with", "at", "from", "by", "as", "that", "it", "its", "his", "her",
            "after", "over", "how", "why", "what", "will", "has", "have", "be",
            "but", "they", "their", "this", "was", "were", "who", "amid"}


def parece_portugues(texto: str) -> bool:
    """True quando o trecho parece estar em portugues (ou quando nao da para dizer).

    Na duvida devolve True de proposito: marcar um texto que ja esta em portugues
    como "traduzir" e pior do que deixar passar um trecho curto ambiguo.
    """
    toks = normalizar(texto).split()
    if not toks:
        return True
    pt = sum(1 for t in toks if t in _FUNC_PT)
    en = sum(1 for t in toks if t in _FUNC_EN)
    if pt == 0 and en == 0:
        return True
    return pt >= en
