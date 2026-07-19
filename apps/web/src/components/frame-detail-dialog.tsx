"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "./icon";
import { searchSimilarFrames, searchVideoFrames } from "@/lib/api";
import type { FrameResult } from "@/lib/api";
import { VideoPlayer } from "./video-player";
import type { VideoPlayerHandle } from "./video-player";
import { FrameNavigator } from "./frame-navigator";

interface FrameDetailDialogProps {
  frame: FrameResult;
  onClose: () => void;
  onSubmit: (frame: FrameResult) => void;
}

export function FrameDetailDialog({ frame, onClose, onSubmit }: FrameDetailDialogProps) {
  const [similarFrames, setSimilarFrames] = useState<FrameResult[]>([]);
  const [similarLoading, setSimilarLoading] = useState(false);
  const [allFrames, setAllFrames] = useState<FrameResult[]>([]);
  const [currentFrameIndex, setCurrentFrameIndex] = useState(frame.frame_index);
  const [fetchFrameIndex, setFetchFrameIndex] = useState(frame.frame_index);
  const [allFramesLoading, setAllFramesLoading] = useState(false);
  const [allFramesError, setAllFramesError] = useState<string | null>(null);

  const currentArrayIndex = useMemo(() => {
    const idx = allFrames.findIndex((f) => f.frame_index === currentFrameIndex);
    return idx >= 0 ? idx : 0;
  }, [allFrames, currentFrameIndex]);

  const videoRef = useRef<VideoPlayerHandle>(null);
  const allFramesRef = useRef<FrameResult[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { allFramesRef.current = allFrames; }, [allFrames]);

  useEffect(() => {
    let cancelled = false;
    setSimilarLoading(true);
    searchSimilarFrames(frame.video_id, frame.frame_index).then((res) => {
      if (!cancelled) {
        setSimilarFrames(res.results);
        setSimilarLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [frame.video_id, frame.frame_index]);

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
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("keydown", handleEscape);
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-on-surface/80 backdrop-blur-sm">
      <div className="bg-surface-container-lowest rounded-xl shadow-2xl w-full max-w-6xl h-[90vh] flex overflow-hidden relative border border-outline-variant">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-50 text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high rounded-full p-1 transition-colors"
        >
          <Icon name="close" size={20} />
        </button>

        {/* Left Panel - Video */}
        <div className="w-[60%] flex flex-col bg-[#111111] text-white border-r border-outline-variant">
          {/* Video Section */}
          <div className="relative w-full aspect-video bg-black flex-shrink-0">
            <VideoPlayer
              ref={videoRef}
              watchUrl={frame.watch_url}
              onTimeUpdate={(t) => {
                const frames = allFramesRef.current;
                if (frames.length === 0) return;
                const closest = frames.reduce((prev, curr) =>
                  Math.abs(curr.pts_time - t) < Math.abs(prev.pts_time - t) ? curr : prev
                );
                if (debounceRef.current) clearTimeout(debounceRef.current);
                debounceRef.current = setTimeout(() => {
                  setCurrentFrameIndex(closest.frame_index);
                  const pos = frames.findIndex(f => f.frame_index === closest.frame_index);
                  const isNearEdge = pos <= 1 || pos >= frames.length - 2;
                  if (isNearEdge) {
                    setFetchFrameIndex(closest.frame_index);
                  }
                }, 300);
              }}
              onReady={() => {
                videoRef.current?.seekTo(frame.pts_time);
              }}
            />
            {/* Metadata Overlay */}
            <div className="absolute top-4 right-4 bg-black/60 backdrop-blur-md rounded px-3 py-2 font-mono-sm text-mono-sm text-gray-200 border border-white/10 flex flex-col gap-1">
              <div className="flex justify-between gap-4">
                <span>Frame</span>
                <span className="text-white font-medium">{currentFrameIndex}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span>Video</span>
                <span className="text-white font-medium">{frame.video_id}</span>
              </div>
              {(() => {
                const currentFrame = allFrames.find(f => f.frame_index === currentFrameIndex);
                const t = currentFrame?.pts_time ?? frame.pts_time;
                if (!t) return null;
                return (
                  <div className="flex justify-between gap-4">
                    <span>Time</span>
                    <span className="text-white font-medium">{t.toFixed(0)}ms</span>
                  </div>
                );
              })()}
            </div>
          </div>

          {/* Frame Navigator */}
          {allFramesLoading ? (
            <div className="flex items-center justify-center py-3 px-4 bg-[#111111]">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-white" />
            </div>
          ) : allFramesError ? (
            <div className="flex items-center justify-center py-3 px-4 bg-[#111111] font-mono-sm text-mono-sm text-red-400">
              {allFramesError}
            </div>
          ) : allFrames.length > 0 && (
            <>
              <div className="flex items-center justify-center gap-2 bg-[#111111] py-2 px-4 border-t border-white/5">
                <span className="font-mono-sm text-mono-sm text-gray-400">
                  Frame {currentFrameIndex}
                </span>
              </div>
              <FrameNavigator
                frames={allFrames}
                currentArrayIndex={currentArrayIndex}
                onFrameSelect={(f) => {
                  setCurrentFrameIndex(f.frame_index);
                  videoRef.current?.seekTo(f.pts_time);
                }}
              />
            </>
          )}

          {/* Submission Controls */}
          <div className="flex-grow p-6 flex flex-col gap-4 overflow-y-auto border-t border-white/5">
            <h2 className="font-headline-sm text-headline-sm text-white">
              Frame {currentFrameIndex} from {frame.video_id}
            </h2>

            {/* Mode Toggles */}
            <div className="flex items-center gap-6">
              {["Track", "QA", "KIS"].map((mode) => (
                <label key={mode} className="flex items-center gap-2 cursor-pointer group">
                  <input
                    type="radio"
                    name="detail-mode"
                    defaultChecked={mode === "KIS"}
                    className="form-radio text-primary-container border-outline-variant bg-transparent w-4 h-4"
                  />
                  <span className="font-label-md text-label-md text-gray-300 group-hover:text-white transition-colors">
                    {mode}
                  </span>
                </label>
              ))}
            </div>

            {/* Input Fields */}
            <div className="grid grid-cols-3 gap-4">
              <input
                className="bg-[#222222] border border-[#333333] rounded px-3 py-2 font-mono-sm text-mono-sm text-white focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all"
                type="text"
                placeholder="Frame ID"
                defaultValue={frame.id}
              />
              <input
                className="bg-[#222222] border border-[#333333] rounded px-3 py-2 font-mono-sm text-mono-sm text-white focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all"
                type="text"
                placeholder="Video ID"
                defaultValue={frame.video_id}
              />
              <input
                className="bg-[#222222] border border-[#333333] rounded px-3 py-2 font-mono-sm text-mono-sm text-white focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all"
                type="text"
                placeholder="Time (ms)"
                defaultValue={frame.pts_time.toFixed(0)}
              />
            </div>

            {/* Submit */}
            <div className="mt-auto pt-4">
              <button
                onClick={() => onSubmit(frame)}
                className="w-full bg-primary-container hover:bg-primary-fixed hover:shadow-lg text-on-primary-container px-8 py-2.5 rounded font-label-md text-label-md font-bold transition-all"
              >
                Submit
              </button>
            </div>
          </div>
        </div>

        {/* Right Panel - Similar Frames */}
        <div className="w-[40%] flex flex-col bg-surface-container-lowest">
          <div className="p-4 border-b border-outline-variant flex items-center justify-between sticky top-0 bg-surface-container-lowest z-10">
            <h3 className="font-headline-sm text-headline-sm text-on-surface font-bold">
              Similar Frames
            </h3>
          </div>
            <div className="p-4 overflow-y-auto h-full bg-surface-container-low">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
              {similarLoading
                ? Array.from({ length: 9 }).map((_, i) => (
                    <div
                      key={i}
                      className="aspect-video bg-surface rounded overflow-hidden border border-outline-variant relative"
                    >
                      <div className="w-full h-full bg-surface-container animate-pulse" />
                    </div>
                  ))
                : similarFrames.map((sf) => (
                    <div
                      key={`${sf.video_id}-${sf.frame_index}`}
                      onClick={onClose}
                      className="aspect-video bg-surface rounded overflow-hidden border border-outline-variant cursor-pointer hover:border-primary hover:shadow-md transition-all relative group"
                      title={`Frame ${sf.frame_index} score ${(sf.score * 100).toFixed(0)}%`}
                    >
                      <img
                        className="w-full h-full object-cover"
                        src={sf.thumbnail_url}
                        alt={`Frame ${sf.frame_index}`}
                      />
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-1.5">
                        <span className="text-mono-sm font-mono-sm text-white/90">
                          #{sf.frame_index}
                        </span>
                      </div>
                    </div>
                  ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
