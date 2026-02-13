"""
Topic Segmentation using LangExtract.

Este módulo usa a biblioteca LangExtract do Google para segmentar texto
em tópicos educacionais com posições exatas de caracteres.
"""

import asyncio
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Categorias de tópicos educacionais
TOPIC_CATEGORIES = {
    "DEFINICAO": {"name": "Definições", "color": "#fef08a"},
    "EXEMPLO": {"name": "Exemplos", "color": "#bbf7d0"},
    "CONCEITO": {"name": "Conceitos", "color": "#bfdbfe"},
    "FORMULA": {"name": "Fórmulas", "color": "#ddd6fe"},
    "PROCEDIMENTO": {"name": "Procedimentos", "color": "#fed7aa"},
    "COMPARACAO": {"name": "Comparações", "color": "#fbcfe8"},
}

# Flag para verificar se LangExtract está disponível
LANGEXTRACT_AVAILABLE = False
try:
    import langextract as lx
    LANGEXTRACT_AVAILABLE = True
    logger.info("[TopicSegmentation] LangExtract disponível")
except ImportError:
    logger.warning("[TopicSegmentation] LangExtract não instalado - usando fallback")


def _create_examples():
    """Cria exemplos few-shot para o LangExtract."""
    if not LANGEXTRACT_AVAILABLE:
        return []

    return [
        lx.data.ExampleData(
            text="Git é um sistema de controle de versão distribuído que permite rastrear mudanças no código.",
            extractions=[
                lx.data.Extraction(
                    extraction_class="DEFINICAO",
                    extraction_text="Git é um sistema de controle de versão distribuído",
                )
            ]
        ),
        lx.data.ExampleData(
            text="Por exemplo, ao criar um branch você pode trabalhar isoladamente sem afetar o código principal.",
            extractions=[
                lx.data.Extraction(
                    extraction_class="EXEMPLO",
                    extraction_text="ao criar um branch você pode trabalhar isoladamente sem afetar o código principal",
                )
            ]
        ),
        lx.data.ExampleData(
            text="O princípio de separação de responsabilidades é fundamental para código limpo.",
            extractions=[
                lx.data.Extraction(
                    extraction_class="CONCEITO",
                    extraction_text="princípio de separação de responsabilidades é fundamental para código limpo",
                )
            ]
        ),
        lx.data.ExampleData(
            text="Para fazer um commit, execute: git add . && git commit -m 'mensagem'",
            extractions=[
                lx.data.Extraction(
                    extraction_class="PROCEDIMENTO",
                    extraction_text="git add . && git commit -m 'mensagem'",
                )
            ]
        ),
    ]


async def segment_with_langextract(
    text: str,
    model: str = "qwen3:4b-instruct",
    ollama_url: str = "http://localhost:11434",
    openai_key: Optional[str] = None,
    gemini_key: Optional[str] = None
) -> List[dict]:
    """
    Segmenta texto usando LangExtract com posições exatas.

    Args:
        text: Texto para segmentar
        model: ID do modelo (ex: qwen3:4b-instruct, gpt-4o-mini, gemini-2.5-flash)
        ollama_url: URL do servidor Ollama local
        openai_key: Chave da API OpenAI (opcional)
        gemini_key: Chave da API Google/Gemini (opcional)

    Returns:
        Lista de segmentos com {start, end, category, text}
    """
    if not LANGEXTRACT_AVAILABLE:
        raise ImportError("LangExtract não está instalado. Execute: pip install langextract")

    prompt = """
    Identifique trechos educacionais importantes no texto.

    Categorias válidas:
    - DEFINICAO: conceitos sendo definidos ou explicados
    - EXEMPLO: casos práticos, ilustrações, cenários
    - CONCEITO: ideias-chave, princípios fundamentais
    - FORMULA: expressões matemáticas, equações
    - PROCEDIMENTO: passos, processos, métodos
    - COMPARACAO: contrastes, similaridades

    Extraia trechos EXATOS do texto (50-200 caracteres cada).
    Máximo 15 trechos por texto.
    """

    examples = _create_examples()

    # Detecta provider
    use_ollama = not openai_key and not gemini_key

    # Função síncrona que será executada em thread separada
    def _run_extraction():
        if use_ollama:
            logger.info(f"[LangExtract] Using Ollama: {model}")
            return lx.extract(
                text_or_documents=text,
                prompt_description=prompt,
                examples=examples,
                model_id=model,
                model_url=ollama_url,
                fence_output=False,
                use_schema_constraints=False,
            )
        elif openai_key:
            logger.info(f"[LangExtract] Using OpenAI: {model}")
            return lx.extract(
                text_or_documents=text,
                prompt_description=prompt,
                examples=examples,
                model_id=model or "gpt-4o-mini",
            )
        else:
            logger.info(f"[LangExtract] Using Gemini: {model}")
            return lx.extract(
                text_or_documents=text,
                prompt_description=prompt,
                examples=examples,
                model_id=model or "gemini-2.5-flash",
            )

    try:
        # Executa em thread separada para não bloquear o event loop
        result = await asyncio.to_thread(_run_extraction)

        # Processa resultados
        segments = []

        # LangExtract retorna extractions com char_interval
        if hasattr(result, 'extractions'):
            for extraction in result.extractions:
                # Acessa char_interval (CharInterval com start_pos/end_pos)
                char_interval = getattr(extraction, 'char_interval', None)
                if char_interval:
                    start = getattr(char_interval, 'start_pos', None)
                    end = getattr(char_interval, 'end_pos', None)

                    if start is not None and end is not None:
                        # extraction_class contém a categoria
                        category = getattr(extraction, 'extraction_class', 'CONCEITO')
                        if category:
                            category = category.upper()
                        else:
                            category = 'CONCEITO'

                        # Valida categoria
                        if category not in TOPIC_CATEGORIES:
                            category = 'CONCEITO'

                        segments.append({
                            "start": start,
                            "end": end,
                            "category": category,
                            "custom_name": None,  # Necessário para _build_topic_definitions
                            "text": text[start:end] if 0 <= start < end <= len(text) else "",
                        })
                        logger.debug(f"[LangExtract] Segment: {start}-{end} ({category})")

        logger.info(f"[LangExtract] Found {len(segments)} segments with exact positions")
        return segments

    except Exception as e:
        logger.error(f"[LangExtract] Error: {e}")
        raise


def is_langextract_available() -> bool:
    """Verifica se LangExtract está disponível."""
    return LANGEXTRACT_AVAILABLE


def get_topic_color(category: str) -> str:
    """Retorna a cor para uma categoria de tópico."""
    return TOPIC_CATEGORIES.get(category.upper(), {}).get("color", "#e5e7eb")


def get_topic_name(category: str) -> str:
    """Retorna o nome para uma categoria de tópico."""
    return TOPIC_CATEGORIES.get(category.upper(), {}).get("name", category)
