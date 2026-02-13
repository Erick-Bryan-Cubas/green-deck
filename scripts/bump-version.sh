#!/usr/bin/env bash
set -euo pipefail

VERSION="$1"
SUFFIX="${2:-}"

if [ -n "$SUFFIX" ]; then
  FULL_VERSION="${VERSION}-${SUFFIX}"
else
  FULL_VERSION="${VERSION}"
fi

# pyproject.toml
sed -i "s/^version = \".*\"/version = \"${FULL_VERSION}\"/" pyproject.toml

# app/__init__.py
sed -i "s/__version__ = \".*\"/__version__ = \"${FULL_VERSION}\"/" app/__init__.py

# app/main.py
sed -i "s/version=\"[^\"]*\"/version=\"${FULL_VERSION}\"/" app/main.py

# frontend/package.json
sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"${FULL_VERSION}\"/" frontend/package.json

# frontend/src/config/version.ts
IS_BETA="false"
if [ -n "$SUFFIX" ]; then IS_BETA="true"; fi

cat > frontend/src/config/version.ts << EOF
// Centralized version configuration
export const APP_VERSION = 'v${VERSION}'
export const VERSION_SUFFIX = '${SUFFIX}'
export const IS_BETA = ${IS_BETA}
export const FULL_VERSION = IS_BETA ? \`\${APP_VERSION}-\${VERSION_SUFFIX}\` : APP_VERSION // v${FULL_VERSION}
EOF

echo "Version bumped to ${FULL_VERSION}"
