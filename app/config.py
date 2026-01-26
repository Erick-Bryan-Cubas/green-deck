import os
from dotenv import load_dotenv

load_dotenv()

# Ollama
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_GENERATE_URL = os.getenv("OLLAMA_URL", f"{OLLAMA_HOST}/api/generate")
# Modelo padrão: None força seleção dinâmica baseada nos modelos disponíveis
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", None)
OLLAMA_ANALYSIS_MODEL = os.getenv("OLLAMA_ANALYSIS_MODEL", None)
# Modelo para validação de qualidade de cards (pode ser mais rápido/barato que o de geração)
OLLAMA_VALIDATION_MODEL = os.getenv("OLLAMA_VALIDATION_MODEL", None)
OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", f"{OLLAMA_HOST}/api/embed")

# Anki
ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL", "http://127.0.0.1:8765")

# Server
PORT = int(os.getenv("PORT", "3000"))

# Limits (removidos)
MAX_SOURCE_CHARS = None
MAX_CTX_CHARS = None

# Security
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
).split(",")

# Rate Limiting
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")
RATE_LIMIT_GENERATE = os.getenv("RATE_LIMIT_GENERATE", "10/minute")

# Document Processing Timeouts (seconds)
DOCUMENT_EXTRACTION_TIMEOUT = int(os.getenv("DOCUMENT_EXTRACTION_TIMEOUT", "180"))  # 3 minutes
DOCUMENT_PREVIEW_TIMEOUT = int(os.getenv("DOCUMENT_PREVIEW_TIMEOUT", "90"))  # 90 seconds
