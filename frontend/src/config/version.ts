// Centralized version configuration
export const APP_VERSION = 'v1.3.0'
export const VERSION_SUFFIX = 'beta'
export const IS_BETA = true
export const FULL_VERSION = IS_BETA ? `${APP_VERSION}-${VERSION_SUFFIX}` : APP_VERSION // v1.3.0-beta
