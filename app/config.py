import os
from dotenv import load_dotenv

load_dotenv()

# Ollama
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_GENERATE_URL = os.getenv("OLLAMA_URL", f"{OLLAMA_HOST}/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen-flashcard")
# OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")
OLLAMA_ANALYSIS_MODEL = os.getenv("OLLAMA_ANALYSIS_MODEL", "embeddinggemma")
# Modelo para validação de qualidade de cards (pode ser mais rápido/barato que o de geração)
OLLAMA_VALIDATION_MODEL = os.getenv("OLLAMA_VALIDATION_MODEL", "qwen-flashcard")
OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", f"{OLLAMA_HOST}/api/embed")

# Anki
ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://127.0.0.1:8765")

# Server
PORT = int(os.getenv("PORT", "3000"))

# Limits (removidos)
MAX_SOURCE_CHARS = None
MAX_CTX_CHARS = None
