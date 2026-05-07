// PKCE (RFC 7636) helpers using Web Crypto. Used to authenticate the SPA
// against OpenEMR without ever sending a client secret to the browser.

function base64UrlEncode(bytes: Uint8Array): string {
  let binary = ''
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function randomBytes(length: number): Uint8Array {
  const out = new Uint8Array(length)
  crypto.getRandomValues(out)
  return out
}

// Verifier: 43–128 chars, [A-Z a-z 0-9 - . _ ~]. base64url of 32 random bytes
// gives a 43-char string and easily satisfies the entropy requirement.
export function generateCodeVerifier(): string {
  return base64UrlEncode(randomBytes(32))
}

export async function deriveCodeChallenge(verifier: string): Promise<string> {
  const encoded = new TextEncoder().encode(verifier)
  const digest = await crypto.subtle.digest('SHA-256', encoded)
  return base64UrlEncode(new Uint8Array(digest))
}

// Opaque random `state` value used to bind the auth code redirect to the
// originating browser session — guards against CSRF on /oauth/callback.
export function generateState(): string {
  return base64UrlEncode(randomBytes(16))
}
