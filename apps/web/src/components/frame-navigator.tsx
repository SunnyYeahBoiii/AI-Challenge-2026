"use client";

import { useMemo } from "react";
import { Icon } from "./icon";
import type { FrameResult } from "@/lib/api";

interface FrameNavigatorProps {
  frames: FrameResult[];
  currentFrameIndex: number;
  onFrameSelect: (frame: FrameResult) => void;
}

export function FrameNavigator({ frames, currentFrameIndex, onFrameSelect }: FrameNavigatorProps) {
  const { visibleFrames, currentOffset } = useMemo(() => {
    if (frames.length <= 5) {
      return { visibleFrames: frames, currentOffset: currentFrameIndex };
    }
    let start = Math.max(0, currentFrameIndex - 2);
    if (start + 5 > frames.length) {
      start = frames.length - 5;
    }
    return {
      visibleFrames: frames.slice(start, start + 5),
      currentOffset: currentFrameIndex - start,
    };
  }, [frames, currentFrameIndex]);

  if (frames.length === 0) return null;

  return (
    <div className="flex items-center justify-center gap-2 bg-[#111111] py-3 px-4">
      <button
        onClick={() => onFrameSelect(frames[currentFrameIndex - 1])}
        disabled={currentFrameIndex <= 0}
        className="bg-[#222222] hover:bg-[#333333] rounded-full p-2 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        aria-label="Previous frame"
      >
        <Icon name="chevron_left" size={24} className="text-white" />
      </button>

      <div className="overflow-hidden">
        <div
          className="flex items-center gap-2 transition-transform duration-300 ease-in-out"
          style={{ transform: `translateX(${-currentOffset * 168}px)` }}
        >
          {visibleFrames.map((frame, i) => {
            const isCurrent = i === currentOffset;
            return (
              <div
                key={frame.id}
                onClick={() => onFrameSelect(frame)}
                className={`
                  relative aspect-video w-40 flex-shrink-0 rounded-lg overflow-hidden cursor-pointer
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
                  <span className="text-mono-sm font-mono-sm text-white/90">
                    {frame.frame_index}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <button
        onClick={() => onFrameSelect(frames[currentFrameIndex + 1])}
        disabled={currentFrameIndex >= frames.length - 1}
        className="bg-[#222222] hover:bg-[#333333] rounded-full p-2 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        aria-label="Next frame"
      >
        <Icon name="chevron_right" size={24} className="text-white" />
      </button>
    </div>
  );
}
