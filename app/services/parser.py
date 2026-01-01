# app/services/parser.py
import json
import re
from typing import List, Dict, Any

from app.utils.text import (
    get_card_type,
    is_valid_cloze,
    normalize_basic_answer,
    normalize_cloze_answer,
)


def parse_flashcards_qa(text: str) -> List[Dict[str, str]]:
    """
    Parseia saída do modelo no formato:

    Q: ...
    A: ...
    SRC: "..."

    (uma linha em branco separando cards)

    Aceita também aliases de SRC: FONTE:/REF: (case-insensitive).
    """
    if not text:
        return []

    t = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in t.split("\n")]

    cards: List[Dict[str, str]] = []
    cur_q, cur_a, cur_src = "", "", ""
    mode = None  # "q" | "a" | "src"

    def flush():
        nonlocal cur_q, cur_a, cur_src, mode
        q = re.sub(r"\s+", " ", cur_q).strip()
        a = re.sub(r"\s+", " ", cur_a).strip()
        s = re.sub(r"\s+", " ", cur_src).strip().strip('"').strip()

        if q and a:
            out = {"front": q, "back": a}
            if s:
                out["src"] = s
            cards.append(out)

        cur_q, cur_a, cur_src, mode = "", "", "", None

    for ln in lines:
        if not ln:
            # card boundary
            if cur_q and cur_a:
                flush()
            continue

        # Reconhece Q: ou CLOZE: como front do card
        if re.match(r"(?i)^(q|cloze)\s*:\s*", ln):
            if cur_q and cur_a:
                flush()
            mode = "q"
            cur_q = re.sub(r"(?i)^(q|cloze)\s*:\s*", "", ln).strip()
            continue

        # Reconhece A: ou EXTRA: como back do card
        if re.match(r"(?i)^(a|extra)\s*:\s*", ln):
            mode = "a"
            cur_a = re.sub(r"(?i)^(a|extra)\s*:\s*", "", ln).strip()
            continue

        if re.match(r"(?i)^(src|fonte|ref)\s*:\s*", ln):
            mode = "src"
            cur_src = re.sub(r"(?i)^(src|fonte|ref)\s*:\s*", "", ln).strip()
            continue

        # continuação de linha (quando o modelo quebra)
        if mode == "q":
            cur_q = (cur_q + " " + ln).strip()
        elif mode == "a":
            cur_a = (cur_a + " " + ln).strip()
        elif mode == "src":
            cur_src = (cur_src + " " + ln).strip()
        else:
            # Linha solta fora de Q/A/SRC: ignora pra não "sujar" o parse
            continue

    if cur_q and cur_a:
        flush()

    return _dedup_by_front(cards)


def parse_flashcards_json(text: str) -> List[Dict[str, str]]:
    """
    Fallback: tenta parsear cards quando o modelo devolve JSON, por ex:
    [
      {"front":"...", "back":"...", "src":"..."},
      ...
    ]

    Também aceita variações comuns:
    - {"cards":[...]}
    - chaves: q/Q/question/pergunta -> front
             a/A/answer/resposta    -> back
             src/SRC/source/ref/... -> src
    """
    if not text:
        return []

    t = text.strip()
    if not t:
        return []

    data: Any = None

    # 1) Tenta extrair o maior array JSON possível (muitos modelos embrulham com texto)
    lb = t.find("[")
    rb = t.rfind("]")
    if lb != -1 and rb != -1 and rb > lb:
        candidate = t[lb : rb + 1]
        try:
            data = json.loads(candidate)
        except Exception:
            data = None

    # 2) Se não rolou, tenta objeto JSON (ex: {"cards":[...]})
    if data is None:
        lc = t.find("{")
        rc = t.rfind("}")
        if lc != -1 and rc != -1 and rc > lc:
            candidate = t[lc : rc + 1]
            try:
                data = json.loads(candidate)
            except Exception:
                data = None

    if data is None:
        return []

    # normaliza para lista
    if isinstance(data, dict):
        # chaves mais prováveis
        for k in ("cards", "flashcards", "items", "data"):
            if isinstance(data.get(k), list):
                data = data[k]
                break

    if not isinstance(data, list):
        return []

    cards: List[Dict[str, str]] = []

    def _pick(d: dict, keys: tuple[str, ...]) -> str:
        for k in keys:
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    for item in data:
        if not isinstance(item, dict):
            continue

        front = _pick(
            item,
            (
                "front",
                "question",
                "pergunta",
                "q",
                "Q",
            ),
        )
        back = _pick(
            item,
            (
                "back",
                "answer",
                "resposta",
                "a",
                "A",
            ),
        )
        src = _pick(
            item,
            (
                "src",
                "SRC",
                "source",
                "reference",
                "ref",
                "fonte",
            ),
        ).strip().strip('"').strip()

        if front and back:
            out = {"front": front, "back": back}
            if src:
                out["src"] = src
            cards.append(out)

    return _dedup_by_front(cards)


def _dedup_by_front(cards: List[Dict[str, str]]) -> List[Dict[str, str]]:
    # dedup por front (mantendo o primeiro)
    seen = set()
    out: List[Dict[str, str]] = []
    for c in cards or []:
        k = re.sub(r"\s+", " ", (c.get("front") or "")).strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(c)
    return out


def normalize_cards(cards: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Normaliza:
    - valida/ajusta cloze inválido
    - limpa resposta
    - preserva `src` (quando existir)
    - NÃO adiciona prefixos [BASIC]/[CLOZE]
    """
    normalized: List[Dict[str, str]] = []
    for c in cards or []:
        q = (c.get("front", "") or "").strip()
        a = (c.get("back", "") or "").strip()
        src = (c.get("src", "") or "").strip().strip('"').strip()

        card_type = get_card_type(q)

        if card_type == "cloze":
            if not is_valid_cloze(q):
                # Se cloze inválido, converte pra BASIC removendo {{c1::...}}
                q = re.sub(r"\{\{c\d+::([^}]+)\}\}", r"\1", q).strip()
                a = normalize_basic_answer(a)
            else:
                a = normalize_cloze_answer(a)
        else:
            a = normalize_basic_answer(a)

        # limpeza extra
        a = re.sub(r"(^|\s)(-|\d+\))\s+", " ", a).strip()

        out = {"front": q, "back": a}
        if src:
            out["src"] = src
        normalized.append(out)

    return normalized


def pick_default_deck(deck_options: str) -> str:
    s = (deck_options or "General").strip()
    return s or "General"
