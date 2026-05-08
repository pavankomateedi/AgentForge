// Reads VITE_* env vars at build time. Centralized so individual modules
// don't sprinkle import.meta.env reads across the codebase. If a required
// var is missing in dev, this throws loudly so the misconfig surfaces
// immediately rather than at the first OAuth redirect.

function required(name: string, value: string | undefined): string {
  // Treat only undefined as missing. Empty string is a legitimate value
  // (e.g. VITE_OPENEMR_BASE_URL="" means "use same-origin") and must not
  // crash the SPA at module load.
  if (value === undefined) {
    throw new Error(
      `Missing required env var ${name}. Copy dashboard/.env.example to dashboard/.env and fill it in.`,
    )
  }
  return value
}

export const config = {
  openemrBaseUrl: required(
    'VITE_OPENEMR_BASE_URL',
    import.meta.env.VITE_OPENEMR_BASE_URL,
  ),
  fhirBase: required(
    'VITE_OPENEMR_FHIR_BASE',
    import.meta.env.VITE_OPENEMR_FHIR_BASE,
  ),
  oauthAuthorizeUrl: required(
    'VITE_OAUTH_AUTHORIZE_URL',
    import.meta.env.VITE_OAUTH_AUTHORIZE_URL,
  ),
  oauthTokenUrl: required(
    'VITE_OAUTH_TOKEN_URL',
    import.meta.env.VITE_OAUTH_TOKEN_URL,
  ),
  oauthClientId: required(
    'VITE_OAUTH_CLIENT_ID',
    import.meta.env.VITE_OAUTH_CLIENT_ID,
  ),
  oauthRedirectUri: required(
    'VITE_OAUTH_REDIRECT_URI',
    import.meta.env.VITE_OAUTH_REDIRECT_URI,
  ),
  oauthScopes: required(
    'VITE_OAUTH_SCOPES',
    import.meta.env.VITE_OAUTH_SCOPES,
  ),
  // Dev-only: bypass the OAuth dance with a fake token so card development
  // can proceed against a no-auth FHIR server (HAPI test) before OpenEMR
  // is available. Stripped from production .env.
  devBypass: import.meta.env.VITE_DEV_BYPASS === 'true',
  // Dev-only: when fhirBase is a relative proxy path (e.g. /fhir-api),
  // this is the absolute upstream Vite forwards to. Used to rewrite
  // Bundle.link.next URLs back through the proxy. Empty in production.
  fhirProxyTarget: import.meta.env.VITE_FHIR_PROXY_TARGET as string | undefined,
} as const
