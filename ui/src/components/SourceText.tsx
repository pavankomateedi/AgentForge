// Renders a verified briefing without exposing the underlying source-id tags.
// The verifier confirms every clinical claim is grounded; the inline
// <source id="..."/> tags are stripped from the display so the clinician
// sees clean prose. The verification badge in ResponsePanel is the
// user-facing trust signal.

const SOURCE_TAG_RE = /\s*<source\s+id="[^"]+"\s*\/>/g

export function SourceText({ text }: { text: string }) {
  const cleaned = text.replace(SOURCE_TAG_RE, '').trim()
  return <>{cleaned}</>
}
