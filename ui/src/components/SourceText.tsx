// Renders a verified briefing as GFM markdown without exposing the
// underlying source-id tags. The verifier confirms every clinical
// claim is grounded; the inline <source id="..."/> tags are stripped
// from the display so the clinician sees clean prose. The verification
// badge in BriefingCard is the user-facing trust signal.
//
// We render through react-markdown + remark-gfm so the agent can
// produce structured comparisons (tables, lists, headings, fenced
// code) when it makes sense — e.g., side-by-side PDF-vs-chart lab
// comparisons. Plain prose continues to render unchanged.

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const SOURCE_TAG_RE = /\s*<source\s+id="[^"]+"\s*\/>/g

export function SourceText({ text }: { text: string }) {
  const cleaned = text.replace(SOURCE_TAG_RE, '').trim()
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      // Use semantic HTML elements with our existing CSS classes so
      // tables/lists/code pick up the workspace theme automatically.
      components={{
        table: (props) => (
          <table className="briefing-table" {...props} />
        ),
        a: ({ href, children, ...rest }) => (
          // External links open in a new tab — clinicians shouldn't
          // lose their conversation by clicking a source URL.
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            {...rest}
          >
            {children}
          </a>
        ),
      }}
    >
      {cleaned}
    </ReactMarkdown>
  )
}
