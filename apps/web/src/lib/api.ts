import axios from "axios";

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

export interface SearchTextRequest {
  text: string;
  tags?: string[];
  tag_mode?: "and" | "or";
  ocr_keywords?: string[];
  asr_keywords?: string[];
  ocr_match_mode?: "and" | "or";
  asr_match_mode?: "and" | "or";
  keywords?: string[];
  keyword_mode?: "and" | "or";
  keyword_source?: "all" | "ocr" | "asr";
  topk?: number;
  enhance?: boolean;
}

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

export async function searchText(req: SearchTextRequest): Promise<{ results: FrameResult[]; total: number }> {
  const { data } = await api.post("/search", req);
  return data;
}

export async function searchImage(
  file: File,
  params?: { tags?: string[]; keywords?: string[]; topk?: number }
): Promise<{ results: FrameResult[]; total: number }> {
  const form = new FormData();
  form.append("image", file);
  if (params?.tags?.length) params.tags.forEach((t) => form.append("tags", t));
  if (params?.keywords?.length) params.keywords.forEach((k) => form.append("keywords", k));
  if (params?.topk) form.append("topk", String(params.topk));
  const { data } = await api.post("/search/image", form);
  return data;
}

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

export async function searchSimilarFrames(
  videoId: string,
  frameIndex: number,
  topk?: number
): Promise<{ results: FrameResult[]; total: number }> {
  const { data } = await api.post("/search/similar", { video_id: videoId, frame_index: frameIndex, topk });
  return data;
}

export async function multiBoxSearch(
  req: MultiBoxRequest
): Promise<TemporalSearchResponse> {
  const { data } = await api.post("/frames", req);
  return data;
}

// ====== Videos API ======

export async function listVideos(
  params?: { q?: string; tags?: string[]; size?: number }
): Promise<{ videos: VideoResult[]; total: number }> {
  const { data } = await api.get("/videos", { params });
  return data;
}

export async function getVideo(videoId: string): Promise<VideoResult> {
  const { data } = await api.get(`/videos/${encodeURIComponent(videoId)}`);
  return data;
}

export interface KeyframeInfo {
  frame_index: number;
  timestamp: number;
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

// ====== Embed API ======

export async function embedText(
  text: string,
  enhance?: boolean
): Promise<{ vector: number[]; dim: number; text: string; enhanced: boolean }> {
  const { data } = await api.post("/embed/text", { text, enhance });
  return data;
}

export async function embedImage(
  file: File
): Promise<{ vector: number[]; dim: number; filename: string }> {
  const form = new FormData();
  form.append("image", file);
  const { data } = await api.post("/embed/image", form);
  return data;
}

// ====== DRES API ======

export interface DresSubmitResult {
  submission?: string;
  status?: boolean;
  [key: string]: unknown;
}

export async function submitFrameToDres(params: {
  frameId: string;
  videoId: string;
  timestamp: number;
  submissionType: "track" | "qa" | "kis";
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
