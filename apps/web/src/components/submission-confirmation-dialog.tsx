"use client";

import { useState } from "react";
import { Icon } from "./icon";
import { buildTrakeSubmitText } from "@/lib/cloud-api";
import { createSubmission, type Query } from "@/lib/submissions";

interface SubmissionConfirmationDialogProps {
  frameId: string;
  videoId: string;
  timestamp: number;
  submissionType: "track" | "qa" | "kis";
  sessionId: string | null;
  /** Selected DRES evaluation (contest) run to submit against. */
  evaluationId?: string | null;
  /** Prefill from frame-detail dialog when type is QA. */
  answer?: string;
  /** TRAKE ordered frame ids for TR-VIDEO-id1,id2,... */
  trakeFrameIds?: number[];
  /** Submit mode: DRES or Cloud API */
  submitMode?: "dres" | "cloud";
  /** Available queries for Cloud mode task selection */
  queries?: Query[];
  /** Currently selected query in topbar */
  selectedQueryId?: string | null;
  onClose: () => void;
}

export function SubmissionConfirmationDialog({
  frameId,
  videoId,
  timestamp,
  submissionType,
  sessionId,
  evaluationId,
  answer = "",
  trakeFrameIds,
  submitMode = "dres",
  queries = [],
  selectedQueryId,
  onClose,
}: SubmissionConfirmationDialogProps) {
  const [status, setStatus] = useState<
    "idle" | "loading" | "correct" | "wrong" | "duplicate" | "error" | "saved"
  >("idle");
  const [response, setResponse] = useState<string | null>(null);
  const [qaAnswer, setQaAnswer] = useState(answer);
  const [localQueryId, setLocalQueryId] = useState<string>(selectedQueryId ?? "");

  const isQa = submissionType === "qa";
  const isTrake =
    submissionType === "track" &&
    Array.isArray(trakeFrameIds) &&
    trakeFrameIds.length > 0;
  const timeMs = Math.round(timestamp * 1000);
  const qaAnswerTrimmed = qaAnswer.trim();
  const qaPreview = qaAnswerTrimmed
    ? `QA-${qaAnswerTrimmed}-${videoId}-${timeMs}`
    : "";
  const trakePreview = isTrake
    ? buildTrakeSubmitText(videoId, trakeFrameIds!)
    : "";

  const handleSubmit = async () => {
    if (submitMode === "cloud") {
      const selectedQuery = queries.find((q) => q.id === localQueryId);
      if (!selectedQuery) {
        setResponse("Please select a task to submit to.");
        setStatus("error");
        return;
      }
      if (isQa && !qaAnswerTrimmed) {
        setResponse("Enter a QA answer.");
        setStatus("error");
        return;
      }
      if (isTrake && (!videoId || !trakeFrameIds?.length)) {
        setResponse("TRAKE requires a video id and ordered frame ids.");
        setStatus("error");
        return;
      }
      setStatus("loading");
      try {
        const queryType = submissionType === "track" ? "trake" : submissionType;
        const frameIds = isTrake ? trakeFrameIds! : [parseInt(frameId) || 0];
        await createSubmission({
          queryName: selectedQuery.name,
          queryType,
          videoId,
          frameIds,
          answer: isQa ? qaAnswerTrimmed : undefined,
        });
        setResponse(`Saved to "${selectedQuery.name}".`);
        setStatus("saved");
      } catch {
        setResponse("Failed to save submission");
        setStatus("error");
      }
      return;
    }

    if (!sessionId) {
      setResponse("Not logged in to DRES — open DRES Settings and log in first.");
      setStatus("error");
      return;
    }
    if (isQa && !qaAnswerTrimmed) {
      setResponse("Enter a QA answer.");
      setStatus("error");
      return;
    }
    if (isTrake && (!videoId || !trakeFrameIds?.length)) {
      setResponse("TRAKE requires a video id and ordered frame ids.");
      setStatus("error");
      return;
    }
    setStatus("loading");
    try {
      const body = isTrake
        ? {
            video_path: videoId,
            frame_ids: trakeFrameIds,
            sessionId,
            ...(evaluationId ? { evaluationId } : {}),
          }
        : {
            frame_id: frameId,
            video_path: videoId,
            timestamp,
            sessionId,
            ...(evaluationId ? { evaluationId } : {}),
            ...(isQa ? { answer: qaAnswer } : {}),
          };
      const res = await fetch(`/api/dres/submit/${submissionType}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      setResponse(JSON.stringify(data, null, 2));
      if (!res.ok) {
        setStatus("error");
      } else if (data.submission === "WRONG") {
        setStatus("wrong");
      } else if (data.status === false) {
        setStatus("duplicate");
      } else if (data.submission === "CORRECT") {
        setStatus("correct");
      } else {
        setStatus("error");
      }
    } catch {
      setResponse("Submission failed");
      setStatus("error");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/80 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Confirm submission"
        className="bg-surface-container-lowest rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col border border-outline-variant"
      >
        <div className="flex items-center justify-between p-4 border-b border-outline-variant">
          <h2 className="text-headline-sm text-on-surface font-bold">
            Confirm Submission
          </h2>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high rounded-full p-1 transition-colors"
          >
            <Icon name="close" size={20} />
          </button>
        </div>

        <div className="p-4 space-y-3 overflow-y-auto flex-1">
          {submitMode === "cloud" && (
            <div>
              <label className="text-label-sm text-on-surface-variant mb-1 block">Task</label>
              <select
                className="w-full rounded border border-outline-variant bg-surface px-3 py-2 text-body-md"
                value={localQueryId}
                onChange={(e) => setLocalQueryId(e.target.value)}
              >
                <option value="">Select a task...</option>
                {queries.map((q) => (
                  <option key={q.id} value={q.id}>
                    {q.name} ({q.queryType.toUpperCase()})
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="text-body-md text-on-surface-variant">
            Type: <span className="font-bold text-on-surface">{submissionType.toUpperCase()}</span>
          </div>
          <div className="text-body-md text-on-surface-variant">
            Video: <span className="font-mono text-on-surface">{videoId}</span>
          </div>
          {isTrake ? (
            <div className="rounded-lg bg-surface-container p-3 font-mono text-mono-sm break-all">
              {trakePreview}
            </div>
          ) : (
            <>
              <div className="text-body-md text-on-surface-variant">
                Frame: <span className="font-mono text-on-surface">{frameId}</span>
              </div>
              <div className="text-body-md text-on-surface-variant">
                Time: <span className="font-mono text-on-surface">{timestamp}s</span>
              </div>
            </>
          )}
          {isQa && (
            <textarea
              value={qaAnswer}
              onChange={(e) => setQaAnswer(e.target.value)}
              placeholder="QA answer…"
              rows={3}
              className="w-full rounded border border-outline-variant bg-surface px-3 py-2 font-mono text-mono-sm"
            />
          )}
          {isQa && qaPreview && (
            <div className="rounded-lg bg-surface-container p-3 font-mono text-mono-sm break-all">
              {qaPreview}
            </div>
          )}
          {response && (
            <pre className="rounded-lg bg-surface-container p-3 text-mono-sm overflow-auto max-h-48">
              {response}
            </pre>
          )}
          {status !== "idle" && status !== "loading" && (
            <p className="text-label-md font-bold uppercase">{status}</p>
          )}
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-outline-variant">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded border border-outline-variant text-label-md"
          >
            Close
          </button>
          <button
            onClick={handleSubmit}
            disabled={status === "loading"}
            className="px-6 py-2 rounded bg-primary-container text-on-primary-container text-label-md font-bold disabled:opacity-50"
          >
            {status === "loading" ? "Submitting…" : submitMode === "cloud" ? "Save to Cloud" : "Submit to DRES"}
          </button>
        </div>
      </div>
    </div>
  );
}
