"use client";

import { useState } from "react";
import { Icon } from "./icon";

interface SubmissionConfirmationDialogProps {
  frameId: string;
  videoId: string;
  timestamp: number;
  submissionType: "track" | "qa" | "kis";
  sessionId: string | null;
  onClose: () => void;
}

export function SubmissionConfirmationDialog({
  frameId,
  videoId,
  timestamp,
  submissionType,
  sessionId,
  onClose,
}: SubmissionConfirmationDialogProps) {
  const [status, setStatus] = useState<
    "idle" | "loading" | "correct" | "wrong" | "duplicate" | "error"
  >("idle");
  const [response, setResponse] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!sessionId) {
      setResponse("Not logged in to DRES — open DRES Settings and log in first.");
      setStatus("error");
      return;
    }
    setStatus("loading");
    try {
      const res = await fetch(`/api/dres/submit/${submissionType}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          frame_id: frameId,
          video_path: videoId,
          timestamp,
          sessionId,
        }),
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
        {/* Header */}
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

        {/* Content */}
        <div className="p-4 flex flex-col gap-4 overflow-y-auto">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="text-label-md text-on-surface-variant">Type:</span>
              <span className="text-body-md text-on-surface uppercase font-bold">
                {submissionType}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-label-md text-on-surface-variant">Frame:</span>
              <span className="font-mono text-mono-sm text-on-surface">{frameId}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-label-md text-on-surface-variant">Video:</span>
              <span className="font-mono text-mono-sm text-on-surface">{videoId}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-label-md text-on-surface-variant">Time:</span>
              <span className="font-mono text-mono-sm text-on-surface">
                {timestamp.toFixed(1)}s
              </span>
            </div>
          </div>

          {/* Response */}
          {status === "correct" && (
            <div className="flex items-center gap-2 text-body-sm text-green-700 bg-green-50 p-2 rounded">
              <Icon name="check_circle" size={16} />
              Correct — submission accepted
            </div>
          )}
          {status === "wrong" && (
            <div className="flex items-center gap-2 text-body-sm text-on-tertiary-container bg-tertiary-container/50 p-2 rounded">
              <Icon name="cancel" size={16} />
              Wrong — try a different answer
            </div>
          )}
          {status === "duplicate" && (
            <div className="flex items-center gap-2 text-body-sm text-on-tertiary-container bg-tertiary-container/50 p-2 rounded">
              <Icon name="content_copy" size={16} />
              Already submitted — see response below
            </div>
          )}
          {status === "error" && (
            <div className="flex items-center gap-2 text-body-sm text-on-error-container bg-error-container/50 p-2 rounded">
              <Icon name="error" size={16} />
              Submission rejected — see response below
            </div>
          )}
          {response && (
            <div className="bg-surface-container-low rounded p-3 font-mono text-mono-sm overflow-x-auto">
              <pre className="whitespace-pre-wrap">{response}</pre>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-outline-variant">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded border border-outline-variant text-label-md text-on-surface-variant hover:bg-surface-container transition-colors"
          >
            {status === "correct" || status === "wrong" || status === "duplicate" ? "Close" : "Cancel"}
          </button>
          <button
            onClick={handleSubmit}
            disabled={
              status === "loading" ||
              status === "correct" ||
              status === "wrong" ||
              status === "duplicate"
            }
            className="px-4 py-2 rounded bg-primary-container text-on-primary-container text-label-md hover:bg-primary-fixed transition-colors disabled:opacity-50"
          >
            {status === "loading" ? "Submitting..." : "Submit"}
          </button>
        </div>
      </div>
    </div>
  );
}
