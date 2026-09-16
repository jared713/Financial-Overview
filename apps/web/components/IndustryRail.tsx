"use client";

import { useRef, useState } from "react";
import { fmtBytes } from "@/lib/api";

export const MAX_FILES = 8;
export const MAX_TOTAL_BYTES = 20 * 1024 * 1024;

const ACCEPT = ".pdf,.txt,.md,.markdown,.csv,.tsv,.json";

export function IndustryRail({
  title,
  onTitleChange,
  prompt,
  onPromptChange,
  files,
  onFilesChange,
  onRun,
  busy,
  disabled,
}: {
  title: string;
  onTitleChange: (value: string) => void;
  prompt: string;
  onPromptChange: (value: string) => void;
  files: File[];
  onFilesChange: (files: File[]) => void;
  onRun: () => void;
  busy: boolean;
  disabled: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const total = files.reduce((n, f) => n + f.size, 0);
  const tooMany = files.length > MAX_FILES;
  const tooBig = total > MAX_TOTAL_BYTES;
  const canRun = title.trim().length > 0 && files.length > 0 && !tooMany && !tooBig;

  function addFiles(incoming: FileList | null) {
    if (!incoming) return;
    const existing = new Set(files.map((f) => `${f.name}:${f.size}`));
    const added = Array.from(incoming).filter(
      (f) => !existing.has(`${f.name}:${f.size}`),
    );
    onFilesChange([...files, ...added]);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        <div>
          <label className="label" htmlFor="industry-title">
            Industry
          </label>
          <input
            id="industry-title"
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
            placeholder="e.g. UK EdTech"
            disabled={disabled}
            className="input mt-1.5"
          />
        </div>

        <div>
          <p className="label">Documents</p>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              addFiles(e.dataTransfer.files);
            }}
            onClick={() => inputRef.current?.click()}
            className={`mt-1.5 cursor-pointer rounded-md border border-dashed px-3 py-5 text-center transition-colors ${
              dragging ? "border-accent bg-accent-soft" : "border-line hover:border-accent"
            }`}
          >
            <p className="text-xs font-medium text-ink">Drop files or click to choose</p>
            <p className="mt-1 text-xs text-muted">
              PDF or plain text, up to {MAX_FILES} files and{" "}
              {MAX_TOTAL_BYTES / (1024 * 1024)}MB
            </p>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPT}
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
              className="hidden"
            />
          </div>

          {files.length > 0 && (
            <ul className="mt-2 space-y-1">
              {files.map((file) => (
                <li
                  key={`${file.name}:${file.size}`}
                  className="flex items-center justify-between gap-2 rounded-md border border-line px-2 py-1.5"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-xs text-ink" title={file.name}>
                      {file.name}
                    </span>
                    <span className="num text-xs text-subtle">{fmtBytes(file.size)}</span>
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      onFilesChange(files.filter((f) => f !== file))
                    }
                    aria-label={`Remove ${file.name}`}
                    className="shrink-0 rounded p-1 text-subtle hover:bg-canvas hover:text-red-600"
                  >
                    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                      <path d="M4 4l8 8M12 4l-8 8" />
                    </svg>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {(tooMany || tooBig) && (
            <p className="mt-2 text-xs text-red-600">
              {tooMany && `At most ${MAX_FILES} files. `}
              {tooBig && `Total is ${fmtBytes(total)}, over the limit.`}
            </p>
          )}
        </div>

        <div>
          <label className="label" htmlFor="industry-prompt">
            What should Claude do with them?
          </label>
          <textarea
            id="industry-prompt"
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            rows={6}
            placeholder="e.g. Size the UK EdTech market, identify the main funding routes into schools, and flag the policy risks over the next three years."
            disabled={disabled}
            className="input mt-1.5 resize-y text-xs"
          />
          <p className="mt-1.5 text-xs text-subtle">
            Leave blank for a general summary.
          </p>
        </div>
      </div>

      <div className="space-y-2 border-t border-line p-4">
        <button
          type="button"
          onClick={onRun}
          disabled={!canRun || busy || disabled}
          className="btn-primary w-full"
        >
          {busy ? "Analysing…" : "Analyse documents"}
        </button>
        <p className="text-xs text-subtle">
          {files.length === 0
            ? "Attach at least one document."
            : !title.trim()
              ? "Name the industry."
              : `${files.length} file${files.length === 1 ? "" : "s"} · ${fmtBytes(total)}`}
        </p>
      </div>
    </div>
  );
}
