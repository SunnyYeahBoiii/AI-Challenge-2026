"use client";

import { useCallback, useRef, useState } from "react";
import { isAxiosError } from "axios";
import {
  classifyDresSubmit,
  submitFrameToDres,
  submitTrakeToDres,
  type DresSubmitResult,
} from "@/lib/api";
import type { SubmitStatus } from "@/lib/submit-verdict";

export type { SubmitStatus as DresSubmitStatus } from "@/lib/submit-verdict";

export interface DresSubmitState {
  status: SubmitStatus;
  message?: string;
}

/** How long a result badge stays before the button returns to idle. */
const RESULT_MS = 4000;

interface FramePayload {
  kind: "frame";
  frameId: string;
  videoId: string;
  timestamp: number;
  submissionType: "track" | "trake" | "qa" | "kis";
  answer?: string;
}

interface TrakePayload {
  kind: "trake";
  videoId: string;
  frameIds: number[];
}

export type DresSubmitPayload = FramePayload | TrakePayload;

interface ApiErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: { description?: string } | string;
  };
}

/**
 * Turn a failed request into a verdict the badge can render.
 *
 * DRES explains itself in `error.details.description` — for example
 * "Maximum number of correct submissions (1) exceeded for the team" — while
 * `error.message` is only the API's generic wrapper, so the details win.
 * Reading `message` alone is what made every DRES refusal look identical.
 */
function readFailure(err: unknown): { status: SubmitStatus; message: string } {
  if (!isAxiosError(err)) {
    return {
      status: "error",
      message: err instanceof Error ? err.message : "Submission failed",
    };
  }
  const error = (err.response?.data as ApiErrorEnvelope | undefined)?.error;
  const details = error?.details;
  const reason =
    typeof details === "string"
      ? details
      : typeof details?.description === "string"
        ? details.description
        : undefined;
  return {
    status: error?.code === "DRES_REJECTED" ? "rejected" : "error",
    message: reason ?? error?.message ?? err.message,
  };
}

/**
 * Submit straight to DRES and report the verdict per call site.
 *
 * Results are keyed so several submit buttons — the frame dialog, the TRAKE
 * board, each chain row — can show their own badge without a shared dialog
 * standing between the click and the request.
 */
export function useDresSubmit(sessionId: string | null, evaluationId: string | null) {
  const [states, setStates] = useState<Record<string, DresSubmitState>>({});
  const inFlightRef = useRef<Set<string>>(new Set());

  const settle = useCallback((key: string, state: DresSubmitState) => {
    setStates((current) => ({ ...current, [key]: state }));
    setTimeout(() => {
      setStates((current) => {
        if (!(key in current)) return current;
        const { [key]: _done, ...rest } = current;
        return rest;
      });
    }, RESULT_MS);
  }, []);

  const submit = useCallback(
    async (key: string, payload: DresSubmitPayload) => {
      if (inFlightRef.current.has(key)) return;
      if (!sessionId) {
        settle(key, {
          status: "error",
          message: "Not logged in to DRES — open DRES Settings and log in first.",
        });
        return;
      }
      if (payload.kind === "trake" && payload.frameIds.length === 0) {
        settle(key, { status: "error", message: "TRAKE needs at least one frame." });
        return;
      }
      if (payload.kind === "frame") {
        if (!Number.isInteger(Number(payload.frameId))) {
          settle(key, { status: "error", message: `Invalid frame id: "${payload.frameId}"` });
          return;
        }
        if (payload.submissionType === "qa" && !payload.answer?.trim()) {
          settle(key, { status: "error", message: "Enter a QA answer." });
          return;
        }
      }

      inFlightRef.current.add(key);
      setStates((current) => ({ ...current, [key]: { status: "loading" } }));
      try {
        const evaluation = evaluationId ? { evaluationId } : {};
        const data: DresSubmitResult =
          payload.kind === "trake"
            ? await submitTrakeToDres({
                videoId: payload.videoId,
                frameIds: payload.frameIds,
                sessionId,
                ...evaluation,
              })
            : await submitFrameToDres({
                frameId: payload.frameId,
                videoId: payload.videoId,
                timestamp: payload.timestamp,
                submissionType: payload.submissionType,
                sessionId,
                ...evaluation,
                ...(payload.submissionType === "qa" ? { answer: payload.answer ?? "" } : {}),
              });
        settle(key, { status: classifyDresSubmit(data) });
      } catch (err) {
        const failure = readFailure(err);
        settle(key, { status: failure.status, message: failure.message });
      } finally {
        inFlightRef.current.delete(key);
      }
    },
    [evaluationId, sessionId, settle],
  );

  return { states, submit };
}
