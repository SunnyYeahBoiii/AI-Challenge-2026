"use client";

import { useState } from "react";
import { Icon } from "./icon";
import type { FrameResult } from "@/lib/api";

interface SubmissionConfirmationDialogProps {
  frame: FrameResult;
  submissionType: "track" | "qa" | "kis";
  onClose: () => void;
}

export function SubmissionConfirmationDialog({
  frame,
  submissionType,
  onClose,
}: SubmissionConfirmationDialogProps) {
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [response, setResponse] = useState<string | null>(null);

  const handleSubmit = async () => {
    setStatus("loading");
    try {
      const res = await fetch(`/api/dres/submit/${submissionType}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          frame_id: frame.id,
          video_path: frame.video_id,
          timestamp: frame.pts_time,
        }),
      });
      const data = await res.json();
      setResponse(JSON.stringify(data, null, 2));
      setStatus(res.ok ? "success" : "error");
    } catch {
      setResponse("Submission failed");
      setStatus("error");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/80 backdrop-blur-sm">
      <div className="bg-surface-container-lowest rounded-xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col border border-outline-variant">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-outline-variant">
          <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">
            Confirm Submission
          </h2>
          <button
            onClick={onClose}
            className="text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high rounded-full p-1 transition-colors"
          >
            <Icon name="close" size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 flex flex-col gap-4 overflow-y-auto">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <span className="font-label-md text-label-md text-on-surface-variant">Type:</span>
              <span className="font-body-md text-body-md text-on-surface uppercase font-bold">
                {submissionType}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-label-md text-label-md text-on-surface-variant">Frame:</span>
              <span className="font-mono-sm text-mono-sm text-on-surface">{frame.id}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-label-md text-label-md text-on-surface-variant">Video:</span>
              <span className="font-mono-sm text-mono-sm text-on-surface">{frame.video_id}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-label-md text-label-md text-on-surface-variant">Time:</span>
              <span className="font-mono-sm text-mono-sm text-on-surface">
                {frame.pts_time.toFixed(1)}s
              </span>
            </div>
          </div>

          {/* Response */}
          {response && (
            <div className="bg-surface-container-low rounded p-3 font-mono-sm text-mono-sm overflow-x-auto">
              <pre className="whitespace-pre-wrap">{response}</pre>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-outline-variant">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded border border-outline-variant font-label-md text-label-md text-on-surface-variant hover:bg-surface-container transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={status === "loading"}
            className="px-4 py-2 rounded bg-primary-container text-on-primary-container font-label-md text-label-md hover:bg-opacity-90 transition-colors disabled:opacity-50"
          >
            {status === "loading" ? "Submitting..." : "Submit"}
          </button>
        </div>
      </div>
    </div>
  );
}
