"use client";

import { useCallback, useRef, useState } from "react";
import { isAxiosError } from "axios";
import {
  classifyDresSubmit,
  submitFrameToDres,
  submitTrakeToDres,
  type DresSubmitResult,
} from "@/lib/api";

export type DresSubmitStatus = "loading" | "correct" | "wrong" | "duplicate" | "error";

export interface DresSubmitState {
  status: DresSubmitStatus;
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

function errorMessage(err: unknown): string {
  if (isAxiosError(err)) {
    const body = err.response?.data as { error?: { message?: string } } | undefined;
    return body?.error?.message ?? err.message;
  }
  return err instanceof Error ? err.message : "Submission failed";
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
        settle(key, { status: "error", message: errorMessage(err) });
      } finally {
        inFlightRef.current.delete(key);
      }
    },
    [evaluationId, sessionId, settle],
  );

  return { states, submit };
}
