"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { Icon } from "./icon";
import { classifyDresSubmit, fetchRepeatFrameDetails, submitFrameToDres } from "@/lib/api";
import type { FrameResult, RepeatFrameDetails, TemporalSearchResponse } from "@/lib/api";
import {
  canonicalRepeatRequestKey,
  frameRepeatKey,
  repeatHoverItems,
  repeatHoverPlacement,
} from "@/lib/repeat-detection";
import { TRAKE_FRAME_MIME } from "@/lib/trake-types";

const FRAME_PAGE_SIZE = 48;
const VIDEO_PAGE_SIZE = 12;
/** Mirrors RepeatFramesRequest.frames max_length on the API. */
const REPEAT_FRAME_BATCH_SIZE = 1500;

function uniqueRepeatFrames(frames: FrameResult[]): FrameResult[] {
  const unique = new Map<string, FrameResult>();
  for (const frame of frames) {
    unique.set(frameRepeatKey(frame), frame);
  }
  return [...unique.values()];
}

/** Repeats are relative to the displayed set, so each batch is scored as a whole. */
function splitRepeatBatches(frames: FrameResult[]): FrameResult[][] {
  const unique = uniqueRepeatFrames(frames);
  const batches: FrameResult[][] = [];
  for (let index = 0; index < unique.length; index += REPEAT_FRAME_BATCH_SIZE) {
    batches.push(unique.slice(index, index + REPEAT_FRAME_BATCH_SIZE));
  }
  return batches;
}

/** How long a result indicator stays on the card before reverting to idle. */
const QUICK_SUBMIT_RESULT_MS = 2500;

type QuickSubmitStatus = "loading" | "correct" | "wrong" | "duplicate" | "error";
type RepeatHoverState = { key: string; placement: "left" | "right" };

const QUICK_SUBMIT_STYLE: Record<QuickSubmitStatus, { bg: string; icon: string }> = {
  loading: { bg: "bg-black/50", icon: "send" },
  correct: { bg: "bg-green-600", icon: "check_circle" },
  wrong: { bg: "bg-orange-600", icon: "cancel" },
  duplicate: { bg: "bg-orange-600", icon: "content_copy" },
  error: { bg: "bg-red-600", icon: "error" },
};

interface ResultsPanelProps {
  result: TemporalSearchResponse;
  queryCount: number;
  viewMode: "grouped" | "continuous";
  onFrameSelect: (frame: FrameResult) => void;
  onFrameDetail: (frame: FrameResult) => void;
  isLoading?: boolean;
  submissionType: "track" | "qa" | "kis";
  dresSessionId: string | null;
  dresEvaluationId: string | null;
  gridCols?: number;
  hasSearched?: boolean;
  trakeFocusedLabel?: string;
  onAddToTrake?: (frame: FrameResult) => void;
  submitMode?: "dres" | "cloud";
  onCloudQuickSubmit?: (frame: FrameResult) => void;
}

export function ResultsPanel({
  result,
  queryCount,
  viewMode,
  onFrameSelect,
  onFrameDetail,
  isLoading,
  submissionType,
  dresSessionId,
  dresEvaluationId,
  gridCols = 6,
  hasSearched = false,
  trakeFocusedLabel,
  onAddToTrake,
  submitMode = "dres",
  onCloudQuickSubmit,
}: ResultsPanelProps) {
  const [visibleUnitCount, setVisibleUnitCount] = useState(VIDEO_PAGE_SIZE);
  const [zoomFrame, setZoomFrame] = useState<FrameResult | null>(null);
  const [lastOpenedKey, setLastOpenedKey] = useState<string | null>(null);
  const [quickSubmit, setQuickSubmit] = useState<
    Record<string, { status: QuickSubmitStatus; message?: string }>
  >({});
  const repeatAbortRef = useRef<AbortController | null>(null);
  const repeatCacheRef = useRef<Map<string, Record<string, RepeatFrameDetails>>>(new Map());
  const [repeatFrameDetails, setRepeatFrameDetails] = useState<Record<string, RepeatFrameDetails>>({});
  const [repeatHover, setRepeatHover] = useState<RepeatHoverState | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const scrollRootRef = useRef<HTMLElement | null>(null);

  const openRepeatHover = useCallback((target: HTMLElement, key: string) => {
    setRepeatHover({
      key,
      placement: repeatHoverPlacement(target.getBoundingClientRect(), window.innerWidth),
    });
  }, []);

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
    if (!dresSessionId || !dresEvaluationId) {
      setQuickSubmit((s) => ({
        ...s,
        [key]: { status: "error", message: "Log in and select a DRES evaluation" },
      }));
      setTimeout(() => clearQuickSubmit(key), QUICK_SUBMIT_RESULT_MS);
      return;
    }
    setQuickSubmit((s) => ({ ...s, [key]: { status: "loading" } }));
    try {
      const data = await submitFrameToDres({
        frameId: String(frame.frame_idx),
        videoId: frame.video_id,
        timestamp: frame.timestamp,
        submissionType,
        sessionId: dresSessionId,
        evaluationId: dresEvaluationId,
      });
      const status = classifyDresSubmit(data);
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
    setVisibleUnitCount(viewMode === "continuous" && queryCount <= 1 ? FRAME_PAGE_SIZE : VIDEO_PAGE_SIZE);
  }, [result, viewMode, queryCount]);

  const continuousFrames = useMemo(
    () =>
      result.videos
        .flatMap((video) => video.valid_frames)
        .sort(
          (left, right) =>
            right.score - left.score ||
            (left.retrieval_rank ?? Number.MAX_SAFE_INTEGER) -
              (right.retrieval_rank ?? Number.MAX_SAFE_INTEGER)
        ),
    [result.videos]
  );

  const paginatesFrames = viewMode === "continuous" && queryCount <= 1;
  const totalUnits = paginatesFrames ? continuousFrames.length : result.videos.length;
  const pageSize = paginatesFrames ? FRAME_PAGE_SIZE : VIDEO_PAGE_SIZE;

  const displayGroups = useMemo(() => {
    if (paginatesFrames) {
      return [{ key: "continuous", video: null, frames: continuousFrames.slice(0, visibleUnitCount) }];
    }
    return result.videos.slice(0, visibleUnitCount).map((video) => ({
      key: video.video_id,
      video,
      frames:
        viewMode === "grouped"
          ? video.valid_frames
          : video.best_sequence.frames,
    }));
  }, [continuousFrames, paginatesFrames, result.videos, viewMode, visibleUnitCount]);

  const visibleFrameCount = displayGroups.reduce((total, group) => total + group.frames.length, 0);
  const visibleVideoCount = new Set(
    displayGroups.flatMap((group) => group.frames.map((frame) => frame.video_id))
  ).size;

  const repeatBatches = useMemo(() => {
    const batches = splitRepeatBatches(displayGroups.flatMap((group) => group.frames));
    return [
      ...new Map(batches.map((frames) => [canonicalRepeatRequestKey(frames), frames])).values(),
    ];
  }, [displayGroups]);

  useEffect(() => {
    repeatAbortRef.current?.abort();
    repeatCacheRef.current.clear();
    setRepeatFrameDetails({});
    setRepeatHover(null);
  }, [result]);

  useEffect(() => {
    const missing = repeatBatches.filter(
      (frames) => !repeatCacheRef.current.has(canonicalRepeatRequestKey(frames))
    );
    if (missing.length === 0) return;

    repeatAbortRef.current?.abort();
    const controller = new AbortController();
    repeatAbortRef.current = controller;
    Promise.all(
      missing.map(async (frames) => ({
        key: canonicalRepeatRequestKey(frames),
        details: await fetchRepeatFrameDetails(
          frames.map(({ video_id, frame_index, timestamp }) => ({
            video_id,
            frame_index,
            timestamp,
          })),
          controller.signal
        ),
      }))
    )
      .then((responses) => {
        if (controller.signal.aborted) return;
        const additions: Record<string, RepeatFrameDetails> = {};
        for (const { key, details } of responses) {
          repeatCacheRef.current.set(key, details);
          Object.assign(additions, details);
        }
        setRepeatFrameDetails((current) => ({ ...current, ...additions }));
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          console.warn("Repeat detection unavailable:", error);
        }
      });
    return () => controller.abort();
  }, [repeatBatches]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    const root = scrollRootRef.current;
    if (!sentinel || !root || visibleUnitCount >= totalUnits) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisibleUnitCount((count) => Math.min(count + pageSize, totalUnits));
        }
      },
      { root, rootMargin: "400px", threshold: 0 }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [pageSize, totalUnits, visibleUnitCount]);

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

  if (result.total_valid_frames === 0) {
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
          {viewMode === "continuous" && queryCount > 1 ? (
            <>
              Showing {visibleFrameCount} best-sequence frames · {visibleVideoCount} of{" "}
              {result.total_videos} videos · {result.total_valid_frames} valid frames available
            </>
          ) : (
            <>
              Showing {visibleFrameCount} of {result.total_valid_frames}{" "}
              {result.total_valid_frames === 1 ? "valid frame" : "valid frames"} ·{" "}
              {visibleVideoCount} of {result.total_videos} videos
            </>
          )}
        </span>
      </div>
      <div className="flex flex-col gap-6">
        {displayGroups.map((group, groupIndex) => (
          <div
            key={group.key || groupIndex}
            className="flex flex-col gap-2"
          >
            {group.video && (
              <div className="flex items-center gap-2 py-1">
                <Icon name="movie" size={16} className="text-on-surface-variant" />
                <span className="text-label-md text-on-surface">{group.video.video_id}</span>
                <span className="text-label-sm text-on-surface-variant">
                  {viewMode === "grouped"
                    ? `${group.frames.length} valid frames`
                    : `best sequence · ${group.video.best_sequence.total_span_seconds.toFixed(1)}s`}
                </span>
                {group.video.has_vector_score !== false && (
                  <span className="text-label-xs text-on-surface-variant bg-surface-container rounded px-1.5 py-0.5">
                    {(group.video.video_score * 100).toFixed(0)}%
                  </span>
                )}
                <div className="h-px bg-outline-variant flex-1" />
              </div>
            )}
            <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))` }}>
              {group.frames.map((frame) => {
                const key = `${frame.video_id}-${frame.frame_index}`;
                const isLastOpened = lastOpenedKey === key;
                const repeatKey = frameRepeatKey(frame);
                const repeatItems = repeatFrameDetails[repeatKey]
                  ? repeatHoverItems(repeatFrameDetails[repeatKey])
                  : [];
                const isRepeat = repeatItems.length > 0;
                return (
                <div
                  key={key}
                  className="relative"
                  onMouseEnter={(e) => {
                    if (isRepeat) openRepeatHover(e.currentTarget, repeatKey);
                  }}
                  onMouseLeave={() => {
                    setRepeatHover((current) => (current?.key === repeatKey ? null : current));
                  }}
                >
                <div
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
                  <div className="absolute top-1 left-8 flex gap-1">
                    {isRepeat && (
                      <span
                        className="rounded bg-red-600 px-1.5 py-0.5 text-label-xs font-bold text-white shadow"
                        onMouseEnter={(e) => openRepeatHover(e.currentTarget, repeatKey)}
                        onFocus={(e) => openRepeatHover(e.currentTarget, repeatKey)}
                        onClick={(e) => e.stopPropagation()}
                        tabIndex={0}
                        aria-describedby={
                          repeatHover?.key === repeatKey ? `repeat-details-${key}` : undefined
                        }
                      >
                        REPEAT
                      </span>
                    )}
                    {(frame.matches?.map((match) => match.query_index) ??
                      (frame.query_index !== undefined ? [frame.query_index] : [])).map((queryIndex) => (
                      <span
                        key={queryIndex}
                        className="rounded bg-primary/90 px-1.5 py-0.5 text-label-xs font-bold text-on-primary shadow"
                        title={`Matches query ${queryIndex + 1}`}
                      >
                        Q{queryIndex + 1}
                      </span>
                    ))}
                  </div>
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
                  {onAddToTrake && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onAddToTrake(frame);
                      }}
                      title={trakeFocusedLabel ? `Add to ${trakeFocusedLabel}` : "Add to TRAKE event"}
                      aria-label="Add to TRAKE event"
                      className="absolute top-1 right-8 p-1 rounded bg-black/50 text-white opacity-0 group-hover:opacity-100 hover:bg-primary-container transition-opacity"
                    >
                      <Icon name="playlist_add" size={16} />
                    </button>
                  )}
                  {submissionType !== "qa" && (() => {
                    const entry = quickSubmit[key];
                    const status = entry?.status;
                    const style = QUICK_SUBMIT_STYLE[status ?? "loading"];
                    const titleByStatus: Record<QuickSubmitStatus, string> = {
                      loading: "Submitting…",
                      correct: "Correct",
                      wrong: "Wrong",
                      duplicate: "Already submitted",
                      error: entry?.message ?? "Submission failed",
                    };
                    return (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (submitMode === "cloud") {
                            onCloudQuickSubmit?.(frame);
                          } else {
                            handleQuickSubmit(frame);
                          }
                        }}
                        disabled={status === "loading"}
                        title={status ? titleByStatus[status] : `Submit frame ${frame.frame_idx}`}
                        aria-label="Quick submit frame"
                        className={`absolute top-1 left-1 p-1 rounded text-white transition-opacity ${
                          status ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                        } ${status ? style.bg : "bg-black/50 hover:bg-primary-container"}`}
                      >
                        {status === "loading" ? (
                          <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                        ) : (
                          <Icon name={status ? style.icon : "send"} size={16} />
                        )}
                      </button>
                    );
                  })()}
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent px-1.5 pt-4 pb-1 flex justify-between items-end opacity-0 group-hover:opacity-100 transition-opacity">
                    <span className="font-mono text-mono-sm text-white/90">
                      #{frame.frame_index}
                    </span>
                    {!frame.filter_only && frame.score > 0 && (
                      <span className="text-label-xs text-white/80 bg-black/40 rounded px-1">
                        {(frame.score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </div>
                {isRepeat && repeatHover?.key === repeatKey && (
                  <div
                    id={`repeat-details-${key}`}
                    role="tooltip"
                    className={`absolute top-0 z-40 flex w-56 flex-col gap-3 rounded-lg border-2 border-red-500/70 bg-surface-container-high p-3 shadow-xl ${
                      repeatHover.placement === "right" ? "left-full ml-3" : "right-full mr-3"
                    }`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {repeatItems.map((item) => (
                      <div
                        key={item.key}
                        className="overflow-hidden rounded-md border border-outline-variant bg-surface-container"
                      >
                        <img
                          src={item.thumbnailUrl}
                          alt={`${item.label}: ${item.identity}`}
                          className="aspect-video w-full object-cover"
                          loading="lazy"
                        />
                        <div className="px-2 py-1.5 text-label-sm leading-snug">
                          <div className="font-bold text-red-400">{item.label}</div>
                          <div className="break-words text-on-surface-variant">{item.identity}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      {visibleUnitCount < totalUnits && (
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
