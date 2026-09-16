"use client";

import { useRef, useState } from "react";
import { fmtBytes } from "@/lib/api";

/** Sits above a finished analysis: say what to change, optionally attach more
 *  documents, and the revision lands underneath the current one. */
export function RefineBox({
  onSubmit,
  allowFiles,
  busy,
  placeholder,
}: {
  onSubmit: (instruction: string, files: File[]) => Promise<void>;
  allowFiles: boolean;
  busy: boolean;
  placeholder: string;
}) {
  const [instruction, setInstruction] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const canSend = instruction.trim().length > 0 && !busy;

  async function send() {
    if (!canSend) return;
    await onSubmit(instruction.trim(), files);
    setInstruction("");
    setFiles([]);
  }

  return (
    <div className="mb-5 rounded-lg border border-line bg-canvas p-3">
      <textarea
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
        }}
        rows={2}
        placeholder={placeholder}
        className="input resize-y bg-surface text-sm"
      />
      {files.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {files.map((file) => (
            <li
              key={`${file.name}:${file.size}`}
              className="flex items-center gap-1.5 rounded-full border border-line bg-surface px-2 py-0.5 text-xs"
            >
              <span className="max-w-[12rem] truncate" title={file.name}>
                {file.name}
              </span>
              <span className="num text-subtle">{fmtBytes(file.size)}</span>
              <button
                type="button"
                onClick={() => setFiles(files.filter((f) => f !== file))}
                aria-label={`Remove ${file.name}`}
                className="text-subtle hover:text-red-600"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-subtle">
          The revision appears below, and the current version is kept.
        </span>
        <span className="flex items-center gap-2">
          {allowFiles && (
            <>
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="btn-secondary px-2.5 py-1 text-xs"
              >
                Add documents
              </button>
              <input
                ref={inputRef}
                type="file"
                multiple
                accept=".pdf,.txt,.md,.markdown,.csv,.tsv,.json"
                onChange={(e) => {
                  const existing = new Set(files.map((f) => `${f.name}:${f.size}`));
                  setFiles([
                    ...files,
                    ...Array.from(e.target.files ?? []).filter(
                      (f) => !existing.has(`${f.name}:${f.size}`),
                    ),
                  ]);
                  e.target.value = "";
                }}
                className="hidden"
              />
            </>
          )}
          <button
            type="button"
            onClick={send}
            disabled={!canSend}
            className="btn-primary px-2.5 py-1 text-xs"
          >
            {busy ? "Revising…" : "Revise"}
          </button>
        </span>
      </div>
    </div>
  );
}
