# app/services/prompt_provider.py

from dataclasses import dataclass, field
from string import Template
from typing import Literal, Optional, Dict

from app.core.prompts import PROMPTS

CardType = Literal["basic", "cloze", "both"]


def _render(key: str, **kwargs) -> str:
    tmpl = Template(PROMPTS[key])
    return tmpl.safe_substitute(**kwargs).strip()


def _render_custom(template_str: str, **kwargs) -> str:
    """Renderiza um template customizado."""
    tmpl = Template(template_str)
    return tmpl.safe_substitute(**kwargs).strip()


@dataclass
class PromptProvider:
    """
    Provedor de prompts com suporte a customização.

    Uso:
        provider = PromptProvider()  # Usa prompts padrão
        provider = PromptProvider(custom_prompts={"system": "...", "guidelines": "..."})  # Customizado
    """
    custom_prompts: Dict[str, str] = field(default_factory=dict)
    user_profile: Optional[str] = None
    
    def _build_profile_instruction(self) -> str:
        """Retorna instrução de perfil para injetar no system prompt."""
        if not self.user_profile:
            return ""
        return (
            f"\nAdapte a linguagem, os exemplos e a profundidade dos flashcards "
            f"ao perfil do usuário: {self.user_profile}\n"
        )

    def flashcards_system(self, card_type: CardType) -> str:
        # Se há prompt customizado, usa ele
        if self.custom_prompts.get("system"):
            base = self.custom_prompts["system"]
        elif card_type == "cloze":
            base = PROMPTS["FLASHCARDS_SYSTEM_CLOZE"]
        else:
            base = PROMPTS["FLASHCARDS_SYSTEM_PTBR"]
        
        # Injeta instrução de perfil do usuário, se houver
        profile_instruction = self._build_profile_instruction()
        if profile_instruction:
            return base.rstrip() + profile_instruction
        return base

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

    def flashcards_guidelines(self) -> str:
        """Retorna as diretrizes de criação de cards (customizável)."""
        return (
            self.custom_prompts.get("guidelines")
            or PROMPTS["FLASHCARDS_GUIDELINES"]
        ).strip()

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
        # Agora o contexto vai dentro do XML, entao nao precisa do prefixo antigo
        ctx_block = (ctx or "").strip() or "Nenhum contexto adicional fornecido."

        # Monta bloco de perfil do usuario se houver
        user_profile_block = ""
        if self.user_profile:
            user_profile_block = (
                f"\n<USER_PROFILE>\n{self.user_profile}\n</USER_PROFILE>\n"
            )

        # Se ha prompt de geracao customizado, usa ele
        if self.custom_prompts.get("generation"):
            rendered = _render_custom(
                self.custom_prompts["generation"],
                guidelines=self.flashcards_guidelines(),
                src=src,
                ctx_block=ctx_block,
                checklist_block=(checklist_block or "").strip(),
                target_min=str(target_min),
                target_max=str(target_max),
                type_instruction=self.flashcards_type_instruction(card_type),
                format_block=self.flashcards_format_block(card_type),
                user_profile_block=user_profile_block,
            )
            # Se o template customizado nao usa ${user_profile_block}, injeta manualmente
            if user_profile_block and "${user_profile_block}" not in self.custom_prompts["generation"]:
                rendered = user_profile_block + rendered
            return rendered

        base = _render(
            "FLASHCARDS_GENERATION",
            guidelines=self.flashcards_guidelines(),
            src=src,
            ctx_block=ctx_block,
            checklist_block=(checklist_block or "").strip(),
            target_min=str(target_min),
            target_max=str(target_max),
            type_instruction=self.flashcards_type_instruction(card_type),
            format_block=self.flashcards_format_block(card_type),
        )

        # Injeta bloco de perfil antes do prompt de geracao
        if user_profile_block:
            return user_profile_block + base
        return base

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
        # Contexto vai dentro do XML
        ctx_block = (ctx or "").strip() or "Nenhum contexto adicional fornecido."

        return _render(
            "FLASHCARDS_REPAIR",
            guidelines=self.flashcards_guidelines(),
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

    # ========================================
    # Metodos para reescrita de cards com LLM
    # ========================================

    def build_card_rewrite_prompt(
        self, *, front: str, back: str, action: str
    ) -> str:
        """
        Constroi prompt para reescrever um card.

        Args:
            front: Front do card original
            back: Back do card original
            action: "densify" | "split" | "simplify"

        Returns:
            Prompt renderizado
        """
        key_map = {
            "densify": "CARD_REWRITE_DENSIFY",
            "split": "CARD_REWRITE_SPLIT",
            "split_cloze": "CARD_REWRITE_SPLIT",
            "simplify": "CARD_REWRITE_SIMPLIFY",
        }
        key = key_map.get(action, "CARD_REWRITE_SIMPLIFY")
        return _render(key, front=front, back=back)

    def card_rewrite_system(self) -> str:
        """Retorna o system prompt para reescrita de cards."""
        return PROMPTS["CARD_REWRITE_SYSTEM"]

    def with_custom_prompts(
        self,
        system: Optional[str] = None,
        generation: Optional[str] = None,
        guidelines: Optional[str] = None,
        user_profile: Optional[str] = None,
    ) -> "PromptProvider":
        """
        Retorna um novo PromptProvider com prompts customizados.
        
        Args:
            system: Prompt de sistema customizado (opcional)
            generation: Template de geração customizado (opcional)
            guidelines: Diretrizes customizadas (opcional)
            user_profile: Perfil do usuário (opcional)
            
        Returns:
            Novo PromptProvider com os prompts customizados
        """
        custom = {}
        if system:
            custom["system"] = system
        if generation:
            custom["generation"] = generation
        if guidelines:
            custom["guidelines"] = guidelines
        
        return PromptProvider(custom_prompts=custom, user_profile=user_profile or self.user_profile)


def get_prompt_provider(
    custom_system: Optional[str] = None,
    custom_generation: Optional[str] = None,
    custom_guidelines: Optional[str] = None,
    user_profile: Optional[str] = None,
) -> PromptProvider:
    """
    Factory para criar PromptProvider com suporte a customização.

    Args:
        custom_system: Prompt de sistema customizado (opcional)
        custom_generation: Template de geração customizado (opcional)
        custom_guidelines: Diretrizes customizadas (opcional)
        user_profile: Perfil do usuário para adaptar linguagem e exemplos (opcional)

    Returns:
        PromptProvider configurado
    """
    custom = {}
    if custom_system:
        custom["system"] = custom_system
    if custom_generation:
        custom["generation"] = custom_generation
    if custom_guidelines:
        custom["guidelines"] = custom_guidelines

    return PromptProvider(custom_prompts=custom, user_profile=user_profile)
