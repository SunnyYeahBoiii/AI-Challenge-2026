"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "./icon";
import { searchVideoFrames } from "@/lib/api";
import type { FrameResult } from "@/lib/api";
import { VideoPlayer } from "./video-player";
import type { VideoPlayerHandle } from "./video-player";
import { FrameNavigator } from "./frame-navigator";
import { computeFrameId } from "@/lib/frame-id";

export interface FrameSubmission {
  frameId: string;
  videoId: string;
  timeSec: string;
  /** Full QA answer text; only used when submission type is QA. */
  answer?: string;
}

export interface TrakeEventOption {
  id: string;
  displayLabel: string;
}

interface FrameDetailDialogProps {
  frame: FrameResult;
  submissionType: "track" | "qa" | "kis";
  onClose: () => void;
  onSubmit: (submission: FrameSubmission) => void;
  /** TRACK: Events available to add into (E1, E2, …). */
  trakeEvents?: TrakeEventOption[];
  /** Default Event id when opening the dialog (focused Event on the board). */
  trakeFocusedEventId?: string | null;
  onAddToTrake?: (
    submission: FrameSubmission & {
      fps: number;
      frameIdx: number;
      thumbnailUrl: string;
      eventId: string;
    },
  ) => void;
  /** TRAKE single: save the navigated frame back into the chain instead of submitting. */
  onSaveChainFrame?: (frameIdx: number) => void;
  /** Label for the save button, e.g. "Event 2/4". */
  chainEventLabel?: string;
}

export function FrameDetailDialog({
  frame,
  submissionType,
  onClose,
  onSubmit,
  trakeEvents = [],
  trakeFocusedEventId,
  onAddToTrake,
  onSaveChainFrame,
  chainEventLabel,
}: FrameDetailDialogProps) {
  const [allFrames, setAllFrames] = useState<FrameResult[]>([]);
  const [currentFrameIndex, setCurrentFrameIndex] = useState(frame.frame_index);
  const [fetchFrameIndex, setFetchFrameIndex] = useState(frame.frame_index);
  const [allFramesLoading, setAllFramesLoading] = useState(false);
  const [allFramesError, setAllFramesError] = useState<string | null>(null);
  const [showFullscreenImage, setShowFullscreenImage] = useState(false);
  const [qaAnswer, setQaAnswer] = useState("");
  const [trakeTargetEventId, setTrakeTargetEventId] = useState(
    () =>
      trakeFocusedEventId &&
      trakeEvents.some((e) => e.id === trakeFocusedEventId)
        ? trakeFocusedEventId
        : (trakeEvents[0]?.id ?? ""),
  );

  useEffect(() => {
    if (trakeEvents.length === 0) {
      setTrakeTargetEventId("");
      return;
    }
    setTrakeTargetEventId((prev) => {
      if (prev && trakeEvents.some((e) => e.id === prev)) return prev;
      if (
        trakeFocusedEventId &&
        trakeEvents.some((e) => e.id === trakeFocusedEventId)
      ) {
        return trakeFocusedEventId;
      }
      return trakeEvents[0].id;
    });
  }, [trakeEvents, trakeFocusedEventId]);

  const trakeTargetLabel =
    trakeEvents.find((e) => e.id === trakeTargetEventId)?.displayLabel ?? "Event";

  const videoRef = useRef<VideoPlayerHandle>(null);
  const allFramesRef = useRef<FrameResult[]>([]);
  // Cleared once playback time nears the seek target, so a stray mid-seek timeupdate can't snap the navigator back.
  const pendingSeekRef = useRef<number | null>(null);
  const pendingSeekTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const userEditedTimeRef = useRef(false);
  const lastMatchedFrameRef = useRef<FrameResult>(frame);
  // null (not pre-seeded to the initial frame's key) so the sync effect below
  // also arms pendingSeekRef on first mount, not just on later frame changes —
  // otherwise the first open's premature timeupdate ticks (before the initial
  // seek lands) snap currentFrameIndex to the wrong frame.
  const framePropKeyRef = useRef<string | null>(null);
  const timeInputFocusedRef = useRef(false);

  // Escape hatch: clears pendingSeekRef itself if no timeupdate ever lands near the target.
  function beginSeek(time: number) {
    pendingSeekRef.current = time;
    if (pendingSeekTimeoutRef.current) clearTimeout(pendingSeekTimeoutRef.current);
    pendingSeekTimeoutRef.current = setTimeout(() => {
      pendingSeekRef.current = null;
    }, 1500);
  }

  useEffect(() => { allFramesRef.current = allFrames; }, [allFrames]);

  // `frame` identity changes only on a new dialog open or similar-frame click, not on in-window navigator arrows.
  useEffect(() => {
    const key = `${frame.video_id}:${frame.frame_index}`;
    if (framePropKeyRef.current === key) return;
    framePropKeyRef.current = key;
    beginSeek(frame.timestamp);
    setCurrentFrameIndex(frame.frame_index);
    setFetchFrameIndex(frame.frame_index);
    videoRef.current?.seekTo(frame.timestamp);
  }, [frame]);

  // Falls back to the incoming `frame` prop, then the last resolved frame, while the window fetch is in flight.
  const currentFrame = useMemo(() => {
    const found = allFrames.find(
      (f) => f.frame_index === currentFrameIndex && f.video_id === frame.video_id
    );
    if (found) {
      lastMatchedFrameRef.current = found;
      return found;
    }
    if (currentFrameIndex === frame.frame_index) {
      lastMatchedFrameRef.current = frame;
      return frame;
    }
    return lastMatchedFrameRef.current;
  }, [allFrames, currentFrameIndex, frame]);

  // Submission fields follow the navigated frame, but stay editable.
  const [videoIdInput, setVideoIdInput] = useState(frame.video_id);
  const [timeInput, setTimeInput] = useState(frame.timestamp.toFixed(1));

  // Ground-truth frame_idx at the keyframe's own timestamp; only recomputed if the user typed a custom time (Milvus has no frame_idx for arbitrary timestamps, and fps there loses precision from float32 storage).
  const computedFrameId = useMemo(() => {
    if (!userEditedTimeRef.current) return currentFrame.frame_idx;
    const t = Number.parseFloat(timeInput) || 0;
    return computeFrameId(t, currentFrame.fps);
  }, [timeInput, currentFrame]);

  useEffect(() => {
    setVideoIdInput(currentFrame.video_id);
    userEditedTimeRef.current = false;
    setTimeInput(currentFrame.timestamp.toFixed(1));
    setShowFullscreenImage(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- key on value, not the fresh object identity a refetch returns
  }, [currentFrame.video_id, currentFrame.frame_index]);

  const currentArrayIndex = useMemo(() => {
    const idx = allFrames.findIndex((f) => f.frame_index === currentFrameIndex);
    return idx >= 0 ? idx : 0;
  }, [allFrames, currentFrameIndex]);

  useEffect(() => {
    let cancelled = false;
    setAllFramesLoading(true);
    setAllFramesError(null);
    searchVideoFrames(frame.video_id, fetchFrameIndex, 5)
      .then((res) => {
        if (!cancelled) {
          setAllFrames(res.results);
          setAllFramesLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setAllFramesError(err.message || "Failed to load frames");
          setAllFramesLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [frame.video_id, fetchFrameIndex]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (showFullscreenImage) {
        setShowFullscreenImage(false);
        return;
      }
      onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("keydown", handleEscape);
      if (pendingSeekTimeoutRef.current) clearTimeout(pendingSeekTimeoutRef.current);
    };
  }, [onClose, showFullscreenImage]);

  const inputClass =
    "bg-neutral-800 border border-neutral-700 rounded px-3 py-2 font-mono text-mono-sm text-white placeholder:text-gray-500 focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Frame ${currentFrameIndex} details`}
        className="bg-surface-container-lowest rounded-xl shadow-2xl w-full max-w-7xl max-h-[90vh] flex flex-col overflow-hidden relative border border-outline-variant"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          aria-label="Close dialog"
          className="absolute top-4 right-4 z-50 text-white hover:bg-white/10 rounded-full p-1 transition-colors"
        >
          <Icon name="close" size={20} />
        </button>

        <div className="grid grid-cols-[minmax(0,1fr)_22rem] flex-1 min-h-0">
          {/* Left: Video + Navigator + Submission */}
          <div className="flex flex-col min-h-0 min-w-0 bg-neutral-900 text-white overflow-y-auto">
            {/* Video — larger but capped so OCR/ASR column always stays visible */}
            <div className="relative w-full h-[420px] overflow-hidden bg-black flex-shrink-0">
              <VideoPlayer
                ref={videoRef}
                src={frame.video_url}
                poster={frame.thumbnail_url}
                initialTime={frame.timestamp}
                onTimeUpdate={(t) => {
                  // Stray timeupdate ticks fire while a seek is still landing (before
                  // `seeked`); acting on them — even just to display `t` — shows a
                  // transient, pre-seek time/frame instead of the one actually requested.
                  if (pendingSeekRef.current !== null) {
                    if (Math.abs(t - pendingSeekRef.current) > 0.4) return;
                    pendingSeekRef.current = null;
                    if (pendingSeekTimeoutRef.current) {
                      clearTimeout(pendingSeekTimeoutRef.current);
                      pendingSeekTimeoutRef.current = null;
                    }
                  }
                  if (!timeInputFocusedRef.current) {
                    userEditedTimeRef.current = true;
                    setTimeInput(t.toFixed(1));
                  }
                  const frames = allFramesRef.current;
                  if (frames.length === 0) return;
                  const closest = frames.reduce((prev, curr) =>
                    Math.abs(curr.timestamp - t) < Math.abs(prev.timestamp - t) ? curr : prev
                  );
                  setCurrentFrameIndex(closest.frame_index);
                  const pos = frames.findIndex(f => f.frame_index === closest.frame_index);
                  const isNearEdge = pos <= 1 || pos >= frames.length - 2;
                  if (isNearEdge) {
                    // A big seek (e.g. dragging the native scrubber far away) lands `closest`
                    // on the stale window's edge, which is still nowhere near `t`. Re-fetching
                    // around that edge frame would only nudge the window one step closer per
                    // tick, crawling toward the target over several fetches. Estimate the real
                    // frame at `t` via fps and jump the fetch window straight there instead.
                    const estimated = computeFrameId(t, closest.fps);
                    const isFarJump = Math.abs(estimated - closest.frame_index) > frames.length;
                    setFetchFrameIndex(isFarJump ? estimated : closest.frame_index);
                  }
                }}
                onReady={() => {}}
              />
            </div>

            {/* Frame Navigator */}
            {allFrames.length === 0 && allFramesLoading ? (
              <div className="flex items-center justify-center py-3 px-4 bg-neutral-900">
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-neutral-600 border-t-white" />
              </div>
            ) : allFrames.length === 0 && allFramesError ? (
              <div className="flex items-center justify-center py-3 px-4 bg-neutral-900 font-mono text-mono-sm text-red-400">
                {allFramesError}
              </div>
            ) : allFrames.length > 0 && (
              <FrameNavigator
                  frames={allFrames}
                  currentArrayIndex={currentArrayIndex}
                  onFrameSelect={(f) => {
                    beginSeek(f.timestamp);
                    setCurrentFrameIndex(f.frame_index);
                    videoRef.current?.seekTo(f.timestamp);
                    const pos = allFrames.findIndex(fr => fr.frame_index === f.frame_index);
                    const isNearEdge = pos <= 1 || pos >= allFrames.length - 2;
                    if (isNearEdge) {
                      setFetchFrameIndex(f.frame_index);
                    }
                  }}
                  onFullscreen={() => setShowFullscreenImage(true)}
                />
            )}

            {/* Submission bar */}
            <div className="flex flex-col gap-3 px-6 py-4 border-t border-neutral-800 bg-neutral-900">
              <div className="flex items-center gap-4 overflow-x-auto">
                <input
                  className={`${inputClass} opacity-80 cursor-not-allowed w-20 flex-shrink-0`}
                  type="text"
                  aria-label="Frame ID"
                  value={computedFrameId}
                  readOnly
                  title="ground-truth frame_idx, or floor(timestamp * fps) if time is edited"
                />

                <input
                  className={`${inputClass} w-28 flex-shrink-0`}
                  type="text"
                  aria-label="Video ID"
                  placeholder="Video ID"
                  value={videoIdInput}
                  onChange={(e) => setVideoIdInput(e.target.value)}
                />

                <div className="flex gap-1 flex-shrink-0">
                  <input
                    className={`${inputClass} w-20`}
                    type="text"
                    aria-label="Time in seconds"
                    placeholder="Time (s)"
                    value={timeInput}
                    onChange={(e) => {
                      userEditedTimeRef.current = true;
                      setTimeInput(e.target.value);
                    }}
                    onFocus={() => { timeInputFocusedRef.current = true; }}
                    onBlur={() => { timeInputFocusedRef.current = false; }}
                  />
                  <button
                    onClick={() => {
                      const t = videoRef.current?.getCurrentTime();
                      if (t === undefined) return;
                      userEditedTimeRef.current = true;
                      setTimeInput(t.toFixed(1));
                    }}
                    title="Use current player time"
                    className="bg-neutral-800 border border-neutral-700 hover:bg-neutral-700 rounded px-2 transition-colors flex-shrink-0"
                  >
                    <Icon name="videocam" size={16} className="text-white" />
                  </button>
                </div>

                {submissionType === "track" && (
                  <select
                    aria-label="TRAKE event target"
                    value={trakeTargetEventId}
                    onChange={(e) => setTrakeTargetEventId(e.target.value)}
                    disabled={trakeEvents.length === 0}
                    className={`${inputClass} w-24 flex-shrink-0`}
                  >
                    {trakeEvents.length === 0 ? (
                      <option value="">No events</option>
                    ) : (
                      trakeEvents.map((ev) => (
                        <option key={ev.id} value={ev.id}>
                          {ev.displayLabel}
                        </option>
                      ))
                    )}
                  </select>
                )}

                {onSaveChainFrame ? (
                  <button
                    onClick={() => onSaveChainFrame(Number(computedFrameId))}
                    disabled={!videoIdInput.trim()}
                    title="Scrub the video to the right moment, then save this frame into the chain"
                    className="ml-auto flex-shrink-0 bg-primary-container hover:bg-primary-fixed hover:shadow-lg text-on-primary-container px-8 py-2.5 rounded text-label-md font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {`Save ${chainEventLabel ?? "frame"} #${computedFrameId}`}
                  </button>
                ) : (
                <button
                  onClick={() => {
                    if (submissionType === "track" && onAddToTrake) {
                      if (!trakeTargetEventId) return;
                      onAddToTrake({
                        frameId: String(computedFrameId),
                        videoId: videoIdInput,
                        timeSec: timeInput,
                        fps: currentFrame.fps,
                        frameIdx: Number(computedFrameId),
                        thumbnailUrl: currentFrame.thumbnail_url,
                        eventId: trakeTargetEventId,
                      });
                      return;
                    }
                    onSubmit({
                      frameId: String(computedFrameId),
                      videoId: videoIdInput,
                      timeSec: timeInput,
                      ...(submissionType === "qa" ? { answer: qaAnswer } : {}),
                    });
                  }}
                  disabled={
                    !videoIdInput.trim() ||
                    (submissionType === "qa" && !qaAnswer.trim()) ||
                    (submissionType === "track" &&
                      (!onAddToTrake || !trakeTargetEventId))
                  }
                  className="ml-auto flex-shrink-0 bg-primary-container hover:bg-primary-fixed hover:shadow-lg text-on-primary-container px-8 py-2.5 rounded text-label-md font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {submissionType === "track"
                    ? `Add to ${trakeTargetLabel}`
                    : `Submit Frame ${computedFrameId}`}
                </button>
                )}
              </div>

              {submissionType === "qa" && (
                <textarea
                  id="qa-answer-detail"
                  value={qaAnswer}
                  onChange={(e) => setQaAnswer(e.target.value)}
                  placeholder="QA answer…"
                  rows={3}
                  aria-label="QA answer"
                  className="w-full min-h-[4.5rem] resize-y rounded border border-neutral-700 bg-neutral-800 px-3 py-2 font-mono text-mono-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-container"
                />
              )}
            </div>
          </div>

          {/* Right: Metadata panel — fixed column so video cannot eat this space */}
          <div className="min-h-0 border-l border-neutral-800 bg-neutral-900 text-white flex flex-col overflow-hidden">
            <div className="px-4 py-3 border-b border-neutral-800 flex-shrink-0">
              <h3 className="text-label-md font-semibold text-gray-300">Frame Metadata</h3>
              <p className="text-mono-sm text-gray-500 mt-0.5">Frame {currentFrame.frame_index}</p>
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 flex flex-col gap-4">
              <div className="flex flex-col min-h-0 flex-1">
                <h4 className="text-label-md font-medium text-gray-400 mb-1.5 flex items-center gap-1.5 flex-shrink-0">
                  <Icon name="text_fields" size={14} />
                  OCR Text
                </h4>
                <div className="bg-neutral-800 rounded-lg p-3 text-mono-sm text-gray-300 whitespace-pre-wrap break-words min-h-[4rem] flex-1 overflow-y-auto">
                  {currentFrame.ocr_text || <span className="text-gray-600 italic">No OCR text</span>}
                </div>
              </div>
              <div className="flex flex-col min-h-0 flex-[1.4]">
                <h4 className="text-label-md font-medium text-gray-400 mb-1.5 flex items-center gap-1.5 flex-shrink-0">
                  <Icon name="graphic_eq" size={14} />
                  ASR Text
                </h4>
                <div className="bg-neutral-800 rounded-lg p-3 text-mono-sm text-gray-300 whitespace-pre-wrap break-words min-h-[4rem] flex-1 overflow-y-auto">
                  {currentFrame.asr_text || <span className="text-gray-600 italic">No ASR text</span>}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Fullscreen keyframe image */}
      {showFullscreenImage && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/90 p-8"
          onClick={(e) => { e.stopPropagation(); setShowFullscreenImage(false); }}
        >
          <button
            onClick={() => setShowFullscreenImage(false)}
            aria-label="Close fullscreen image"
            className="absolute top-4 right-4 z-10 text-white hover:bg-white/10 rounded-full p-1 transition-colors"
          >
            <Icon name="close" size={24} />
          </button>
          <img
            src={currentFrame.thumbnail_url}
            alt={`Frame ${currentFrameIndex} keyframe fullscreen`}
            className="max-w-full max-h-full object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}
