import axios from "axios";

import { prepareSearchText } from "@/lib/local-translation";

const api = axios.create({ baseURL: "/api" });

// ====== Backend-matching types ======

export interface FrameResult {
  id: string;
  video_id: string;
  frame_index: number;
  frame_idx: number;
  shot_idx: number;
  start_time: number;
  end_time: number;
  timestamp: number;
  fps: number;
  score: number;
  title: string;
  description: string;
  keywords: string[];
  author?: string;
  publish_date?: string;
  thumbnail_url: string;
  watch_url: string;
  video_url: string;
  sequence_idx?: number;
  sequence_id?: string;
  matches?: QueryMatch[];
  query_index?: number;
  similarity?: number;
  ocr_text?: string;
  asr_text?: string;
  retrieval_rank?: number;
  filter_only?: boolean;
}

export interface QueryMatch {
  query_index: number;
  similarity: number;
}

export interface TemporalSequence {
  sequence_id: string;
  sequence_score: number;
  total_span_seconds: number;
  frames: FrameResult[];
}

export interface TemporalVideoResult {
  video_id: string;
  video_score: number;
  has_vector_score?: boolean;
  valid_frames: FrameResult[];
  best_sequence: TemporalSequence;
}

export interface TemporalSearchResponse {
  mode: "parallel" | "sequential";
  videos: TemporalVideoResult[];
  total_videos: number;
  total_valid_frames: number;
}

export interface VideoResult {
  video_id: string;
  title: string;
  description: string;
  keywords: string[];
  author: string;
  channel_id: string;
  length: number;
  publish_date: string;
  thumbnail_url: string;
  watch_url: string;
  level: string;
  frame_count: number;
}

export interface HealthStatus {
  status: string;
  milvus: string;
  elasticsearch: string;
}

// ====== Request types ======

export interface MultiBoxQuery {
  text?: string;
  image?: string;
  tags?: string[];
  tag_match_mode?: "and" | "or";
  ocr_keywords?: string[];
  asr_keywords?: string[];
  ocr_match_mode?: "and" | "or";
  asr_match_mode?: "and" | "or";
  keywords?: string[];
  key_match_mode?: "and" | "or";
  keyword_source?: "all" | "ocr" | "asr";
  enhance?: boolean | null;
  topk?: number;
}

export interface MultiBoxRequest {
  box_queries: MultiBoxQuery[];
  temporal_window_seconds?: number;
  enhance?: boolean;
  mode?: "parallel" | "sequential";
}

// ====== Search API ======

export async function searchVideoFrames(
  videoId: string,
  frameIndex?: number,
  range?: number
): Promise<{ video_id: string; results: FrameResult[]; total: number }> {
  const body: Record<string, unknown> = { video_id: videoId };
  if (frameIndex !== undefined) body.frame_index = frameIndex;
  if (range !== undefined) body.range = range;
  const { data } = await api.post("/search/video", body);
  return data;
}

export async function searchText(
  text: string,
  topk: number,
): Promise<{ results: FrameResult[]; total: number }> {
  const prepared = await prepareSearchText(text, true);
  const { data } = await api.post("/search", {
    text: prepared.text,
    topk,
    enhance: prepared.enhance,
  });
  return data;
}

export async function multiBoxSearch(
  req: MultiBoxRequest
): Promise<TemporalSearchResponse> {
  const boxQueries = await Promise.all(
    req.box_queries.map(async (box) => {
      const shouldEnhance = box.enhance ?? req.enhance ?? true;
      if (!box.text || !shouldEnhance) return box;

      const prepared = await prepareSearchText(box.text, true);
      return {
        ...box,
        text: prepared.text,
        enhance: prepared.enhance,
      };
    }),
  );
  const { data } = await api.post("/frames", { ...req, box_queries: boxQueries });
  return data;
}

// ====== Videos API ======

export async function listVideos(
  params?: { q?: string; size?: number }
): Promise<{ videos: VideoResult[]; total: number }> {
  const { data } = await api.get("/videos", { params });
  return data;
}

export interface KeyframeInfo {
  frame_index: number;
  timestamp: number;
  fps: number | null;
  thumbnail_url: string;
  video_url: string;
  is_exact: boolean;
}

export async function getNearestKeyframe(
  videoId: string,
  frameIndex: number,
  range: number = 100
): Promise<KeyframeInfo | null> {
  try {
    const { data } = await api.post("/submissions/keyframe", {
      video_id: videoId,
      frame_index: frameIndex,
      range,
    });
    return data;
  } catch {
    return null;
  }
}

export async function getNearestKeyframes(
  items: Array<{ video_id: string; frame_index: number; key?: string; range?: number }>
): Promise<Record<string, KeyframeInfo | null>> {
  try {
    const { data } = await api.post("/submissions/keyframes", { items });
    return data.keyframes;
  } catch {
    return {};
  }
}

// ====== DRES API ======

export interface DresSubmitResult {
  submission?: string;
  status?: boolean;
  [key: string]: unknown;
}

/** Shared DRES verdict classification (order matters: a WRONG verdict wins,
 * then the duplicate flag, then CORRECT). */
export function classifyDresSubmit(data: DresSubmitResult): "correct" | "wrong" | "duplicate" | "error" {
  if (data.submission === "WRONG") return "wrong";
  if (data.status === false) return "duplicate";
  if (data.submission === "CORRECT") return "correct";
  return "error";
}

export async function submitFrameToDres(params: {
  frameId: string;
  videoId: string;
  timestamp: number;
  submissionType: "track" | "trake" | "qa" | "kis";
  sessionId: string;
  /** Required for QA — full answer text (sent as one DRES text answer). */
  answer?: string;
  /** Target evaluation (contest) run. Falls back to first ACTIVE run if omitted. */
  evaluationId?: string;
}): Promise<DresSubmitResult> {
  const { data } = await api.post(`/dres/submit/${params.submissionType}`, {
    frame_id: params.frameId,
    video_path: params.videoId,
    timestamp: params.timestamp,
    sessionId: params.sessionId,
    ...(params.evaluationId ? { evaluationId: params.evaluationId } : {}),
    ...(params.submissionType === "qa" && params.answer != null
      ? { answer: params.answer }
      : {}),
  });
  return data;
}

/** TRAKE: TR-<VIDEO_ID>-<FRAME_ID1>,<FRAME_ID2>,... via Flask. */
export async function submitTrakeToDres(params: {
  videoId: string;
  frameIds: number[];
  sessionId: string;
  /** Target evaluation (contest) run. Falls back to first ACTIVE run if omitted. */
  evaluationId?: string;
}): Promise<DresSubmitResult> {
  const { data } = await api.post(`/dres/submit/track`, {
    video_path: params.videoId,
    frame_ids: params.frameIds,
    sessionId: params.sessionId,
    ...(params.evaluationId ? { evaluationId: params.evaluationId } : {}),
  });
  return data;
}

// ====== Health API ======

export async function healthCheck(): Promise<HealthStatus> {
  const { data } = await api.get("/health");
  return data;
}

// ====== Admin / model API ======

export interface ModelStatus {
  state: "none" | "loading" | "ready" | "error";
  model_id: string | null;
  collection_name: string | null;
  embedding_dim: number | null;
  error: string | null;
}

export async function getModelStatus(): Promise<{ status: ModelStatus; available_models: string[] }> {
  const { data } = await api.get("/admin/model");
  return data;
}

/**
 * Pass `null` for `modelId` to unload the active model without loading another one.
 * `collectionName` overrides the model's default Milvus collection — leave empty to use the default.
 */
export async function setActiveModel(
  modelId: string | null,
  collectionName?: string
): Promise<{ status: ModelStatus }> {
  const { data } = await api.post("/admin/model", {
    model_id: modelId,
    collection_name: collectionName || undefined,
  });
  return data;
}
