/** One keyframe pinned to the shared wall. */
export interface PinSnapshot {
  id: string;
  videoId: string;
  frameIndex: number;
  timestamp: number;
  fps: number;
  thumbnailUrl: string;
  createdAt: string;
}

/** What a client sends to pin a frame. Frame-only by decision: no note, no
 * status, no pinner identity — the wall is a shared shortlist, not a tracker. */
export interface AddPinInput {
  videoId: string;
  frameIndex: number;
  timestamp: number;
  fps: number;
  thumbnailUrl?: string;
}

export interface RemovePinInput {
  videoId: string;
  frameIndex: number;
}
