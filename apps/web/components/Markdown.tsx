"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Claude returns Markdown with GFM tables; Tailwind's preflight strips default
 *  element styling, so each tag gets explicit classes here. */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm leading-relaxed text-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (props) => <h1 className="mb-3 mt-6 text-lg font-semibold text-ink first:mt-0" {...props} />,
          h2: (props) => <h2 className="mb-2 mt-6 text-base font-semibold text-ink first:mt-0" {...props} />,
          h3: (props) => <h3 className="mb-2 mt-4 text-sm font-semibold text-ink" {...props} />,
          p: (props) => <p className="my-2" {...props} />,
          ul: (props) => <ul className="my-2 list-disc space-y-1 pl-5" {...props} />,
          ol: (props) => <ol className="my-2 list-decimal space-y-1 pl-5" {...props} />,
          strong: (props) => <strong className="font-semibold" {...props} />,
          a: (props) => <a className="text-accent hover:underline" {...props} />,
          code: (props) => (
            <code
              className="rounded bg-canvas px-1 py-0.5 font-mono text-xs text-ink ring-1 ring-inset ring-line"
              {...props}
            />
          ),
          blockquote: (props) => (
            <blockquote
              className="my-2 border-l-2 border-line pl-3 text-muted"
              {...props}
            />
          ),
          table: (props) => (
            <div className="my-3 overflow-x-auto">
              <table className="w-full border-collapse overflow-hidden rounded-md text-xs" {...props} />
            </div>
          ),
          th: (props) => (
            <th
              className="border border-line bg-canvas px-2.5 py-1.5 text-left font-semibold uppercase tracking-label text-muted"
              {...props}
            />
          ),
          td: (props) => (
            <td
              className="border border-line px-2.5 py-1.5 tabular-nums"
              {...props}
            />
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
