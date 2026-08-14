import type { TrakeBoardSnapshot } from "./trake-types";
import { computeFrameId } from "./frame-id";

export function cloudApiHttpBase(): string {
  return (
    process.env.NEXT_PUBLIC_CLOUD_API_URL || "http://localhost:5002"
  ).replace(/\/$/, "");
}

export async function createTrakeBoard(
  title = "TRAKE Board",
): Promise<TrakeBoardSnapshot> {
  const res = await fetch(`${cloudApiHttpBase()}/boards`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`Create board failed: ${res.status}`);
  return res.json();
}

export async function fetchTrakeBoard(
  boardId: string,
): Promise<TrakeBoardSnapshot> {
  const res = await fetch(`${cloudApiHttpBase()}/boards/${boardId}`);
  if (!res.ok) throw new Error(`Fetch board failed: ${res.status}`);
  return res.json();
}

/** Frame id used for DRES TRAKE wire format from Selection pts_time. */
export function selectionFrameId(ptsTime: number, fps: number): number {
  return computeFrameId(ptsTime, fps);
}

export function buildTrakeSubmitText(
  videoId: string,
  frameIds: number[],
): string {
  return `TR-${videoId}-${frameIds.join(",")}`;
}
