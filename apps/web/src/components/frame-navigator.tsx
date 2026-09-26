"use client";

import { useMemo } from "react";
import { Icon } from "./icon";
import type { FrameResult } from "@/lib/api";
import { KEYFRAME_PAGE_SIZE, offsetInPage, pageBounds } from "@/lib/frame-pages";

interface FrameNavigatorProps {
  frames: FrameResult[];
  currentArrayIndex: number;
  /** Index into `frames` where the visible page starts. */
  pageStartIndex: number;
  canGoPrevious: boolean;
  canGoNext: boolean;
  onPreviousPage: () => void;
  onNextPage: () => void;
  onFrameSelect: (frame: FrameResult) => void;
  onFullscreen: (frame: FrameResult) => void;
}

const NAV_BUTTON_CLASS =
  "rounded px-1.5 py-0.5 text-lg leading-none text-white/80 hover:bg-white/20 " +
  "hover:text-white disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent";

export function FrameNavigator({
  frames,
  currentArrayIndex,
  pageStartIndex,
  canGoPrevious,
  canGoNext,
  onPreviousPage,
  onNextPage,
  onFrameSelect,
  onFullscreen,
}: FrameNavigatorProps) {
  const { visibleFrames, currentOffset } = useMemo(() => {
    const { start, end } = pageBounds(pageStartIndex, frames.length, KEYFRAME_PAGE_SIZE);
    return {
      visibleFrames: frames.slice(start, end),
      // -1 while the selected frame's thumbnail is on another page: the page
      // simply shows no highlight until the user pages back or plays on.
      currentOffset: offsetInPage(pageStartIndex, currentArrayIndex, KEYFRAME_PAGE_SIZE),
    };
  }, [frames, currentArrayIndex, pageStartIndex]);

  if (frames.length === 0) return null;

  return (
    <div className="flex items-center justify-center gap-2 bg-neutral-900 py-3 px-4">
      <button
        type="button"
        onClick={onPreviousPage}
        disabled={!canGoPrevious}
        aria-label="Previous 5 keyframes"
        title="Previous 5 keyframes (←)"
        className={NAV_BUTTON_CLASS}
      >
        <Icon name="chevron_left" size={20} />
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
        type="button"
        onClick={onNextPage}
        disabled={!canGoNext}
        aria-label="Next 5 keyframes"
        title="Next 5 keyframes (→)"
        className={NAV_BUTTON_CLASS}
      >
        <Icon name="chevron_right" size={20} />
      </button>
    </div>
  );
}
