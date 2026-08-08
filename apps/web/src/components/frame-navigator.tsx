"use client";

import { useMemo } from "react";
import { Icon } from "./icon";
import type { FrameResult } from "@/lib/api";

interface FrameNavigatorProps {
  frames: FrameResult[];
  currentArrayIndex: number;
  onFrameSelect: (frame: FrameResult) => void;
  onFullscreen: (frame: FrameResult) => void;
}

export function FrameNavigator({ frames, currentArrayIndex, onFrameSelect, onFullscreen }: FrameNavigatorProps) {
  const { visibleFrames, currentOffset } = useMemo(() => {
    const windowSize = Math.min(3, frames.length);
    let start = currentArrayIndex - Math.floor(windowSize / 2);
    if (start < 0) start = 0;
    if (start + windowSize > frames.length) start = frames.length - windowSize;
    return {
      visibleFrames: frames.slice(start, start + windowSize),
      currentOffset: currentArrayIndex - start,
    };
  }, [frames, currentArrayIndex]);

  if (frames.length === 0) return null;

  return (
    <div className="flex items-center justify-center gap-2 bg-neutral-900 py-3 px-4">
      <button
        onClick={() => onFrameSelect(frames[currentArrayIndex - 1])}
        disabled={currentArrayIndex <= 0}
        className="bg-neutral-800 hover:bg-neutral-700 rounded-full p-2 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        aria-label="Previous frame"
      >
        <Icon name="chevron_left" size={24} className="text-white" />
      </button>

      <div className="flex items-center gap-2">
        {visibleFrames.map((frame, i) => {
          const isCurrent = i === currentOffset;
          return (
            <div
              key={frame.id}
              onClick={() => (isCurrent ? onFullscreen(frame) : onFrameSelect(frame))}
              title={isCurrent ? "View frame fullscreen" : undefined}
              className={`
                group relative aspect-video w-40 flex-shrink-0 rounded-lg overflow-hidden cursor-pointer
                transition-all duration-300
                ${isCurrent ? "ring-2 ring-primary-container" : "ring-1 ring-outline-variant hover:ring-white/30"}
              `}
            >
              <img
                className="w-full h-full object-cover"
                src={frame.thumbnail_url}
                alt={`Frame ${frame.frame_index}`}
              />
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-1.5">
                <span className="font-mono text-mono-sm text-white/90">
                  {frame.frame_index}
                </span>
              </div>
              {isCurrent && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/40 transition-colors">
                  <Icon
                    name="fullscreen"
                    size={20}
                    className="text-white opacity-0 group-hover:opacity-100 transition-opacity"
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <button
        onClick={() => onFrameSelect(frames[currentArrayIndex + 1])}
        disabled={currentArrayIndex >= frames.length - 1}
        className="bg-neutral-800 hover:bg-neutral-700 rounded-full p-2 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        aria-label="Next frame"
      >
        <Icon name="chevron_right" size={24} className="text-white" />
      </button>
    </div>
  );
}
