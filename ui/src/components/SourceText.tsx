// Renders text containing <source id="..."/> tags into JSX, replacing each tag
// with a styled span. React-safe — no dangerouslySetInnerHTML.

const SOURCE_TAG_RE = /(<source\s+id="[^"]+"\s*\/>)/g
const SOURCE_TAG_PARSE_RE = /<source\s+id="([^"]+)"\s*\/>/

export function SourceText({ text }: { text: string }) {
  const parts = text.split(SOURCE_TAG_RE)
  return (
    <>
      {parts.map((part, i) => {
        const m = part.match(SOURCE_TAG_PARSE_RE)
        if (m) {
          return (
            <span key={i} className="source-tag" title={`source: ${m[1]}`}>
              {m[1]}
            </span>
          )
        }
        return <span key={i}>{part}</span>
      })}
    </>
  )
}
