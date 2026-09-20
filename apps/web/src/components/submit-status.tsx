"use client";

import { Icon } from "./icon";
import type { DresSubmitState, DresSubmitStatus } from "@/hooks/use-dres-submit";

const STYLE: Record<DresSubmitStatus, { bg: string; icon: string; label: string }> = {
  loading: { bg: "bg-black/40", icon: "send", label: "Submitting…" },
  correct: { bg: "bg-green-600", icon: "check_circle", label: "Correct" },
  wrong: { bg: "bg-orange-600", icon: "cancel", label: "Wrong" },
  duplicate: { bg: "bg-orange-600", icon: "content_copy", label: "Duplicate" },
  error: { bg: "bg-red-600", icon: "error", label: "Error" },
};

/**
 * The verdict badge that replaced the confirmation dialog.
 *
 * Submitting is now one click, so the result has to land on the button that
 * was clicked — there is no dialog left to hold a response pane.
 */
export function SubmitStatusBadge({ state }: { state?: DresSubmitState }) {
  if (!state) return null;
  const style = STYLE[state.status];
  return (
    <span
      role="status"
      title={state.message ?? style.label}
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-label-xs font-bold text-white ${style.bg}`}
    >
      {state.status === "loading" ? (
        <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
      ) : (
        <Icon name={style.icon} size={14} />
      )}
      {style.label}
    </span>
  );
}
