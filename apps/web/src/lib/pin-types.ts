/** One keyframe on the shared pin wall, as cloud-api broadcasts it. */
export interface PinSnapshot {
  id: string;
  videoId: string;
  frameIndex: number;
  timestamp: number;
  fps: number;
  thumbnailUrl: string;
  createdAt: string;
}

/** Frame-only payload: the wall carries no note, status or pinner identity. */
export interface PinInput {
  videoId: string;
  frameIndex: number;
  timestamp: number;
  fps: number;
  thumbnailUrl?: string;
}

/** Same shape the server keys pins by, so the UI can match without an id. */
export function pinKey(videoId: string, frameIndex: number): string {
  return `${videoId}#${frameIndex}`;
}
