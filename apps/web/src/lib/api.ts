import axios from "axios";

const api = axios.create({ baseURL: "/api" });

// ====== Backend-matching types ======

export interface FrameResult {
  id: string;
  video_id: string;
  frame_index: number;
  shot_idx: number;
  start_time: number;
  end_time: number;
  pts_time: number;
  fps: number;
  score: number;
  title: string;
  description: string;
  keywords: string[];
  thumbnail_url: string;
  watch_url: string;
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
  keywords?: string[];
  key_match_mode?: "and" | "or";
  enhance?: boolean | null;
  topk?: number;
}

export interface MultiBoxRequest {
  box_queries: MultiBoxQuery[];
  temporal_window_seconds?: number;
  topk?: number;
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
): Promise<{ results: FrameResult[]; total: number }> {
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

// ====== Health API ======

export async function healthCheck(): Promise<HealthStatus> {
  const { data } = await api.get("/health");
  return data;
}
