import type {
  FrameResult,
  TemporalSearchResponse,
  TemporalVideoResult,
} from "@/lib/api";

export function emptySearchResult(
  mode: "parallel" | "sequential" = "parallel",
): TemporalSearchResponse {
  return { mode, videos: [], total_videos: 0, total_valid_frames: 0 };
}

/** Reshape a flat frame list (video browse) into the temporal search shape. */
export function videoFramesResponse(
  frames: FrameResult[],
  mode: "parallel" | "sequential",
): TemporalSearchResponse {
  const grouped = new Map<string, FrameResult[]>();
  frames.forEach((frame) => {
    const current = grouped.get(frame.video_id) ?? [];
    const score = Number.isFinite(frame.score) ? frame.score : 0;
    current.push({
      ...frame,
      score,
      matches: [{ query_index: 0, similarity: score }],
    });
    grouped.set(frame.video_id, current);
  });
  const videos: TemporalVideoResult[] = Array.from(grouped.entries()).map(([videoId, results]) => {
    const validFrames = [...results].sort((left, right) => left.frame_idx - right.frame_idx);
    const best = [...validFrames].sort(
      (left, right) => right.score - left.score || left.frame_idx - right.frame_idx
    )[0];
    return {
      video_id: videoId,
      video_score: best?.score ?? 0,
      has_vector_score: false,
      valid_frames: validFrames,
      best_sequence: {
        sequence_id: `${videoId}:${best?.frame_index ?? 0}`,
        sequence_score: best?.score ?? 0,
        total_span_seconds: 0,
        frames: best ? [{ ...best, query_index: 0, similarity: best.score }] : [],
      },
    };
  });
  videos.sort((left, right) => right.video_score - left.video_score);
  return {
    mode,
    videos,
    total_videos: videos.length,
    total_valid_frames: videos.reduce((total, video) => total + video.valid_frames.length, 0),
  };
}
