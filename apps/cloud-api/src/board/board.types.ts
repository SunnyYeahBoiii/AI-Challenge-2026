import { IsArray, IsOptional, IsString, MaxLength } from "class-validator";

/** Identifies one moment in a video — the fields every TrakeBoard candidate
 * and selection carries (and the Prisma models store). */
export interface MomentRef {
  videoId: string;
  ptsTime: number;
  previewFrameId: string;
  fps: number;
}

export interface BoardEventSnapshot {
  id: string;
  position: number;
  labelText: string;
  displayLabel: string;
  candidates: CandidateSnapshot[];
  selection: SelectionSnapshot | null;
}

export interface CandidateSnapshot extends MomentRef {
  id: string;
  frameIdx: number;
  thumbnailUrl: string;
  addedBy: string;
  createdAt: string;
}

export interface SelectionSnapshot extends MomentRef {
  eventId: string;
  candidateId: string | null;
  updatedBy: string;
  updatedAt: string;
}

export interface BoardSnapshot {
  id: string;
  title: string;
  targetVideoId: string | null;
  createdAt: string;
  updatedAt: string;
  events: BoardEventSnapshot[];
  members: string[];
}

export interface AddCandidateInput extends MomentRef {
  eventId: string;
  frameIdx: number;
  thumbnailUrl?: string;
  addedBy?: string;
}

export interface SetSelectionInput extends MomentRef {
  eventId: string;
  candidateId?: string | null;
  updatedBy?: string;
}

export class AddBoardEventInput {
  @IsOptional()
  @IsString()
  @MaxLength(200)
  labelText?: string;
}

export class ReorderBoardEventsInput {
  @IsArray()
  @IsString({ each: true })
  orderedEventIds!: string[];
}
