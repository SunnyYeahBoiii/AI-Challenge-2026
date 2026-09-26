/**
 * How a DRES submission ended, shared by every submit surface: the frame
 * detail dialog, the TRAKE board, each chain row, result cards, and pins.
 *
 * `rejected` is distinct from `duplicate` on purpose. DRES reports a
 * server-side filter rejection (for example submitting past the team's
 * correct-answer quota) as `status: false`, the same value it uses for a
 * duplicate, so collapsing the two told the team nothing.
 */
export type SubmitStatus =
  | "loading"
  | "correct"
  | "wrong"
  | "duplicate"
  | "rejected"
  | "error";

export interface SubmitStatusStyle {
  bg: string;
  icon: string;
  label: string;
}

/**
 * Badge colours per verdict. `rejected` is purple to read as "DRES refused to
 * record this", distinct from the orange used for a wrong or duplicate answer
 * and the red used for a genuine failure.
 */
export const SUBMIT_STATUS_STYLE: Record<SubmitStatus, SubmitStatusStyle> = {
  loading: { bg: "bg-black/40", icon: "send", label: "Submitting…" },
  correct: { bg: "bg-green-600", icon: "check_circle", label: "Correct" },
  wrong: { bg: "bg-orange-600", icon: "cancel", label: "Wrong" },
  duplicate: { bg: "bg-orange-600", icon: "content_copy", label: "Duplicate" },
  rejected: { bg: "bg-purple-600", icon: "block", label: "Rejected" },
  error: { bg: "bg-red-600", icon: "error", label: "Error" },
};

const TITLE: Record<SubmitStatus, string> = {
  loading: "Submitting…",
  correct: "Correct",
  wrong: "Wrong",
  duplicate: "Already submitted",
  rejected: "Rejected by DRES",
  error: "Submission failed",
};

/**
 * Tooltip for a verdict, preferring DRES's own wording whenever the API sent
 * one. A quota rejection is a full sentence, so it needs the hover.
 */
export function submitStatusTitle(status: SubmitStatus, message?: string): string {
  return message ?? TITLE[status];
}
