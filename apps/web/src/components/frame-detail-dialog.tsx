"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "./icon";
import type { Frame } from "./results-panel";

interface FrameDetailDialogProps {
  frame: Frame;
  onClose: () => void;
  onSubmit: (frame: Frame) => void;
}

export function FrameDetailDialog({ frame, onClose, onSubmit }: FrameDetailDialogProps) {
  const [videoLoaded, setVideoLoaded] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
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
            <video
              ref={videoRef}
              className="w-full h-full object-contain"
              src={frame.frameLink}
              controls
              onLoadedData={() => setVideoLoaded(true)}
            />
            {/* Metadata Overlay */}
            <div className="absolute top-4 right-4 bg-black/60 backdrop-blur-md rounded px-3 py-2 font-mono-sm text-mono-sm text-gray-200 border border-white/10 flex flex-col gap-1">
              <div className="flex justify-between gap-4">
                <span>Frame</span>
                <span className="text-white font-medium">{frame.frameNum}</span>
              </div>
              <div className="flex justify-between gap-4">
                <span>Video</span>
                <span className="text-white font-medium">{frame.video_path}</span>
              </div>
              {frame.timestamp && (
                <div className="flex justify-between gap-4">
                  <span>Time</span>
                  <span className="text-white font-medium">{frame.timestamp.toFixed(0)}ms</span>
                </div>
              )}
            </div>
          </div>

          {/* Submission Controls */}
          <div className="flex-grow p-6 flex flex-col gap-4 overflow-y-auto">
            <h2 className="font-headline-sm text-headline-sm text-white">
              Frame {frame.frameNum} from {frame.video_path}
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
                defaultValue={frame.video_path}
              />
              <input
                className="bg-[#222222] border border-[#333333] rounded px-3 py-2 font-mono-sm text-mono-sm text-white focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all"
                type="text"
                placeholder="Time (ms)"
                defaultValue={frame.timestamp?.toFixed(0) || ""}
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
              {/* Placeholder similar frames */}
              {Array.from({ length: 9 }).map((_, i) => (
                <div
                  key={i}
                  className="aspect-video bg-surface rounded overflow-hidden border border-outline-variant cursor-pointer hover:border-primary hover:shadow-md transition-all relative"
                >
                  <div className="w-full h-full bg-surface-container animate-pulse" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
