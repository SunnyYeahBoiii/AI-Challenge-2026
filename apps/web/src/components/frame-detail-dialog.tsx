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
}

interface FrameDetailDialogProps {
  frame: FrameResult;
  submissionType: "track" | "qa" | "kis";
  onSubmissionTypeChange: (type: "track" | "qa" | "kis") => void;
  onClose: () => void;
  onSubmit: (submission: FrameSubmission) => void;
}

export function FrameDetailDialog({
  frame,
  submissionType,
  onSubmissionTypeChange,
  onClose,
  onSubmit,
}: FrameDetailDialogProps) {
  const [allFrames, setAllFrames] = useState<FrameResult[]>([]);
  const [currentFrameIndex, setCurrentFrameIndex] = useState(frame.frame_index);
  const [fetchFrameIndex, setFetchFrameIndex] = useState(frame.frame_index);
  const [allFramesLoading, setAllFramesLoading] = useState(false);
  const [allFramesError, setAllFramesError] = useState<string | null>(null);
  const [showFullscreenImage, setShowFullscreenImage] = useState(false);

  const videoRef = useRef<VideoPlayerHandle>(null);
  const allFramesRef = useRef<FrameResult[]>([]);
  // Cleared once playback time nears the seek target, so a stray mid-seek timeupdate can't snap the navigator back.
  const pendingSeekRef = useRef<number | null>(null);
  const pendingSeekTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const userEditedTimeRef = useRef(false);
  const lastMatchedFrameRef = useRef<FrameResult>(frame);
  const framePropKeyRef = useRef(`${frame.video_id}:${frame.frame_index}`);
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
    beginSeek(frame.pts_time);
    setCurrentFrameIndex(frame.frame_index);
    setFetchFrameIndex(frame.frame_index);
    videoRef.current?.seekTo(frame.pts_time);
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
  const [timeInput, setTimeInput] = useState(frame.pts_time.toFixed(1));

  // Ground-truth frame_idx at the keyframe's own timestamp; only recomputed if the user typed a custom time (Milvus has no frame_idx for arbitrary timestamps, and fps there loses precision from float32 storage).
  const computedFrameId = useMemo(() => {
    if (!userEditedTimeRef.current) return currentFrame.frame_idx;
    const t = Number.parseFloat(timeInput) || 0;
    return computeFrameId(t, currentFrame.fps);
  }, [timeInput, currentFrame]);

  useEffect(() => {
    setVideoIdInput(currentFrame.video_id);
    userEditedTimeRef.current = false;
    setTimeInput(currentFrame.pts_time.toFixed(1));
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
        className="bg-surface-container-lowest rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden relative border border-outline-variant"
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

        {/* Video + Navigator */}
        <div className="flex flex-col bg-neutral-900 text-white">
          {/* Video Section */}
          <div className="relative w-full aspect-video bg-black flex-shrink-0">
            <VideoPlayer
              ref={videoRef}
              watchUrl={frame.watch_url}
              initialTime={frame.pts_time}
              onTimeUpdate={(t) => {
                // Live sync: every player tick drives the submit panel directly, not the debounced keyframe snap below.
                if (!timeInputFocusedRef.current) {
                  userEditedTimeRef.current = true;
                  setTimeInput(t.toFixed(1));
                }
                if (pendingSeekRef.current !== null) {
                  if (Math.abs(t - pendingSeekRef.current) > 0.4) return;
                  pendingSeekRef.current = null;
                  if (pendingSeekTimeoutRef.current) {
                    clearTimeout(pendingSeekTimeoutRef.current);
                    pendingSeekTimeoutRef.current = null;
                  }
                }
                const frames = allFramesRef.current;
                if (frames.length === 0) return;
                const closest = frames.reduce((prev, curr) =>
                  Math.abs(curr.pts_time - t) < Math.abs(prev.pts_time - t) ? curr : prev
                );
                setCurrentFrameIndex(closest.frame_index);
                const pos = frames.findIndex(f => f.frame_index === closest.frame_index);
                const isNearEdge = pos <= 1 || pos >= frames.length - 2;
                // Direct call, no debounce: React bails out on a same-value set, so this only actually
                // refetches once per real edge crossing -- a timer here would just get reset by the next
                // 250ms tick before it ever fires (tick period < debounce delay = it never fires).
                if (isNearEdge) {
                  setFetchFrameIndex(closest.frame_index);
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
                  beginSeek(f.pts_time);
                  setCurrentFrameIndex(f.frame_index);
                  videoRef.current?.seekTo(f.pts_time);
                  const pos = allFrames.findIndex(fr => fr.frame_index === f.frame_index);
                  const isNearEdge = pos <= 1 || pos >= allFrames.length - 2;
                  if (isNearEdge) {
                    setFetchFrameIndex(f.frame_index);
                  }
                }}
                onFullscreen={() => setShowFullscreenImage(true)}
              />
          )}
        </div>

        {/* Submission bar - single row */}
        <div className="flex items-center gap-4 px-6 py-4 border-t border-neutral-800 bg-neutral-900 overflow-x-auto">
          {/* Mode Toggles */}
          <div className="flex items-center gap-4 flex-shrink-0">
            {(["track", "qa", "kis"] as const).map((mode) => (
              <label key={mode} className="flex items-center gap-1.5 cursor-pointer group">
                <input
                  type="radio"
                  name="detail-mode"
                  checked={submissionType === mode}
                  onChange={() => onSubmissionTypeChange(mode)}
                  className="form-radio text-primary-container border-neutral-600 bg-transparent w-4 h-4"
                />
                <span className="text-label-md text-gray-400 group-hover:text-white transition-colors">
                  {mode.toUpperCase()}
                </span>
              </label>
            ))}
          </div>

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

          <button
            onClick={() =>
              onSubmit({
                frameId: String(computedFrameId),
                videoId: videoIdInput,
                timeSec: timeInput,
              })
            }
            disabled={!videoIdInput.trim()}
            className="ml-auto flex-shrink-0 bg-primary-container hover:bg-primary-fixed hover:shadow-lg text-on-primary-container px-8 py-2.5 rounded text-label-md font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Submit Frame {computedFrameId}
          </button>
        </div>
      </div>

      {/* Fullscreen keyframe image */}
      {showFullscreenImage && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/90 p-8"
          onClick={() => setShowFullscreenImage(false)}
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
