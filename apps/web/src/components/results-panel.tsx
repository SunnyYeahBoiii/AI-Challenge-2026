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
          <Icon name="image_search" size={48} className="text-outline-variant mb-3" />
          <h2 className="text-headline-sm font-bold text-on-surface mb-2">
            Start Searching
          </h2>
          <p className="text-body-md text-on-surface-variant">
            Use the filters on the left and press &quot;Search&quot; to see results.
          </p>
        </div>
      </div>
    );
  }

  return (
    <main className="flex-1 bg-surface-container-lowest overflow-y-auto p-container-padding">
      <div className="flex justify-between items-center mb-4">
        <span className="text-label-md text-on-surface-variant">
          {frames.length} {frames.length === 1 ? "result" : "results"}
          {viewMode === "grouped" && groupedFrames.length > 1 && (
            <> · {groupedFrames.length} videos</>
          )}
        </span>
      </div>
      <div className="flex flex-col gap-6">
        {groupedFrames.map((group, groupIndex) => (
          <div key={viewMode === "grouped" ? group[0].video_id : groupIndex} className="flex flex-col gap-2">
            {viewMode === "grouped" && (
              <div className="flex items-center gap-2 sticky top-0 bg-surface-container-lowest/95 backdrop-blur-sm py-1 z-10">
                <Icon name="movie" size={16} className="text-on-surface-variant" />
                <span className="text-label-md text-on-surface">{group[0].video_id}</span>
                <span className="text-label-sm text-on-surface-variant">
                  ({group.length})
                </span>
                <div className="h-px bg-outline-variant flex-1" />
              </div>
            )}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7 gap-2">
              {group.map((frame) => (
                <div
                  key={`${frame.video_id}-${frame.frame_index}`}
                  className="relative group cursor-pointer aspect-video bg-surface-container overflow-hidden border border-outline-variant rounded-sm hover:border-primary transition-colors"
                  onClick={() => {
                    onFrameSelect(frame);
                    onFrameDetail(frame);
                  }}
                >
                  <img
                    className="w-full h-full object-cover"
                    src={frame.thumbnail_url}
                    alt={`Frame ${frame.frame_index}`}
                    loading="lazy"
                  />
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent px-1.5 pt-4 pb-1 flex justify-between items-end opacity-0 group-hover:opacity-100 transition-opacity">
                    <span className="font-mono text-mono-sm text-white/90">
                      #{frame.frame_index}
                    </span>
                    {frame.score > 0 && (
                      <span className="text-label-xs text-white/80 bg-black/40 rounded px-1">
                        {(frame.score * 100).toFixed(0)}%
                      </span>
                    )}
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
