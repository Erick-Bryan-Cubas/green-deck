# app/services/prompt_provider.py

from dataclasses import dataclass
from string import Template
from typing import Literal, Optional

from app.api.prompts import PROMPTS

CardType = Literal["basic", "cloze", "both"]


def _render(key: str, **kwargs) -> str:
    tmpl = Template(PROMPTS[key])
    return tmpl.safe_substitute(**kwargs).strip()


@dataclass(frozen=True)
class PromptProvider:
    def flashcards_system(self, card_type: CardType) -> str:
        if card_type == "cloze":
            return PROMPTS["FLASHCARDS_SYSTEM_CLOZE"]
        return PROMPTS["FLASHCARDS_SYSTEM_PTBR"]

    def flashcards_type_instruction(self, card_type: CardType) -> str:
        return {
            "basic": PROMPTS["FLASHCARDS_TYPE_BASIC"],
            "cloze": PROMPTS["FLASHCARDS_TYPE_CLOZE"],
            "both": PROMPTS["FLASHCARDS_TYPE_BOTH"],
        }[card_type]

    def flashcards_format_block(self, card_type: CardType) -> str:
        return {
            "basic": PROMPTS["FLASHCARDS_FORMAT_BASIC"],
            "cloze": PROMPTS["FLASHCARDS_FORMAT_CLOZE"],
            "both": PROMPTS["FLASHCARDS_FORMAT_BOTH"],
        }[card_type]

    def build_flashcards_generation_prompt(
        self,
        *,
        src: str,
        ctx: str,
        checklist_block: str,
        target_min: int,
        target_max: int,
        card_type: CardType,
    ) -> str:
        ctx_block = ""
        if (ctx or "").strip():
            ctx_block = f"CONTEXTO GERAL (apenas para entender o assunto - NÃO crie cards sobre informações que estão APENAS aqui):\n{ctx.strip()}"

        return _render(
            "FLASHCARDS_GENERATION",
            guidelines=PROMPTS["FLASHCARDS_GUIDELINES"].strip(),
            src=src,
            ctx_block=ctx_block,
            checklist_block=(checklist_block or "").strip(),
            target_min=str(target_min),
            target_max=str(target_max),
            type_instruction=self.flashcards_type_instruction(card_type),
            format_block=self.flashcards_format_block(card_type),
        )

    def build_flashcards_repair_prompt(
        self,
        *,
        src: str,
        ctx: str,
        checklist_block: str,
        target_min: int,
        target_max: int,
        card_type: CardType,
    ) -> str:
        ctx_block = ""
        if (ctx or "").strip():
            ctx_block = f"CONTEXTO GERAL (apenas para entender o assunto - NÃO crie cards sobre informações que estão APENAS aqui):\n{ctx.strip()}"

        return _render(
            "FLASHCARDS_REPAIR",
            guidelines=PROMPTS["FLASHCARDS_GUIDELINES"].strip(),
            src=src,
            ctx_block=ctx_block,
            checklist_block=(checklist_block or "").strip(),
            target_min=str(target_min),
            target_max=str(target_max),
            format_block=self.flashcards_format_block(card_type),
        )

    def build_src_validation_prompt(self, *, src_text: str, cards_text: str) -> str:
        return _render(
            "SRC_VALIDATION_PROMPT",
            src_text=src_text,
            cards_text=cards_text,
        )

    def src_validation_system(self) -> str:
        return PROMPTS["SRC_VALIDATION_SYSTEM"]

    def build_relevance_filter_prompt(self, *, src_text: str, cards_text: str) -> str:
        return _render(
            "RELEVANCE_FILTER_PROMPT",
            src_text=src_text,
            cards_text=cards_text,
        )

    def relevance_filter_system(self) -> str:
        return PROMPTS["RELEVANCE_FILTER_SYSTEM"]

    def build_text_analysis_prompt(self, *, text: str, detected_lang: str) -> str:
        key = "TEXT_ANALYSIS_PT" if detected_lang == "pt-br" else "TEXT_ANALYSIS_EN"
        return _render(key, text=text)

    def text_analysis_system(self) -> str:
        return PROMPTS["TEXT_ANALYSIS_SYSTEM"]


def get_prompt_provider() -> PromptProvider:
    return PromptProvider()
