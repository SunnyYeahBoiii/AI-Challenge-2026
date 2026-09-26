"use client";

import { SUBMIT_STATUS_STYLE } from "@/lib/submit-verdict";

import { Icon } from "./icon";
import type { DresSubmitState } from "@/hooks/use-dres-submit";

/**
 * The verdict badge that replaced the confirmation dialog.
 *
 * Submitting is now one click, so the result has to land on the button that
 * was clicked — there is no dialog left to hold a response pane. The tooltip
 * carries DRES's own wording, which is the only place a full explanation such
 * as a quota rejection has room to appear.
 */
export function SubmitStatusBadge({ state }: { state?: DresSubmitState }) {
  if (!state) return null;
  const style = SUBMIT_STATUS_STYLE[state.status];
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
