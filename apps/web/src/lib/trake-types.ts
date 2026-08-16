export interface TrakeCandidate {
  id: string;
  videoId: string;
  ptsTime: number;
  previewFrameId: string;
  fps: number;
  frameIdx: number;
  thumbnailUrl: string;
  addedBy: string;
  createdAt: string;
}

export interface TrakeSelection {
  eventId: string;
  candidateId: string | null;
  videoId: string;
  ptsTime: number;
  previewFrameId: string;
  fps: number;
  updatedBy: string;
  updatedAt: string;
}

export interface TrakeEvent {
  id: string;
  position: number;
  labelText: string;
  displayLabel: string;
  candidates: TrakeCandidate[];
  selection: TrakeSelection | null;
}

export interface TrakeBoardSnapshot {
  id: string;
  title: string;
  targetVideoId: string | null;
  createdAt: string;
  updatedAt: string;
  events: TrakeEvent[];
  members: string[];
}

/** Flat frame fields needed to turn a search result into a Trake candidate. */
export interface FrameToTrake {
  video_id: string;
  timestamp: number;
  frame_idx: number;
  fps: number;
  thumbnail_url: string;
}

export interface TrakeCandidatePayload {
  eventId: string;
  videoId: string;
  ptsTime: number;
  previewFrameId: string;
  fps: number;
  frameIdx: number;
  thumbnailUrl?: string;
  addedBy?: string;
}

export const TRAKE_BOARD_ID_KEY = "trakeBoardId";
export const TRAKE_DISPLAY_NAME_KEY = "trakeDisplayName";
export const TRAKE_FRAME_MIME = "application/x-trake-frame";
