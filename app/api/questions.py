# app/api/questions.py
"""
Endpoints para geração de questões AllInOne (kprim, mc, sc).
"""

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Literal
import json
import logging
import uuid
from datetime import datetime, timezone

from app.services.ollama import ollama_generate_stream
from app.services.api_providers import openai_generate_stream, perplexity_generate_stream
from app.services.question_parser import (
    parse_questions,
    normalize_questions,
)
from app.utils.text import truncate_source
from app.core.prompts import PROMPTS
from app.api.models import get_provider_for_model, get_first_available_ollama_llm

router = APIRouter(prefix="/api", tags=["questions"])
logger = logging.getLogger(__name__)


# =============================================================================
# API Keys from Headers
# =============================================================================
class ApiKeys:
    """Container for API keys extracted from headers."""

    def __init__(
        self,
        anthropic_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        perplexity_key: Optional[str] = None,
    ):
        self.anthropic = anthropic_key
        self.openai = openai_key
        self.perplexity = perplexity_key


def get_api_keys_from_headers(
    x_anthropic_key: Optional[str] = Header(None, alias="X-Anthropic-Key"),
    x_openai_key: Optional[str] = Header(None, alias="X-OpenAI-Key"),
    x_perplexity_key: Optional[str] = Header(None, alias="X-Perplexity-Key"),
) -> ApiKeys:
    return ApiKeys(
        anthropic_key=x_anthropic_key,
        openai_key=x_openai_key,
        perplexity_key=x_perplexity_key,
    )


def merge_api_keys(header_keys: ApiKeys, body_request) -> ApiKeys:
    return ApiKeys(
        anthropic_key=header_keys.anthropic or getattr(body_request, "anthropicApiKey", None),
        openai_key=header_keys.openai or getattr(body_request, "openaiApiKey", None),
        perplexity_key=header_keys.perplexity or getattr(body_request, "perplexityApiKey", None),
    )


# =============================================================================
# Request Models
# =============================================================================
class GenerateQuestionsRequest(BaseModel):
    text: str
    textContext: Optional[str] = ""
    questionType: Literal["kprim", "mc", "sc", "mixed"] = "mixed"
    numQuestions: Optional[int] = None
    model: Optional[str] = None
    domain: Optional[str] = None
    anthropicApiKey: Optional[str] = None
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None


class ParseQuestionsRequest(BaseModel):
    text: str
    model: Optional[str] = None
    anthropicApiKey: Optional[str] = None
    openaiApiKey: Optional[str] = None
    perplexityApiKey: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id() -> str:
    return str(uuid.uuid4())


def _build_generation_prompt(
    text: str,
    context: str,
    question_type: str,
    num_questions: Optional[int],
    domain: Optional[str],
) -> tuple[str, str]:
    """
    Constrói o prompt para geração de questões.
    Retorna (system_prompt, user_prompt).
    """
    # System prompt baseado no tipo
    if question_type == "kprim":
        system = PROMPTS["QUESTION_GENERATION_SYSTEM_KPRIM"]
    elif question_type == "mc":
        system = PROMPTS["QUESTION_GENERATION_SYSTEM_MC"]
    elif question_type == "sc":
        system = PROMPTS["QUESTION_GENERATION_SYSTEM_SC"]
    else:
        system = PROMPTS["QUESTION_GENERATION_SYSTEM"]

    # Calcula quantidade
    if num_questions:
        target_min = max(1, num_questions - 1)
        target_max = num_questions + 1
    else:
        # Auto-calcula baseado no tamanho do texto
        word_count = len(text.split())
        target_min = max(2, word_count // 150)
        target_max = max(5, word_count // 80)

    # Instrução de tipo
    if question_type == "kprim":
        type_instruction = "Gere APENAS questões Kprim (4 afirmativas V/F)."
    elif question_type == "mc":
        type_instruction = "Gere APENAS questões de múltipla escolha (várias corretas)."
    elif question_type == "sc":
        type_instruction = "Gere APENAS questões de escolha única (uma correta)."
    else:
        type_instruction = "Escolha o tipo mais apropriado (kprim, mc ou sc) para cada questão."

    # Instrução de domínio
    domain_instruction = ""
    if domain:
        domain_instruction = f"- Use '{domain}' como valor do campo DOMAIN."

    # Constrói contexto
    ctx_block = ""
    if context:
        ctx_block = context[:2000]

    # Monta o prompt
    prompt_template = PROMPTS["QUESTION_GENERATION_PROMPT"]
    guidelines = PROMPTS["QUESTION_GENERATION_GUIDELINES"]
    format_block = PROMPTS["QUESTION_GENERATION_FORMAT"]

    prompt = prompt_template.replace("${guidelines}", guidelines)
    prompt = prompt.replace("${src}", truncate_source(text, 4000))
    prompt = prompt.replace("${ctx_block}", ctx_block)
    prompt = prompt.replace("${target_min}", str(target_min))
    prompt = prompt.replace("${target_max}", str(target_max))
    prompt = prompt.replace("${question_type}", type_instruction)
    prompt = prompt.replace("${domain_instruction}", domain_instruction)
    prompt = prompt.replace("${format_block}", format_block)

    return system, prompt


def _build_parse_prompt(text: str) -> tuple[str, str]:
    """
    Constrói o prompt para parsing de questões de texto livre.
    Retorna (system_prompt, user_prompt).
    """
    system = PROMPTS["QUESTION_PARSE_SYSTEM"]
    prompt = PROMPTS["QUESTION_PARSE_PROMPT"].replace("${text}", text[:8000])
    return system, prompt


# =============================================================================
# SSE Event Helpers
# =============================================================================
def _sse_event(event: str, data: dict) -> str:
    """Formata um evento SSE."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# =============================================================================
# Endpoints
# =============================================================================
@router.post("/generate-questions-stream")
async def generate_questions_stream(
    request: Request,
    req: GenerateQuestionsRequest,
    header_keys: ApiKeys = Depends(get_api_keys_from_headers),
):
    """
    Gera questões AllInOne a partir de texto via streaming SSE.
    """
    api_keys = merge_api_keys(header_keys, req)

    async def stream_generator():
        try:
            # Início
            yield _sse_event("generation_started", {"status": "starting"})

            # Validação básica
            text = (req.text or "").strip()
            if not text:
                yield _sse_event("error", {"message": "Texto vazio"})
                return

            # Determina modelo e provider
            model = req.model
            provider = "ollama"

            if model:
                provider = get_provider_for_model(model) or "ollama"
            else:
                model = await get_first_available_ollama_llm()
                if not model:
                    yield _sse_event("error", {"message": "Nenhum modelo disponível"})
                    return

            yield _sse_event("model_selected", {"model": model, "provider": provider})

            # Constrói prompts
            system, prompt = _build_generation_prompt(
                text=text,
                context=req.textContext or "",
                question_type=req.questionType,
                num_questions=req.numQuestions,
                domain=req.domain,
            )

            yield _sse_event("generating", {"status": "calling_llm"})

            # Chama o LLM
            raw_response = ""
            options = {"temperature": 0.5, "num_predict": 4096}

            try:
                if provider == "openai" and api_keys.openai:
                    async for piece in openai_generate_stream(
                        api_keys.openai, model, prompt, system=system, options=options
                    ):
                        raw_response += piece
                elif provider == "perplexity" and api_keys.perplexity:
                    async for piece in perplexity_generate_stream(
                        api_keys.perplexity, model, prompt, system=system, options=options
                    ):
                        raw_response += piece
                else:
                    async for piece in ollama_generate_stream(
                        model, prompt, system=system, options=options
                    ):
                        raw_response += piece
            except Exception as e:
                logger.error("LLM generation failed: %s", e)
                yield _sse_event("error", {"message": f"Erro na geração: {str(e)}"})
                return

            yield _sse_event("parsing", {"status": "parsing_response"})

            # Parseia as questões
            questions = parse_questions(raw_response)

            if not questions:
                yield _sse_event("error", {"message": "Nenhuma questão foi gerada"})
                return

            # Normaliza
            questions = normalize_questions(questions)

            yield _sse_event("parsed", {
                "count": len(questions),
                "types": {
                    "kprim": sum(1 for q in questions if q.get("qtype") == 0),
                    "mc": sum(1 for q in questions if q.get("qtype") == 1),
                    "sc": sum(1 for q in questions if q.get("qtype") == 2),
                }
            })

            # Envia questões
            yield _sse_event("questions", {"questions": questions})

            yield _sse_event("done", {"total": len(questions)})

        except Exception as e:
            logger.exception("Unexpected error in question generation stream")
            yield _sse_event("error", {"message": f"Erro inesperado: {str(e)}"})

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/parse-questions-stream")
async def parse_questions_stream(
    request: Request,
    req: ParseQuestionsRequest,
    header_keys: ApiKeys = Depends(get_api_keys_from_headers),
):
    """
    Interpreta questões de texto livre (copiado de PDF, doc, etc.) via streaming SSE.
    Usa IA para extrair e estruturar as questões.
    """
    api_keys = merge_api_keys(header_keys, req)

    async def stream_generator():
        try:
            yield _sse_event("parsing_started", {"status": "starting"})

            text = (req.text or "").strip()
            if not text:
                yield _sse_event("error", {"message": "Texto vazio"})
                return

            # Determina modelo
            model = req.model
            provider = "ollama"

            if model:
                provider = get_provider_for_model(model) or "ollama"
            else:
                model = await get_first_available_ollama_llm()
                if not model:
                    yield _sse_event("error", {"message": "Nenhum modelo disponível"})
                    return

            yield _sse_event("model_selected", {"model": model, "provider": provider})

            # Constrói prompt de parsing
            system, prompt = _build_parse_prompt(text)

            yield _sse_event("parsing", {"status": "calling_llm"})

            # Chama o LLM
            raw_response = ""
            options = {"temperature": 0.3, "num_predict": 4096}

            try:
                if provider == "openai" and api_keys.openai:
                    async for piece in openai_generate_stream(
                        api_keys.openai, model, prompt, system=system, options=options
                    ):
                        raw_response += piece
                elif provider == "perplexity" and api_keys.perplexity:
                    async for piece in perplexity_generate_stream(
                        api_keys.perplexity, model, prompt, system=system, options=options
                    ):
                        raw_response += piece
                else:
                    async for piece in ollama_generate_stream(
                        model, prompt, system=system, options=options
                    ):
                        raw_response += piece
            except Exception as e:
                logger.error("LLM parsing failed: %s", e)
                yield _sse_event("error", {"message": f"Erro no parsing: {str(e)}"})
                return

            # Parseia as questões
            questions = parse_questions(raw_response)

            if not questions:
                yield _sse_event("error", {"message": "Nenhuma questão identificada no texto"})
                return

            questions = normalize_questions(questions)

            yield _sse_event("parsed", {
                "count": len(questions),
                "types": {
                    "kprim": sum(1 for q in questions if q.get("qtype") == 0),
                    "mc": sum(1 for q in questions if q.get("qtype") == 1),
                    "sc": sum(1 for q in questions if q.get("qtype") == 2),
                }
            })

            yield _sse_event("questions", {"questions": questions})
            yield _sse_event("done", {"total": len(questions)})

        except Exception as e:
            logger.exception("Unexpected error in question parsing stream")
            yield _sse_event("error", {"message": f"Erro inesperado: {str(e)}"})

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/question-prompts")
async def get_question_prompts():
    """
    Retorna os prompts padrão para geração de questões.
    """
    return {
        "system": {
            "general": PROMPTS["QUESTION_GENERATION_SYSTEM"],
            "kprim": PROMPTS["QUESTION_GENERATION_SYSTEM_KPRIM"],
            "mc": PROMPTS["QUESTION_GENERATION_SYSTEM_MC"],
            "sc": PROMPTS["QUESTION_GENERATION_SYSTEM_SC"],
        },
        "guidelines": PROMPTS["QUESTION_GENERATION_GUIDELINES"],
        "format": PROMPTS["QUESTION_GENERATION_FORMAT"],
        "generation": PROMPTS["QUESTION_GENERATION_PROMPT"],
        "parse": {
            "system": PROMPTS["QUESTION_PARSE_SYSTEM"],
            "prompt": PROMPTS["QUESTION_PARSE_PROMPT"],
        },
    }
