"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { Icon } from "./icon";
import { classifyDresSubmit, fetchFrameContexts, getModelStatus, submitFrameToDres } from "@/lib/api";
import type {
  FrameContext,
  FrameContextWindow,
  FrameResult,
  TemporalSearchResponse,
} from "@/lib/api";
import {
  buildContextWindows,
  contextCacheKey,
  mergeContextFrames,
  type RenderedFrame,
} from "@/lib/result-context";
import { TRAKE_FRAME_MIME } from "@/lib/trake-types";

const FRAME_PAGE_SIZE = 48;
const VIDEO_PAGE_SIZE = 12;

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
  result: TemporalSearchResponse;
  queryCount: number;
  isVideoBrowse: boolean;
  viewMode: "grouped" | "continuous";
  onFrameSelect: (frame: FrameResult) => void;
  onFrameDetail: (frame: FrameResult) => void;
  isLoading?: boolean;
  submissionType: "track" | "qa" | "kis";
  dresSessionId: string | null;
  dresEvaluationId: string | null;
  dresUrl?: string;
  gridCols?: number;
  hasSearched?: boolean;
  trakeFocusedLabel?: string;
  onAddToTrake?: (frame: FrameResult) => void;
  submitMode?: "dres" | "cloud";
  onCloudQuickSubmit?: (frame: FrameResult) => void;
  isInteractionDisabled?: boolean;
}

export function ResultsPanel({
  result,
  queryCount,
  isVideoBrowse,
  viewMode,
  onFrameSelect,
  onFrameDetail,
  isLoading,
  submissionType,
  dresSessionId,
  dresEvaluationId,
  dresUrl,
  gridCols = 6,
  hasSearched = false,
  trakeFocusedLabel,
  onAddToTrake,
  submitMode = "dres",
  onCloudQuickSubmit,
  isInteractionDisabled = false,
}: ResultsPanelProps) {
  const [visibleUnitCount, setVisibleUnitCount] = useState(VIDEO_PAGE_SIZE);
  const [zoomFrame, setZoomFrame] = useState<FrameResult | null>(null);
  const [lastOpenedKey, setLastOpenedKey] = useState<string | null>(null);
  const [selectedFrameKey, setSelectedFrameKey] = useState<string | null>(null);
  const [quickSubmit, setQuickSubmit] = useState<
    Record<string, { status: QuickSubmitStatus; message?: string }>
  >({});
  const [contextCollection, setContextCollection] = useState<string | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => new Set());
  const [contextLoading, setContextLoading] = useState<Record<string, boolean>>({});
  const [contextErrors, setContextErrors] = useState<Record<string, string>>({});
  const [contextRevision, setContextRevision] = useState(0);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const scrollRootRef = useRef<HTMLElement | null>(null);
  const contextCacheRef = useRef(new Map<string, FrameContext>());
  const contextInFlightRef = useRef(new Set<string>());
  const resultVersionRef = useRef(0);

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
        dresUrl,
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

  useEffect(() => {
    const version = ++resultVersionRef.current;
    setExpandedGroups(new Set());
    setContextLoading({});
    setContextErrors({});
    void getModelStatus()
      .then(({ status }) => {
        if (version === resultVersionRef.current) {
          setContextCollection(status.state === "ready" ? status.collection_name : null);
        }
      })
      .catch(() => {
        if (version === resultVersionRef.current) setContextCollection(null);
      });
  }, [result]);

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

  const canExpandContext = (hasVideo: boolean): boolean =>
    hasVideo && !isVideoBrowse && (viewMode === "grouped" || queryCount > 1);

  const prefetchWindows = useMemo(
    () => displayGroups.flatMap((group) => (
      canExpandContext(group.video !== null) ? buildContextWindows(group.frames) : []
    )),
    [displayGroups, isVideoBrowse, queryCount, viewMode],
  );

  const loadContextWindows = async (windows: FrameContextWindow[]) => {
    if (!contextCollection || windows.length === 0) return;
    const missing = windows.filter((window) => {
      const key = contextCacheKey(contextCollection, window);
      return !contextCacheRef.current.has(key) && !contextInFlightRef.current.has(key);
    });
    if (missing.length === 0) return;

    const keys = missing.map((window) => contextCacheKey(contextCollection, window));
    keys.forEach((key) => contextInFlightRef.current.add(key));
    const resultVersion = resultVersionRef.current;
    setContextLoading((current) => ({
      ...current,
      ...Object.fromEntries(keys.map((key) => [key, true])),
    }));
    setContextErrors((current) => {
      const next = { ...current };
      keys.forEach((key) => delete next[key]);
      return next;
    });
    try {
      const response = await fetchFrameContexts(missing);
      if (resultVersion !== resultVersionRef.current) return;
      if (response.collection_name !== contextCollection) {
        setContextErrors((current) => ({
          ...current,
          ...Object.fromEntries(keys.map((key) => [key, "Active model changed. Search again."])),
        }));
        return;
      }
      response.contexts.forEach((context) => {
        const key = contextCacheKey(contextCollection, context);
        contextCacheRef.current.set(key, context);
        [...context.before, ...context.after].forEach((frame) => {
          const image = new Image();
          image.src = frame.thumbnail_url;
        });
      });
      setContextRevision((revision) => revision + 1);
    } catch (error) {
      if (resultVersion !== resultVersionRef.current) return;
      const message = isAxiosError(error)
        ? (error.response?.data as { error?: { message?: string } } | undefined)?.error?.message ?? "Context lookup failed"
        : "Context lookup failed";
      setContextErrors((current) => ({
        ...current,
        ...Object.fromEntries(keys.map((key) => [key, message])),
      }));
    } finally {
      keys.forEach((key) => contextInFlightRef.current.delete(key));
      if (resultVersion === resultVersionRef.current) {
        setContextLoading((current) => {
          const next = { ...current };
          keys.forEach((key) => delete next[key]);
          return next;
        });
      }
    }
  };

  useEffect(() => {
    void loadContextWindows(prefetchWindows);
  }, [contextCollection, prefetchWindows]);

  const renderedGroups = useMemo(() => displayGroups.map((group) => {
    const isExpandable = canExpandContext(group.video !== null);
    const windows = isExpandable ? buildContextWindows(group.frames) : [];
    const isExpanded = expandedGroups.has(group.key);
    const contexts = contextCollection
      ? windows.flatMap((window) => {
          const context = contextCacheRef.current.get(contextCacheKey(contextCollection, window));
          return context ? [context] : [];
        })
      : [];
    const frames: RenderedFrame[] = isExpanded
      ? mergeContextFrames(group.frames, contexts)
      : group.frames.map((frame) => ({ frame, kind: "official" }));
    return {
      ...group,
      frames,
      officialFrameCount: group.frames.length,
      isExpandable,
      windows,
      isExpanded,
    };
  }), [contextCollection, contextRevision, displayGroups, expandedGroups, isVideoBrowse, queryCount, viewMode]);

  const navigableFrames = useMemo(
    () => renderedGroups.flatMap((group) => group.frames.map(({ frame }) => frame)),
    [renderedGroups],
  );

  useEffect(() => {
    const firstFrame = navigableFrames[0];
    const firstKey = firstFrame ? `${firstFrame.video_id}-${firstFrame.frame_index}` : null;
    setSelectedFrameKey(firstKey);
    if (firstKey) requestAnimationFrame(() => document.getElementById(`result-${firstKey}`)?.focus());
  }, [navigableFrames]);

  useEffect(() => {
    if (!isInteractionDisabled && selectedFrameKey) {
      requestAnimationFrame(() => document.getElementById(`result-${selectedFrameKey}`)?.focus());
    }
  }, [isInteractionDisabled, selectedFrameKey]);

  const selectedFrame = useMemo(
    () => navigableFrames.find(
      (frame) => `${frame.video_id}-${frame.frame_index}` === selectedFrameKey,
    ) ?? null,
    [navigableFrames, selectedFrameKey],
  );

  const visibleFrameCount = displayGroups.reduce((total, group) => total + group.frames.length, 0);
  const visibleVideoCount = new Set(
    displayGroups.flatMap((group) => group.frames.map((frame) => frame.video_id))
  ).size;

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

  const openFrame = (frame: FrameResult) => {
    const key = `${frame.video_id}-${frame.frame_index}`;
    setSelectedFrameKey(key);
    setLastOpenedKey(key);
    onFrameSelect(frame);
    onFrameDetail(frame);
  };

  const quickSubmitFrame = (frame: FrameResult) => {
    if (submitMode === "cloud") {
      onCloudQuickSubmit?.(frame);
      return;
    }
    void handleQuickSubmit(frame);
  };

  useEffect(() => {
    const isEditableTarget = (target: EventTarget | null) =>
      target instanceof HTMLElement &&
      (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

    const onKeyDown = (event: KeyboardEvent) => {
      const isInResultsPanel = event.target instanceof Element && Boolean(event.target.closest("[data-results-panel]"));
      if (!isInResultsPanel) return;
      if (isInteractionDisabled || !selectedFrame || isEditableTarget(event.target)) return;
      if (event.altKey && !event.ctrlKey && !event.shiftKey && !event.metaKey && event.key === "Enter" && submissionType !== "qa") {
        event.preventDefault();
        quickSubmitFrame(selectedFrame);
        return;
      }

      if (event.altKey && !event.ctrlKey && !event.shiftKey && !event.metaKey && event.key.toLowerCase() === "a" && onAddToTrake) {
        event.preventDefault();
        onAddToTrake(selectedFrame);
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [gridCols, isInteractionDisabled, navigableFrames, onAddToTrake, selectedFrame, selectedFrameKey, submissionType, submitMode]);

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
      data-results-panel
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
        {renderedGroups.map((group, groupIndex) => (
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
                    ? `${group.officialFrameCount} valid frames`
                    : `best sequence · ${group.video.best_sequence.total_span_seconds.toFixed(1)}s`}
                </span>
                {group.video.has_vector_score !== false && (
                  <span className="text-label-xs text-on-surface-variant bg-surface-container rounded px-1.5 py-0.5">
                    {(group.video.video_score * 100).toFixed(0)}%
                  </span>
                )}
                {group.isExpandable && (
                  <button
                    type="button"
                    disabled={!contextCollection}
                    onClick={() => {
                      const nextExpanded = !group.isExpanded;
                      setExpandedGroups((current) => {
                        const next = new Set(current);
                        if (nextExpanded) next.add(group.key);
                        else next.delete(group.key);
                        return next;
                      });
                      if (nextExpanded) void loadContextWindows(group.windows);
                    }}
                    title={contextCollection ? "Show or hide nearby stored keyframes" : "Waiting for active model"}
                    className="ml-1 rounded border border-outline-variant px-2 py-0.5 text-label-xs text-on-surface-variant transition-colors hover:border-primary hover:text-primary disabled:cursor-wait disabled:opacity-50"
                  >
                    {group.isExpanded ? "Collapse context" : "Expand context"}
                  </button>
                )}
                {group.isExpandable && (() => {
                  const keys = group.windows.map((window) => contextCollection && contextCacheKey(contextCollection, window));
                  const isLoadingContext = keys.some((key) => key && contextLoading[key]);
                  const error = keys.map((key) => key && contextErrors[key]).find(Boolean);
                  if (isLoadingContext) return <span className="text-label-xs text-on-surface-variant">Loading context…</span>;
                  if (error) return <span className="text-label-xs text-error">{error}</span>;
                  return null;
                })()}
                <div className="h-px bg-outline-variant flex-1" />
              </div>
            )}
            <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${gridCols}, minmax(0, 1fr))` }}>
              {group.frames.map(({ frame, kind }) => {
                const key = `${frame.video_id}-${frame.frame_index}`;
                const isLastOpened = lastOpenedKey === key;
                return (
                <div
                  key={key}
                  id={`result-${key}`}
                  tabIndex={0}
                  role="group"
                  aria-label={`Frame ${frame.frame_index} from ${frame.video_id}`}
                  draggable={submissionType === "track"}
                  onDragStart={(e) => {
                    if (submissionType !== "track") return;
                    e.dataTransfer.setData(
                      TRAKE_FRAME_MIME,
                      JSON.stringify(frame),
                    );
                    e.dataTransfer.effectAllowed = "copy";
                  }}
                  className={`relative group cursor-pointer aspect-video bg-surface-container overflow-hidden border rounded-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                    isLastOpened
                      ? "border-4 border-red-500 hover:border-red-500 ring-2 ring-red-500/50"
                      : selectedFrameKey === key
                        ? "border-primary ring-2 ring-primary/40"
                        : "border-outline-variant hover:border-primary"
                  }`}
                  onFocus={() => setSelectedFrameKey(key)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      openFrame(frame);
                    }
                    if (event.key.toLowerCase() === "z") {
                      event.preventDefault();
                      setSelectedFrameKey(key);
                      setZoomFrame(frame);
                    }
                  }}
                  onClick={() => openFrame(frame)}
                >
                  <img
                    className="w-full h-full object-cover"
                    src={frame.thumbnail_url}
                    alt={`Frame ${frame.frame_index}`}
                    loading="lazy"
                  />
                  <div className="absolute top-1 left-8 flex gap-1">
                    {kind === "official" && (frame.matches?.map((match) => match.query_index) ??
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
                          quickSubmitFrame(frame);
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
                      {frame.video_id} · #{frame.frame_index}
                    </span>
                    {kind === "official" && !frame.filter_only && frame.score > 0 && (
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
