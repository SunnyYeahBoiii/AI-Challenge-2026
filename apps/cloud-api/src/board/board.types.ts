import { IsArray, IsOptional, IsString, MaxLength } from "class-validator";

export interface BoardEventSnapshot {
  id: string;
  position: number;
  labelText: string;
  displayLabel: string;
  candidates: CandidateSnapshot[];
  selection: SelectionSnapshot | null;
}

export interface CandidateSnapshot {
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

export interface SelectionSnapshot {
  eventId: string;
  candidateId: string | null;
  videoId: string;
  ptsTime: number;
  previewFrameId: string;
  fps: number;
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

export interface AddCandidateInput {
  eventId: string;
  videoId: string;
  ptsTime: number;
  previewFrameId: string;
  fps: number;
  frameIdx: number;
  thumbnailUrl?: string;
  addedBy?: string;
}

export interface SetSelectionInput {
  eventId: string;
  videoId: string;
  ptsTime: number;
  previewFrameId: string;
  fps: number;
  candidateId?: string | null;
  updatedBy?: string;
}

export class CreateBoardInput {
  @IsOptional()
  @IsString()
  @MaxLength(200)
  title?: string;
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
