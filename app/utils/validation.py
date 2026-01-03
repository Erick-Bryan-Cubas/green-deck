"""
Validacao de suficiencia de conteudo para prevenir alucinacao.
Baseado em heuristica de ratio tokens/cards.

Inspirado em test/text_size_checker.py que usa ML para detectar escassez.
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationResult:
    """Resultado da validacao de suficiencia de conteudo."""

    is_valid: bool
    confidence: float  # 0.0 a 1.0
    recommended_max_cards: int
    message: Optional[str] = None
    token_count: int = 0
    ratio: float = 0.0


def count_meaningful_tokens(text: str) -> int:
    """
    Conta tokens com valor semantico (palavras > 3 caracteres).

    Esta heuristica filtra artigos, preposicoes e outros tokens
    que nao carregam informacao significativa para flashcards.
    """
    if not text:
        return 0
    words = [w for w in text.split() if len(w) > 3]
    return len(words)


def validate_content_sufficiency(
    text: str,
    requested_cards: int,
    min_tokens_per_card: int = 12,
) -> ValidationResult:
    """
    Valida se o texto tem conteudo suficiente para o numero de cards solicitado.

    Usa heuristica de ratio tokens/cards:
    - Se ratio < min_tokens_per_card: alto risco de alucinacao

    Args:
        text: Texto fonte para geracao de cards
        requested_cards: Numero de cards solicitados
        min_tokens_per_card: Minimo de tokens esperados por card (default 12)

    Returns:
        ValidationResult com validez, confianca e recomendacoes
    """
    if not text or not text.strip():
        return ValidationResult(
            is_valid=False,
            confidence=1.0,
            recommended_max_cards=0,
            message="Nenhum texto fornecido para geracao de cards.",
            token_count=0,
            ratio=0.0,
        )

    tokens = count_meaningful_tokens(text)

    if tokens == 0:
        return ValidationResult(
            is_valid=False,
            confidence=1.0,
            recommended_max_cards=0,
            message="Texto nao contem conteudo suficiente.",
            token_count=0,
            ratio=0.0,
        )

    # Garante que requested_cards seja pelo menos 1
    requested = max(1, requested_cards)
    ratio = tokens / requested
    recommended_max = max(1, tokens // min_tokens_per_card)

    # Thresholds de decisao
    if ratio >= min_tokens_per_card:
        # Conteudo suficiente
        return ValidationResult(
            is_valid=True,
            confidence=min(1.0, ratio / (min_tokens_per_card * 2)),
            recommended_max_cards=recommended_max,
            message=None,
            token_count=tokens,
            ratio=ratio,
        )
    elif ratio >= min_tokens_per_card * 0.6:
        # Zona de aviso - permite mas avisa
        return ValidationResult(
            is_valid=True,
            confidence=ratio / min_tokens_per_card,
            recommended_max_cards=recommended_max,
            message=f"Texto pode ser escasso para {requested_cards} cards. "
            f"Recomendamos no maximo {recommended_max} cards.",
            token_count=tokens,
            ratio=ratio,
        )
    else:
        # Bloqueio - muito escasso
        return ValidationResult(
            is_valid=False,
            confidence=1.0 - (ratio / min_tokens_per_card),
            recommended_max_cards=recommended_max,
            message=f"Texto insuficiente para {requested_cards} cards. "
            f"O texto possui {tokens} tokens significativos. "
            f"Maximo recomendado: {recommended_max} cards.",
            token_count=tokens,
            ratio=ratio,
        )


def estimate_max_cards(text: str, min_tokens_per_card: int = 12) -> int:
    """
    Estima o numero maximo de cards que podem ser gerados sem alucinacao.

    Args:
        text: Texto fonte
        min_tokens_per_card: Minimo de tokens por card

    Returns:
        Numero maximo recomendado de cards
    """
    tokens = count_meaningful_tokens(text)
    return max(1, tokens // min_tokens_per_card)
