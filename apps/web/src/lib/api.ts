const API_BASE = "/api";

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
}

export interface MultiBoxRequest {
  box_queries: MultiBoxQuery[];
  temporal_window_seconds?: number;
  topk?: number;
  enhance?: boolean;
}

// ====== Search API ======

export async function searchText(req: SearchTextRequest): Promise<{ results: FrameResult[]; total: number }> {
  const res = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
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
  const res = await fetch(`${API_BASE}/search/image`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Image search failed: ${res.status}`);
  return res.json();
}

export async function searchVideoFrames(
  videoId: string
): Promise<{ video_id: string; results: FrameResult[]; total: number }> {
  const res = await fetch(`${API_BASE}/search/video`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId }),
  });
  if (!res.ok) throw new Error(`Video frames search failed: ${res.status}`);
  return res.json();
}

export async function multiBoxSearch(
  req: MultiBoxRequest
): Promise<{ results: FrameResult[]; total: number }> {
  const res = await fetch(`${API_BASE}/frames`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Multi-box search failed: ${res.status}`);
  return res.json();
}

// ====== Videos API ======

export async function listVideos(
  params?: { q?: string; tags?: string[]; size?: number }
): Promise<{ videos: VideoResult[]; total: number }> {
  const sp = new URLSearchParams();
  if (params?.q) sp.set("q", params.q);
  if (params?.tags?.length) sp.set("tags", params.tags.join(","));
  if (params?.size) sp.set("size", String(params.size));
  const res = await fetch(`${API_BASE}/videos?${sp.toString()}`);
  if (!res.ok) throw new Error(`List videos failed: ${res.status}`);
  return res.json();
}

export async function getVideo(videoId: string): Promise<VideoResult> {
  const res = await fetch(`${API_BASE}/videos/${encodeURIComponent(videoId)}`);
  if (!res.ok) throw new Error(`Get video failed: ${res.status}`);
  return res.json();
}

// ====== Embed API ======

export async function embedText(
  text: string,
  enhance?: boolean
): Promise<{ vector: number[]; dim: number; text: string; enhanced: boolean }> {
  const res = await fetch(`${API_BASE}/embed/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, enhance }),
  });
  if (!res.ok) throw new Error(`Embed text failed: ${res.status}`);
  return res.json();
}

export async function embedImage(
  file: File
): Promise<{ vector: number[]; dim: number; filename: string }> {
  const form = new FormData();
  form.append("image", file);
  const res = await fetch(`${API_BASE}/embed/image`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Embed image failed: ${res.status}`);
  return res.json();
}

// ====== Health API ======

export async function healthCheck(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json();
}
