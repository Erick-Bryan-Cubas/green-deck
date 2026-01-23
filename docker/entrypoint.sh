#!/usr/bin/env bash
# =============================================================================
# Green Deck - Docker Entrypoint Script
# =============================================================================
# This script handles container initialization before starting the application.
# It replaces the Windows-specific code in run.py with cross-platform logic.
# =============================================================================

set -Eeuo pipefail

# Create data directories if they don't exist
mkdir -p /app/data/generator /app/data/browser

# Wait for Ollama if configured
if [[ "${WAIT_FOR_OLLAMA:-false}" == "true" && -n "${OLLAMA_HOST:-}" ]]; then
  echo "Waiting for Ollama at ${OLLAMA_HOST}..."

  remaining=60
  # Normalize host (avoid double //)
  ollama_base="${OLLAMA_HOST%/}"

  while (( remaining > 0 )); do
    if curl -fsS "${ollama_base}/api/tags" >/dev/null 2>&1; then
      echo "Ollama is available!"
      break
    fi

    echo "  Ollama not ready, retrying in 2s... (${remaining} seconds remaining)"
    sleep 2
    (( remaining -= 2 ))
  done

  if (( remaining <= 0 )); then
    echo "Warning: Ollama not available after 60s, continuing anyway..."
    echo "  You can manually check Ollama status later."
  fi
fi

# Print startup banner (literal; no bash interpretation)
cat <<'BANNER'
  ____ ___ _     ___    _         _     __ _              ____  _             _    

  _______ .______       _______  _______ .__   __.     _______   _______   ______  __  ___
 /  _____||   _  \     |   ____||   ____||  \ |  |    |       \ |   ____| /      ||  |/  /
|  |  __  |  |_)  |    |  |__   |  |__   |   \|  |    |  .--.  ||  |__   |  ,----'|  '  / 
|  | |_ | |      /     |   __|  |   __|  |  . `  |    |  |  |  ||   __|  |  |     |    <  
|  |__| | |  |\  \----.|  |____ |  |____ |  |\   |    |  '--'  ||  |____ |  `----.|  .  \ 
 \______| | _| `._____||_______||_______||__| \__|    |_______/ |_______| \______||__|\__\
                                                                                        
                        AI-Powered Intelligent Flashcard Generator                                                                                                               

BANNER

echo "  Server:      http://0.0.0.0:${PORT:-3000}"
echo "  Environment: ${ENVIRONMENT:-production}"
echo "  Ollama:      ${OLLAMA_HOST:-not configured}"
echo "  Anki:        ${ANKI_CONNECT_URL:-not configured}"
echo ""
echo "=========================================="
echo ""

# Execute the main command (passed as arguments)
exec "$@"
