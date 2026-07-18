const API_BASE = "/api";

export interface SearchRequest {
  text?: string;
  topk?: number;
}

export interface Frame {
  id: string;
  frameNum: number;
  timestamp: number | null;
  frameLink: string;
  videoLink: string;
  description: string | null;
  tags: string[];
  keywords_ocr: string[];
  keywords_asr: string[];
  score: number;
  video_path: string;
}

export interface SearchResponse {
  results: Frame[];
  total: number;
}

export async function searchFrames(req: SearchRequest): Promise<SearchResponse> {
  const res = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}

export async function healthCheck(): Promise<{
  status: string;
  milvus: string;
  elasticsearch: string;
}> {
  const res = await fetch(`${API_BASE}/health`);
  return res.json();
}
