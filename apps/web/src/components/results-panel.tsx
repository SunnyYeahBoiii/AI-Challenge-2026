"use client";

import { useMemo } from "react";
import { Icon } from "./icon";
import type { FrameResult } from "@/lib/api";

interface ResultsPanelProps {
  frames: FrameResult[];
  viewMode: "grouped" | "continuous";
  onFrameSelect: (frame: FrameResult) => void;
  onFrameDetail: (frame: FrameResult) => void;
  isLoading?: boolean;
}

export function ResultsPanel({
  frames,
  viewMode,
  onFrameSelect,
  onFrameDetail,
  isLoading,
}: ResultsPanelProps) {
  const groupedFrames = useMemo(() => {
    if (viewMode === "continuous") return [frames];
    const groups = new Map<string, FrameResult[]>();
    frames.forEach((frame) => {
      const key = frame.video_id;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(frame);
    });
    return Array.from(groups.values());
  }, [frames, viewMode]);

  if (isLoading) {
    return (
      <div className="p-container-padding">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7 gap-2">
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

  if (frames.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md">
          <h2 className="font-headline-sm text-headline-sm font-bold text-on-surface mb-2">
            Start Searching
          </h2>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Use the filters on the left and press &quot;Enter&quot; to see results.
          </p>
        </div>
      </div>
    );
  }

  return (
    <main className="flex-1 bg-surface-container-lowest overflow-y-auto p-container-padding">
      <div className="flex flex-col gap-6">
        {groupedFrames.map((group, groupIndex) => (
          <div key={groupIndex} className="flex flex-col gap-2">
            {viewMode === "grouped" && (
              <div className="h-px bg-outline-variant w-full my-1" />
            )}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7 gap-2">
              {group.map((frame) => (
                <div
                  key={frame.id}
                  className="relative group cursor-pointer aspect-video bg-surface-container overflow-hidden border border-outline-variant rounded-sm hover:border-primary transition-colors"
                  onClick={() => onFrameSelect(frame)}
                >
                  <img
                    className="w-full h-full object-cover"
                    src={frame.thumbnail_url}
                    alt={`Frame ${frame.frame_index}`}
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onFrameDetail(frame);
                      }}
                      className="text-white"
                    >
                      <Icon name="play_circle" size={32} className="text-white" filled />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
