"use client";

import { useEffect, useState } from "react";
import { Icon } from "./icon";
import { getNearestKeyframe, type FrameResult, type TemporalSearchResponse } from "@/lib/api";
import { SubmitStatusBadge } from "./submit-status";
import type { DresSubmitState } from "@/hooks/use-dres-submit";

export interface ChainEditTarget {
  sequenceId: string;
  videoId: string;
  frameIds: number[];
  eventIndex: number;
  frame: FrameResult;
}

interface TrakeChainListProps {
  result: TemporalSearchResponse;
  isLoading: boolean;
  hasSearched: boolean;
  /** Edited frameIds per sequence_id (overrides best_sequence). */
  edits: Record<string, number[]>;
  onSubmitChain: (videoId: string, frameIds: number[], sequenceId: string) => void;
  /** Verdict per sequence id, keyed as `chain:<sequenceId>` upstream. */
  submitStates: Record<string, DresSubmitState>;
  onEditFrame: (target: ChainEditTarget) => void;
}

function ChainThumb({
  videoId,
  frameIndex,
  fallbackUrl,
  eventLabel,
  edited,
  onClick,
}: {
  videoId: string;
  frameIndex: number;
  fallbackUrl: string;
  eventLabel: string;
  edited: boolean;
  onClick: () => void;
}) {
  const [thumb, setThumb] = useState(fallbackUrl);
  useEffect(() => {
    setThumb(fallbackUrl);
  }, [fallbackUrl]);
  useEffect(() => {
    if (!edited) return;
    let cancelled = false;
    getNearestKeyframe(videoId, frameIndex).then((kf) => {
      if (!cancelled && kf?.thumbnail_url) setThumb(kf.thumbnail_url);
    });
    return () => {
      cancelled = true;
    };
  }, [videoId, frameIndex, edited]);

  return (
    <button
      onClick={onClick}
      className="relative shrink-0 group"
      title={`${eventLabel}: frame ${frameIndex} (click to adjust)`}
    >
      <img
        src={thumb}
        alt={eventLabel}
        className={`w-40 h-24 object-cover rounded border transition group-hover:ring-2 group-hover:ring-primary ${
          edited ? "border-yellow-500 ring-1 ring-yellow-500" : "border-outline-variant"
        }`}
        loading="lazy"
      />
      <span className="absolute top-1 left-1 bg-black/70 text-white text-label-sm font-bold px-1.5 rounded">
        {eventLabel}
      </span>
      <span className="absolute bottom-1 left-1 bg-black/70 text-white text-label-xs px-1.5 rounded font-mono">
        #{frameIndex}
      </span>
    </button>
  );
}

export function TrakeChainList({
  result,
  isLoading,
  hasSearched,
  edits,
  onSubmitChain,
  submitStates,
  onEditFrame,
}: TrakeChainListProps) {
  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center text-on-surface-variant">
        Searching chains...
      </div>
    );
  }

  if (!hasSearched) {
    return (
      <div className="flex-1 flex items-center justify-center text-on-surface-variant text-body-md">
        Enter events on the left, then Search to find chains.
      </div>
    );
  }

  if (result.videos.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-on-surface-variant text-body-md">
        No chains found. Try fewer events or different wording.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      {result.videos.map((video) => {
        const seq = video.best_sequence;
        const originalIds = seq.frames.map((f) => f.frame_index);
        const frameIds = edits[seq.sequence_id] ?? originalIds;
        return (
          <div
            key={seq.sequence_id}
            className="rounded-lg bg-surface-container-lowest border border-outline-variant p-3"
          >
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <span className="text-body-md font-mono font-bold text-on-surface">
                {video.video_id}
              </span>
              <span className="text-label-sm text-on-surface-variant">
                score {(seq.sequence_score * 100).toFixed(1)}%
              </span>
              <span className="text-label-sm text-on-surface-variant">
                span {seq.total_span_seconds.toFixed(1)}s
              </span>
              {edits[seq.sequence_id] && (
                <span className="text-label-sm font-bold text-yellow-600">
                  edited
                </span>
              )}
              <div className="ml-auto flex items-center gap-2">
              <SubmitStatusBadge state={submitStates[`chain:${seq.sequence_id}`]} />
              <button
                onClick={() => onSubmitChain(video.video_id, frameIds, seq.sequence_id)}
                className="flex items-center gap-1 px-3 py-1.5 rounded bg-primary text-on-primary text-label-md font-bold hover:bg-primary/90 transition-colors"
              >
                <Icon name="send" size={16} />
                Submit chain
              </button>
              </div>
            </div>
            <div className="flex gap-2 overflow-x-auto">
              {seq.frames.map((frame, i) => (
                <ChainThumb
                  key={`${frame.video_id}-${frame.frame_index}`}
                  videoId={video.video_id}
                  frameIndex={frameIds[i] ?? frame.frame_index}
                  fallbackUrl={frame.thumbnail_url}
                  eventLabel={`${i + 1}`}
                  edited={(frameIds[i] ?? frame.frame_index) !== frame.frame_index}
                  onClick={() =>
                    onEditFrame({
                      sequenceId: seq.sequence_id,
                      videoId: video.video_id,
                      frameIds,
                      eventIndex: i,
                      frame,
                    })
                  }
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
