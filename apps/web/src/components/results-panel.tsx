"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { Icon } from "./icon";
import { submitFrameToDres } from "@/lib/api";
import type { FrameResult } from "@/lib/api";
import { TRAKE_FRAME_MIME } from "@/lib/trake-types";

/** How many frames to paint initially / on each scroll page. */
const PAGE_SIZE = 48;

/** How long a result indicator stays on the card before reverting to idle. */
const QUICK_SUBMIT_RESULT_MS = 2500;

type QuickSubmitStatus = "loading" | "correct" | "wrong" | "duplicate" | "error";

const QUICK_SUBMIT_STYLE: Record<QuickSubmitStatus, { bg: string; icon: string }> = {
  loading: { bg: "bg-black/50", icon: "send" },
  correct: { bg: "bg-green-600", icon: "check_circle" },
  wrong: { bg: "bg-orange-600", icon: "cancel" },
  duplicate: { bg: "bg-orange-600", icon: "content_copy" },
  error: { bg: "bg-red-600", icon: "error" },
};

interface ResultsPanelProps {
  frames: FrameResult[];
  viewMode: "grouped" | "continuous";
  onFrameSelect: (frame: FrameResult) => void;
  onFrameDetail: (frame: FrameResult) => void;
  isLoading?: boolean;
  submissionType: "track" | "qa" | "kis";
  dresSessionId: string | null;
  /** Selected DRES evaluation (contest) run to submit against. */
  dresEvaluationId?: string | null;
  gridCols?: number;
  hasSearched?: boolean;
  /** TRACK: add frame to focused Event Candidate list. */
  onAddToTrake?: (frame: FrameResult) => void;
  trakeFocusedLabel?: string | null;
}

export function ResultsPanel({
  frames,
  viewMode,
  onFrameSelect,
  onFrameDetail,
  isLoading,
  submissionType,
  dresSessionId,
  dresEvaluationId,
  gridCols = 6,
  hasSearched = false,
  onAddToTrake,
  trakeFocusedLabel,
}: ResultsPanelProps) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [zoomFrame, setZoomFrame] = useState<FrameResult | null>(null);
  const [lastOpenedKey, setLastOpenedKey] = useState<string | null>(null);
  const [quickSubmit, setQuickSubmit] = useState<
    Record<string, { status: QuickSubmitStatus; message?: string }>
  >({});
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const scrollRootRef = useRef<HTMLElement | null>(null);

  const clearQuickSubmit = (key: string) => {
    setQuickSubmit((s) => {
      if (!(key in s)) return s;
      const { [key]: _removed, ...rest } = s;
      return rest;
    });
  };

  const handleQuickSubmit = async (frame: FrameResult) => {
    const key = `${frame.video_id}-${frame.frame_index}`;
    if (submissionType === "qa") return;
    if (submissionType === "track") {
      if (!onAddToTrake) return;
      onAddToTrake(frame);
      setQuickSubmit((s) => ({ ...s, [key]: { status: "correct" } }));
      setTimeout(() => clearQuickSubmit(key), QUICK_SUBMIT_RESULT_MS);
      return;
    }
    if (!dresSessionId) {
      setQuickSubmit((s) => ({ ...s, [key]: { status: "error", message: "Not logged in to DRES" } }));
      setTimeout(() => clearQuickSubmit(key), QUICK_SUBMIT_RESULT_MS);
      return;
    }
    setQuickSubmit((s) => ({ ...s, [key]: { status: "loading" } }));
    try {
      const data = await submitFrameToDres({
        frameId: String(frame.frame_idx),
        videoId: frame.video_id,
        timestamp: frame.pts_time,
        submissionType,
        sessionId: dresSessionId,
        evaluationId: dresEvaluationId ?? undefined,
      });
      const status: QuickSubmitStatus =
        data.submission === "WRONG"
          ? "wrong"
          : data.status === false
          ? "duplicate"
          : data.submission === "CORRECT"
          ? "correct"
          : "error";
      setQuickSubmit((s) => ({ ...s, [key]: { status } }));
    } catch (err) {
      const message = isAxiosError(err)
        ? (err.response?.data as { message?: string } | undefined)?.message ?? err.message
        : "Submission failed";
      setQuickSubmit((s) => ({ ...s, [key]: { status: "error", message } }));
    }
    setTimeout(() => clearQuickSubmit(key), QUICK_SUBMIT_RESULT_MS);
  };

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [frames, viewMode]);

  const allGroups = useMemo(() => {
    if (viewMode !== "grouped") return null;
    const groups = new Map<string, FrameResult[]>();
    frames.forEach((frame) => {
      if (!groups.has(frame.video_id)) groups.set(frame.video_id, []);
      groups.get(frame.video_id)!.push(frame);
    });
    return Array.from(groups.values())
      .sort((a, b) => Math.max(...b.map((f) => f.score)) - Math.max(...a.map((f) => f.score)))
      .map((group) => [...group].sort((a, b) => a.frame_idx - b.frame_idx));
  }, [frames, viewMode]);

  const totalItems = viewMode === "continuous" ? frames.length : (allGroups?.length ?? 0);

  const groupedFrames = useMemo(() => {
    if (viewMode === "continuous") return [frames.slice(0, visibleCount)];
    if (!allGroups) return [];
    return allGroups.slice(0, visibleCount);
  }, [viewMode, frames, visibleCount, allGroups]);

  const visibleFrameCount = useMemo(() => {
    if (viewMode === "continuous") return Math.min(visibleCount, frames.length);
    if (!allGroups) return 0;
    return allGroups.slice(0, visibleCount).reduce((sum, g) => sum + g.length, 0);
  }, [viewMode, visibleCount, frames.length, allGroups]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    const root = scrollRootRef.current;
    if (!sentinel || !root || visibleCount >= totalItems) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisibleCount((count) => Math.min(count + PAGE_SIZE, totalItems));
        }
      },
      { root, rootMargin: "400px", threshold: 0 }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [totalItems, visibleCount]);

  if (isLoading) {
    return (
      <div className="p-container-padding">
        <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))` }}>
          {Array.from({ length: 20 }).map((_, i) => (
            <div
              key={i}
              className="aspect-video bg-surface-container animate-pulse rounded-sm"
            />
          ))}
        </div>
      </div>
    );
  }

  if (frames.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md">
          <Icon name={hasSearched ? "search_off" : "image_search"} size={48} className="text-outline-variant mb-3" />
          <h2 className="text-headline-sm font-bold text-on-surface mb-2">
            {hasSearched ? "No Results Found" : "Start Searching"}
          </h2>
          <p className="text-body-md text-on-surface-variant">
            {hasSearched
              ? "Try adjusting your query or filters."
              : 'Use the filters on the left and press "Search" to see results.'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <main
      ref={scrollRootRef}
      className="relative flex-1 bg-surface-container-lowest overflow-y-auto p-container-padding"
    >
      <div className="flex justify-between items-center mb-4">
        <span className="text-label-md text-on-surface-variant">
          Showing {visibleFrameCount} of {frames.length}{" "}
          {frames.length === 1 ? "result" : "results"}
          {viewMode === "grouped" && groupedFrames.length > 1 && (
            <> · {groupedFrames.length} videos</>
          )}
        </span>
      </div>
      <div className="flex flex-col gap-6">
        {groupedFrames.map((group, groupIndex) => (
          <div
            key={viewMode === "grouped" ? group[0].video_id : groupIndex}
            className="flex flex-col gap-2"
          >
            {viewMode === "grouped" && (
              <div className="flex items-center gap-2 py-1">
                <Icon name="movie" size={16} className="text-on-surface-variant" />
                <span className="text-label-md text-on-surface">{group[0].video_id}</span>
                <span className="text-label-sm text-on-surface-variant">
                  ({group.length})
                </span>
                <div className="h-px bg-outline-variant flex-1" />
              </div>
            )}
            <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))` }}>
              {group.map((frame) => {
                const key = `${frame.video_id}-${frame.frame_index}`;
                const isLastOpened = lastOpenedKey === key;
                return (
                <div
                  key={key}
                  draggable={submissionType === "track"}
                  onDragStart={(e) => {
                    if (submissionType !== "track") return;
                    e.dataTransfer.setData(
                      TRAKE_FRAME_MIME,
                      JSON.stringify(frame),
                    );
                    e.dataTransfer.effectAllowed = "copy";
                  }}
                  className={`relative group cursor-pointer aspect-video bg-surface-container overflow-hidden border rounded-sm transition-colors ${
                    isLastOpened
                      ? "border-4 border-red-500 hover:border-red-500 ring-2 ring-red-500/50"
                      : "border-outline-variant hover:border-primary"
                  }`}
                  onClick={() => {
                    setLastOpenedKey(key);
                    onFrameSelect(frame);
                    onFrameDetail(frame);
                  }}
                >
                  <img
                    className="w-full h-full object-cover"
                    src={frame.thumbnail_url}
                    alt={`Frame ${frame.frame_index}`}
                    loading="lazy"
                  />
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setLastOpenedKey(key);
                      setZoomFrame(frame);
                    }}
                    title="View larger"
                    aria-label="View larger"
                    className="absolute top-1 right-1 p-1 rounded bg-black/50 text-white opacity-0 group-hover:opacity-100 hover:bg-black/70 transition-opacity"
                  >
                    <Icon name="zoom_in" size={16} />
                  </button>
                  {submissionType !== "qa" && (() => {
                    const entry = quickSubmit[key];
                    const status = entry?.status;
                    const style = QUICK_SUBMIT_STYLE[status ?? "loading"];
                    const isTrack = submissionType === "track";
                    const titleByStatus: Record<QuickSubmitStatus, string> = {
                      loading: "Submitting…",
                      correct: isTrack ? "Added" : "Correct",
                      wrong: "Wrong",
                      duplicate: "Already submitted",
                      error: entry?.message ?? "Submission failed",
                    };
                    return (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleQuickSubmit(frame);
                        }}
                        disabled={status === "loading" || (isTrack && !onAddToTrake)}
                        title={
                          status
                            ? titleByStatus[status]
                            : isTrack
                              ? `Add to ${trakeFocusedLabel ?? "Event"}`
                              : `Submit frame ${frame.frame_idx}`
                        }
                        aria-label={isTrack ? "Add frame to TRAKE event" : "Quick submit frame"}
                        className={`absolute top-1 left-1 p-1 rounded text-white transition-opacity ${
                          status ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                        } ${status ? style.bg : "bg-black/50 hover:bg-primary-container"}`}
                      >
                        {status === "loading" ? (
                          <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                        ) : (
                          <Icon name={status ? style.icon : isTrack ? "playlist_add" : "send"} size={16} />
                        )}
                      </button>
                    );
                  })()}
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent px-1.5 pt-4 pb-1 flex justify-between items-end opacity-0 group-hover:opacity-100 transition-opacity">
                    <span className="font-mono text-mono-sm text-white/90">
                      #{frame.frame_index}
                    </span>
                    {frame.score > 0 && (
                      <span className="text-label-xs text-white/80 bg-black/40 rounded px-1">
                        {(frame.score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      {visibleCount < totalItems && (
        <div
          ref={sentinelRef}
          className="h-8 flex items-center justify-center text-label-sm text-on-surface-variant"
          aria-hidden
        >
          Loading more…
        </div>
      )}
      {zoomFrame && (
        <div
          className="fixed top-topbar-height right-0 bottom-0 left-sidebar-width z-[60] flex items-center justify-center bg-black/90 p-8"
          onClick={() => setZoomFrame(null)}
        >
          <button
            onClick={() => setZoomFrame(null)}
            aria-label="Close larger image"
            className="absolute top-4 right-4 z-10 text-white hover:bg-white/10 rounded-full p-1 transition-colors"
          >
            <Icon name="close" size={24} />
          </button>
          <img
            src={zoomFrame.thumbnail_url}
            alt={`Frame ${zoomFrame.frame_index} larger view`}
            className="max-w-full max-h-full object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </main>
  );
}
