import type { FrameContext, FrameContextWindow, FrameResult } from "@/lib/api";

export const CLUSTER_MAX_GAP_SECONDS = 6;
export const CONTEXT_FRAME_COUNT = 10;

export interface RenderedFrame {
  frame: FrameResult;
  kind: "official" | "context";
}

function frameIndex(frame: FrameResult): number {
  return Number.isFinite(frame.frame_index) ? frame.frame_index : frame.frame_idx;
}

function canonicalTime(frame: FrameResult): number {
  if (Number.isFinite(frame.timestamp)) return frame.timestamp;
  if (Number.isFinite(frame.fps) && frame.fps > 0) return frameIndex(frame) / frame.fps;
  return frameIndex(frame);
}

function frameKey(frame: FrameResult): string {
  return `${frame.video_id}:${frameIndex(frame)}`;
}

function chronological(left: FrameResult, right: FrameResult): number {
  return frameIndex(left) - frameIndex(right) || canonicalTime(left) - canonicalTime(right);
}

/**
 * Make transitive <=6-second clusters from a single video's official frames.
 * Only official frames contribute to the request intervals.
 */
export function buildContextWindows(frames: FrameResult[]): FrameContextWindow[] {
  const officialFrames = Array.from(
    new Map(frames.map((frame) => [frameKey(frame), frame])).values(),
  ).sort(chronological);
  if (officialFrames.length === 0) return [];

  const clusters: FrameResult[][] = [[officialFrames[0]]];
  for (const frame of officialFrames.slice(1)) {
    const cluster = clusters[clusters.length - 1];
    const previous = cluster[cluster.length - 1];
    if (canonicalTime(frame) - canonicalTime(previous) <= CLUSTER_MAX_GAP_SECONDS) {
      cluster.push(frame);
    } else {
      clusters.push([frame]);
    }
  }

  return clusters.map((cluster) => ({
    video_id: cluster[0].video_id,
    start_frame_index: frameIndex(cluster[0]),
    end_frame_index: frameIndex(cluster[cluster.length - 1]),
  }));
}

/** Stable cache key that cannot mix context from different Milvus collections. */
export function contextCacheKey(collectionName: string, window: FrameContextWindow): string {
  return [
    collectionName,
    window.video_id,
    window.start_frame_index,
    window.end_frame_index,
    CONTEXT_FRAME_COUNT,
  ].join(":");
}

/**
 * Merge fetched neighbours into a video's display while preserving official
 * search results as the authoritative representation of every shared frame.
 */
export function mergeContextFrames(
  officialFrames: FrameResult[],
  contexts: FrameContext[],
): RenderedFrame[] {
  const frames = new Map<string, RenderedFrame>();
  for (const frame of officialFrames) {
    frames.set(frameKey(frame), { frame, kind: "official" });
  }
  for (const context of contexts) {
    for (const frame of [...context.before, ...context.after]) {
      const key = frameKey(frame);
      if (!frames.has(key)) frames.set(key, { frame, kind: "context" });
    }
  }
  return [...frames.values()].sort((left, right) => chronological(left.frame, right.frame));
}
