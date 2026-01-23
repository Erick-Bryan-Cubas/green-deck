"""Prompt injection validation utilities."""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Patterns that may indicate prompt injection attempts
DANGEROUS_PATTERNS = [
    # Instruction override attempts
    (r"ignore\s+(previous|above|all|prior|earlier)\s+(instructions?|prompts?|rules?)", "instruction_override"),
    (r"disregard\s+.{0,50}(prompt|instruction|rule|guideline)", "instruction_override"),
    (r"forget\s+(everything|all|previous|your)\s+(instructions?|prompts?|training)", "instruction_override"),

    # Role manipulation
    (r"you\s+are\s+now\s+(a|an|the)\s+", "role_manipulation"),
    (r"pretend\s+(to\s+be|you\s+are)", "role_manipulation"),
    (r"act\s+as\s+(if|though|a|an)", "role_manipulation"),
    (r"assume\s+the\s+role", "role_manipulation"),
    (r"roleplay\s+as", "role_manipulation"),

    # System prompt extraction
    (r"(show|tell|reveal|display|print|output)\s+(me\s+)?(your|the)\s+(system|initial|original)\s+(prompt|instruction|message)", "system_extraction"),
    (r"what\s+(is|are)\s+your\s+(system|initial|original)\s+(prompt|instruction)", "system_extraction"),
    (r"repeat\s+(your|the)\s+(system|initial)\s+(prompt|message|instruction)", "system_extraction"),

    # Delimiter injection
    (r"<\|im_start\|>", "delimiter_injection"),
    (r"<\|im_end\|>", "delimiter_injection"),
    (r"<\|endoftext\|>", "delimiter_injection"),
    (r"<\|system\|>", "delimiter_injection"),
    (r"\[INST\]", "delimiter_injection"),
    (r"\[/INST\]", "delimiter_injection"),
    (r"<<SYS>>", "delimiter_injection"),
    (r"<</SYS>>", "delimiter_injection"),

    # Direct system prompt manipulation
    (r"^system\s*:\s*", "system_prefix"),
    (r"\nsystem\s*:\s*", "system_prefix"),
    (r"^assistant\s*:\s*", "assistant_prefix"),
    (r"\nassistant\s*:\s*", "assistant_prefix"),

    # Jailbreak attempts
    (r"(dan|developer|admin)\s+mode", "jailbreak"),
    (r"bypass\s+(safety|filter|restriction|content)", "jailbreak"),
    (r"disable\s+(safety|filter|restriction|content)", "jailbreak"),
    (r"unlock\s+(full|all|complete)\s+(capabilities|potential|access)", "jailbreak"),
]

# Maximum allowed prompt length
MAX_PROMPT_LENGTH = 10000


def validate_custom_prompt(prompt: str) -> Tuple[bool, str, str]:
    """
    Validates a custom prompt for potential injection attempts.

    Args:
        prompt: The custom prompt to validate

    Returns:
        Tuple of (is_valid, error_message, detected_pattern_type)
        If valid, error_message and detected_pattern_type will be empty strings.
    """
    if not prompt:
        return True, "", ""

    # Check length
    if len(prompt) > MAX_PROMPT_LENGTH:
        logger.warning("Prompt exceeds maximum length: %d > %d", len(prompt), MAX_PROMPT_LENGTH)
        return False, f"Prompt exceeds maximum length of {MAX_PROMPT_LENGTH} characters", "length_exceeded"

    prompt_lower = prompt.lower()

    # Check for dangerous patterns
    for pattern, pattern_type in DANGEROUS_PATTERNS:
        if re.search(pattern, prompt_lower, re.IGNORECASE | re.MULTILINE):
            logger.warning("Potential prompt injection detected: pattern_type=%s", pattern_type)
            return False, "Prompt contains potentially unsafe content", pattern_type

    return True, "", ""


def sanitize_prompt(prompt: str) -> str:
    """
    Sanitizes a prompt by removing or escaping potentially dangerous content.
    This is a less strict alternative to validation that allows the prompt
    but removes dangerous patterns.

    Args:
        prompt: The prompt to sanitize

    Returns:
        Sanitized prompt string
    """
    if not prompt:
        return ""

    sanitized = prompt

    # Truncate if too long
    if len(sanitized) > MAX_PROMPT_LENGTH:
        sanitized = sanitized[:MAX_PROMPT_LENGTH]

    # Remove or escape delimiter injections
    delimiter_patterns = [
        (r"<\|im_start\|>", "[START]"),
        (r"<\|im_end\|>", "[END]"),
        (r"<\|endoftext\|>", "[EOT]"),
        (r"<\|system\|>", "[SYS]"),
        (r"\[INST\]", "[INSTRUCTION]"),
        (r"\[/INST\]", "[/INSTRUCTION]"),
        (r"<<SYS>>", "[SYSTEM_START]"),
        (r"<</SYS>>", "[SYSTEM_END]"),
    ]

    for pattern, replacement in delimiter_patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    # Remove system/assistant role prefixes that could manipulate context
    sanitized = re.sub(r"^(system|assistant)\s*:\s*", "", sanitized, flags=re.IGNORECASE | re.MULTILINE)

    return sanitized


def log_injection_attempt(prompt: str, pattern_type: str, source: str = "unknown"):
    """
    Logs a potential prompt injection attempt for security monitoring.

    Args:
        prompt: The prompt that triggered the detection
        pattern_type: The type of pattern detected
        source: The source/endpoint where the attempt was made
    """
    # Truncate prompt for logging (don't log full content)
    truncated = prompt[:200] + "..." if len(prompt) > 200 else prompt
    logger.warning(
        "SECURITY: Potential prompt injection attempt detected | "
        "source=%s | pattern_type=%s | prompt_preview=%s",
        source,
        pattern_type,
        repr(truncated)
    )
