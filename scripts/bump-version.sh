#!/bin/bash
# =============================================================================
# bump-version.sh — Atualiza atomicamente todos os arquivos de versão do projeto
# Uso: ./scripts/bump-version.sh <version> [suffix]
# Exemplos:
#   ./scripts/bump-version.sh 1.4.0 beta    → v1.4.0-beta
#   ./scripts/bump-version.sh 2.0.0          → v2.0.0 (estável)
# =============================================================================

set -euo pipefail

VERSION="${1:?Uso: $0 <version> [suffix]}"
SUFFIX="${2:-}"

# Diretório raiz do projeto (relativo ao script)
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Calcula valores derivados
if [ -n "$SUFFIX" ]; then
  FULL_TAG="v${VERSION}-${SUFFIX}"
  PLAIN="${VERSION}-${SUFFIX}"
  IS_BETA="true"
  VERSION_SUFFIX="'${SUFFIX}'"
else
  FULL_TAG="v${VERSION}"
  PLAIN="${VERSION}"
  IS_BETA="false"
  VERSION_SUFFIX="''"
fi

echo "Atualizando versão para ${FULL_TAG} em todos os arquivos..."

# 1. frontend/src/config/version.ts
VERSION_TS="${ROOT_DIR}/frontend/src/config/version.ts"
{
  echo "// Centralized version configuration"
  echo "export const APP_VERSION = 'v${VERSION}'"
  echo "export const VERSION_SUFFIX = ${VERSION_SUFFIX}"
  echo "export const IS_BETA = ${IS_BETA}"
  echo "export const FULL_VERSION = IS_BETA ? \`\${APP_VERSION}-\${VERSION_SUFFIX}\` : APP_VERSION // ${FULL_TAG}"
} > "$VERSION_TS"
echo "  ✓ ${VERSION_TS}"

# 2. app/__init__.py
INIT_PY="${ROOT_DIR}/app/__init__.py"
sed -i "s/__version__ = \".*\"/__version__ = \"${PLAIN}\"/" "$INIT_PY"
echo "  ✓ ${INIT_PY}"

# 3. app/main.py
MAIN_PY="${ROOT_DIR}/app/main.py"
sed -i "s/version=\"[^\"]*\"/version=\"${PLAIN}\"/" "$MAIN_PY"
echo "  ✓ ${MAIN_PY}"

# 4. pyproject.toml
PYPROJECT="${ROOT_DIR}/pyproject.toml"
sed -i "s/^version = \".*\"/version = \"${PLAIN}\"/" "$PYPROJECT"
echo "  ✓ ${PYPROJECT}"

# 5. frontend/package.json
PACKAGE_JSON="${ROOT_DIR}/frontend/package.json"
sed -i "s/\"version\": \".*\"/\"version\": \"${PLAIN}\"/" "$PACKAGE_JSON"
echo "  ✓ ${PACKAGE_JSON}"

echo ""
echo "Versão atualizada para ${FULL_TAG} em todos os 5 arquivos."
