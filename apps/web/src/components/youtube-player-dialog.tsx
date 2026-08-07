"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "./icon";
import { VideoPlayer } from "./video-player";
import type { VideoPlayerHandle } from "./video-player";

export interface YoutubePlayerSubmission {
  frameId: string;
  videoId: string;
  timeSec: string;
}

interface YoutubePlayerDialogProps {
  watchUrl: string;
  videoId?: string;
  submissionType: "track" | "qa" | "kis";
  onSubmissionTypeChange: (type: "track" | "qa" | "kis") => void;
  onClose: () => void;
  onSubmit: (submission: YoutubePlayerSubmission) => void;
}

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 100);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(ms).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}.${String(ms).padStart(2, "0")}`;
}

export function YoutubePlayerDialog({
  watchUrl,
  videoId: initialVideoId,
  submissionType,
  onSubmissionTypeChange,
  onClose,
  onSubmit,
}: YoutubePlayerDialogProps) {
  const videoRef = useRef<VideoPlayerHandle>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoIdInput, setVideoIdInput] = useState(initialVideoId ?? "");
  const [timeInput, setTimeInput] = useState("0.0");

  const captureTime = useCallback(() => {
    if (!videoRef.current) return;
    const t = videoRef.current.getCurrentTime();
    setCurrentTime(t);
    setTimeInput(t.toFixed(1));
  }, []);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [onClose]);

  const inputClass =
    "bg-neutral-800 border border-neutral-700 rounded px-3 py-2 font-mono text-mono-sm text-white focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/80 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="YouTube Player"
        className="bg-surface-container-lowest rounded-xl shadow-2xl w-full max-w-5xl h-[90vh] flex flex-col overflow-hidden relative border border-outline-variant"
      >
        {/* Close */}
        <button
          onClick={onClose}
          aria-label="Close dialog"
          className="absolute top-4 right-4 z-50 text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high rounded-full p-1 transition-colors"
        >
          <Icon name="close" size={20} />
        </button>

        {/* Video */}
        <div className="relative w-full aspect-video bg-black flex-shrink-0">
          <VideoPlayer
            ref={videoRef}
            watchUrl={watchUrl}
            onTimeUpdate={(t) => setCurrentTime(t)}
          />
          {/* Time overlay */}
          <div className="absolute top-4 left-4 bg-black/70 backdrop-blur-md rounded px-3 py-2 font-mono text-mono-sm text-gray-200 border border-white/10">
            <span className="text-white font-bold text-lg">{formatTime(currentTime)}</span>
            <span className="text-gray-400 ml-2">({currentTime.toFixed(2)}s)</span>
          </div>
        </div>

        {/* Controls */}
        <div className="flex-grow p-6 flex flex-col gap-4 overflow-y-auto">
          {/* Mode Toggles */}
          <div className="flex items-center gap-6">
            {(["track", "qa", "kis"] as const).map((mode) => (
              <label key={mode} className="flex items-center gap-2 cursor-pointer group">
                <input
                  type="radio"
                  name="yt-mode"
                  checked={submissionType === mode}
                  onChange={() => onSubmissionTypeChange(mode)}
                  className="form-radio text-primary-container border-outline-variant bg-transparent w-4 h-4"
                />
                <span className="text-label-md text-gray-300 group-hover:text-white transition-colors">
                  {mode.toUpperCase()}
                </span>
              </label>
            ))}
          </div>

          {/* Input Fields */}
          <div className="grid grid-cols-3 gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-label-sm text-gray-400">Frame ID</label>
              <input
                className={inputClass}
                type="text"
                placeholder="(auto from time)"
                value={timeInput}
                onChange={(e) => setTimeInput(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-label-sm text-gray-400">Video ID</label>
              <input
                className={inputClass}
                type="text"
                placeholder="e.g. L21_V001"
                value={videoIdInput}
                onChange={(e) => setVideoIdInput(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-label-sm text-gray-400">Time (s)</label>
              <input
                className={inputClass}
                type="text"
                placeholder="seconds"
                value={timeInput}
                onChange={(e) => setTimeInput(e.target.value)}
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3 mt-auto pt-4">
            <button
              onClick={captureTime}
              className="flex-1 bg-neutral-700 hover:bg-neutral-600 text-white px-6 py-2.5 rounded text-label-md font-bold transition-all flex items-center justify-center gap-2"
            >
              <Icon name="videocam" size={18} />
              Use Current Time ({currentTime.toFixed(1)}s)
            </button>
            <button
              onClick={() =>
                onSubmit({
                  frameId: timeInput,
                  videoId: videoIdInput,
                  timeSec: timeInput,
                })
              }
              disabled={!videoIdInput.trim()}
              className="flex-1 bg-primary-container hover:bg-primary-fixed hover:shadow-lg text-on-primary-container px-6 py-2.5 rounded text-label-md font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Submit {submissionType.toUpperCase()}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
