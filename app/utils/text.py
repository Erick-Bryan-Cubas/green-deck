import re
from typing import List, Literal
from app.config import MAX_SOURCE_CHARS

LangHint = Literal["pt-br", "en", "unknown"]


def truncate_source(text: str, limit: int = MAX_SOURCE_CHARS) -> str:
    """
    Normaliza o texto-fonte para uso no prompt e validações.

    Nota:
        O parâmetro `limit` existe para compatibilidade com chamadas antigas.
        Se você quiser realmente truncar pelo limite, implemente aqui.
    """
    return (text or "").strip()


def guess_language_ptbr_en(text: str, *, min_hits: int = 3, margin: int = 2) -> LangHint:
    """
    Heurística simples para inferir se um texto parece estar em PT-BR ou Inglês.

    Esta função NÃO é um detector de idioma completo; ela só tenta distinguir:
      - "pt-br": quando há indícios fortes de português (Brasil)
      - "en": quando há indícios fortes de inglês
      - "unknown": quando não dá para ter confiança (texto curto, misto, técnico demais etc.)

    Como funciona:
      - Tokeniza palavras (inclui acentos).
      - Conta ocorrências de “palavras-função” (stopwords) típicas de cada idioma.
      - Decide por maioria com uma margem mínima (para reduzir falso positivo).

    Args:
        text: Texto a ser analisado.
        min_hits: Número mínimo de ocorrências de marcadores para considerar um idioma.
        margin: Diferença mínima entre os scores para “ganhar” a decisão.

    Returns:
        "pt-br", "en" ou "unknown".
    """
    s = (text or "").strip().lower()
    if not s:
        return "unknown"

    # Captura palavras com letras ASCII + latinas acentuadas
    tokens = re.findall(r"[a-zA-ZÀ-ÿ]+", s)
    if not tokens:
        return "unknown"

    # Evite tokens muito ambíguos ("a", "o", "de", "to") e foque em marcadores úteis.
    pt_markers = {
        "não", "que", "para", "porque", "porquê", "como", "também", "você", "vocês",
        "qual", "quais", "isso", "essa", "esse", "estas", "estes", "são", "é", "foi",
        "mais", "menos", "então", "ou", "numa", "neste", "nessa",
    }
    en_markers = {
        "the", "and", "what", "why", "how", "this", "that", "these", "those",
        "is", "are", "was", "were", "with", "without", "because", "into", "from",
        "can", "could", "should", "would",
    }

    pt_hits = sum(1 for t in tokens if t in pt_markers)
    en_hits = sum(1 for t in tokens if t in en_markers)

    if pt_hits >= min_hits and pt_hits >= en_hits + margin:
        return "pt-br"
    if en_hits >= min_hits and en_hits >= pt_hits + margin:
        return "en"
    return "unknown"


def looks_english(s: str) -> bool:
    """
    DEPRECADO: use `guess_language_ptbr_en(text) == "en"`.

    Mantido por compatibilidade, porque outras partes do código podem importar
    `looks_english` (ex.: gate do repair pass).
    """
    return guess_language_ptbr_en(s) == "en"


def split_sentences(s: str) -> List[str]:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    if not s:
        return []
    parts = re.split(r"(?<=[\.\!\?])\s+", s)
    return [p.strip() for p in parts if p.strip()]


def limit_words(s: str, n: int) -> str:
    words = (s or "").split()
    if len(words) <= n:
        return s
    return " ".join(words[:n]).rstrip(" ,;:") + "."


def normalize_basic_answer(a: str) -> str:
    sents = split_sentences(a)
    out = " ".join(sents[:2]) if sents else (a or "")
    out = limit_words(out, 28)
    return out.strip()


def normalize_cloze_answer(a: str) -> str:
    sents = split_sentences(a)
    out = sents[0] if sents else (a or "")
    out = limit_words(out, 22)
    out = out.strip()
    if not out.lower().startswith("extra:"):
        out = "Extra: " + out
    return out


def ensure_prefix(q: str) -> str:
    q = (q or "").strip()
    if not q:
        return q
    if q.startswith("[BASIC]") or q.startswith("[CLOZE]"):
        return q
    if "{{c1::" in q:
        return "[CLOZE] " + q
    return "[BASIC] " + q


def is_valid_cloze(q: str) -> bool:
    return q.count("{{c1::") == 1
