import re
import logging
from typing import List, Literal

from app.config import MAX_SOURCE_CHARS

LangHint = Literal["pt-br", "en", "unknown"]
LangHint3 = Literal["pt-br", "en", "es", "unknown"]

try:
    import langid  # type: ignore
except Exception:
    langid = None

_LANGID_READY = False


def _ensure_langid_ready() -> bool:
    """
    Inicializa o langid uma única vez e restringe as classes
    (pt/en/es) para reduzir confusões.
    """
    global _LANGID_READY
    if langid is None:
        return False
    if not _LANGID_READY:
        # garante que os logs do langid apareçam em nível INFO
        logging.getLogger("langid.langid").setLevel(logging.INFO)
        try:
            langid.set_languages(["pt", "en", "es"])
        except Exception:
            # se por algum motivo falhar, seguimos com o default
            pass
        _LANGID_READY = True
    return True


def truncate_source(text: str, limit: int = MAX_SOURCE_CHARS) -> str:
    """
    Normaliza o texto-fonte para uso no prompt e validações.

    Nota:
        O parâmetro `limit` existe para compatibilidade com chamadas antigas.
        Se você quiser realmente truncar pelo limite, implemente aqui.
    """
    return (text or "").strip()


def strip_src_lines(text: str) -> str:
    """
    Remove linhas SRC/FONTE/REF antes de detectar idioma.

    Importante porque SRC pode (e muitas vezes deve) estar no idioma do texto-fonte.
    """
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for ln in t.split("\n"):
        if re.match(r"(?i)^(src|fonte|ref)\s*:\s*", ln.strip()):
            continue
        out.append(ln)
    return "\n".join(out).strip()


def detect_language_pt_en_es(text: str) -> LangHint3:
    """
    Detector de idioma (pt/en/es) usando langid (offline).
    Retorna: "pt-br" | "en" | "es" | "unknown"
    """
    s = (text or "").strip()
    if not s:
        return "unknown"

    if not _ensure_langid_ready():
        return "unknown"

    code, score = langid.classify(s)

    if code == "pt":
        mapped: LangHint3 = "pt-br"
    elif code == "en":
        mapped = "en"
    elif code == "es":
        mapped = "es"
    else:
        mapped = "unknown"

    # Log no logger do próprio langid (fica como: INFO:langid.langid:...)
    logging.getLogger("langid.langid").info(
        "classify: code=%s mapped=%s score=%.4f chars=%d",
        code,
        mapped,
        float(score) if score is not None else -1.0,
        len(s),
    )

    return mapped


def guess_language_ptbr_en(text: str) -> LangHint:
    """
    Compat: mantém a assinatura original do projeto, mas agora usa APENAS langid.

    Retorna "pt-br" | "en" | "unknown"
    (se cair em "es", retorna unknown para este helper).
    """
    lang = detect_language_pt_en_es(text)
    if lang == "pt-br":
        return "pt-br"
    if lang == "en":
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


def get_card_type(q: str) -> str:
    """Retorna 'cloze' ou 'basic' baseado no conteúdo do cartão."""
    q = (q or "").strip()
    return "cloze" if "{{c1::" in q else "basic"


def is_valid_cloze(q: str) -> bool:
    """
    Valida formato de card cloze.
    Aceita um ou multiplos cloze deletions: {{c1::...}}, {{c2::...}}, etc.
    Requer numeracao sequencial comecando em 1.
    """
    if not q:
        return False

    # Encontra todos os marcadores cloze
    cloze_pattern = r"\{\{c(\d+)::[^}]+\}\}"
    matches = re.findall(cloze_pattern, q)

    if not matches:
        return False

    # Valida que os numeros sao sequenciais comecando em 1
    numbers = sorted(set(int(n) for n in matches))
    expected = list(range(1, len(numbers) + 1))

    return numbers == expected
