import { computeFrameId } from "./frame-id";

export function cloudApiHttpBase(): string {
  return (
    process.env.NEXT_PUBLIC_CLOUD_API_URL || "http://localhost:5002"
  ).replace(/\/$/, "");
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
