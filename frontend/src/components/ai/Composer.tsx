"use client";

import { useEffect, useRef, useState } from "react";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalTextarea } from "@/components/ui/BrutalTextarea";

export type ComposerState = "idle" | "streaming" | "processing" | "stream-error" | "error";

export function Composer({
  state,
  onSend,
  onCancel,
}: {
  state: ComposerState;
  onSend: (content: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const busy = state === "streaming" || state === "processing";

  useEffect(() => {
    if (!busy && state === "idle") {
      textareaRef.current?.focus();
    }
  }, [state, busy]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || busy) return;
    onSend(trimmed);
    setValue("");
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="border-t border-outline bg-surface p-4">
      <div aria-live="polite">
        {state === "streaming" && (
          <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
            Streaming response
          </p>
        )}
        {state === "processing" && (
          <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
            Processing (no stream returned)
          </p>
        )}
        {state === "stream-error" && (
          <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-error">
            Stream interrupted — review the partial response, then retry explicitly
          </p>
        )}
        {state === "error" && (
          <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-error">
            Generation failed — use retry below
          </p>
        )}
      </div>
      <div className="flex items-end gap-3">
        <BrutalTextarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask something… (Enter to send, Shift+Enter for newline)"
          rows={2}
          disabled={busy}
          aria-label="Message composer"
          className="resize-none"
        />
        {busy ? (
          <BrutalButton variant="default" onClick={onCancel} aria-label="Cancel generation">
            Cancel
          </BrutalButton>
        ) : (
          <BrutalButton variant="yellow" onClick={submit} disabled={!value.trim()}>
            Send
          </BrutalButton>
        )}
      </div>
    </div>
  );
}
