import {
  ArrayNotEmpty,
  IsArray,
  IsIn,
  IsInt,
  IsNotEmpty,
  IsOptional,
  IsString,
  MaxLength,
} from "class-validator";

export type QueryType = "kis" | "qa" | "trake";
export type SubmissionStatus = "pending" | "confirmed" | "review";

export interface SubmissionSnapshot {
  id: string;
  queryName: string;
  queryType: QueryType;
  videoId: string;
  frameIds: number[];
  answer: string;
  status: SubmissionStatus;
  sortOrder: number;
  version: number;
  submittedBy: string;
  reviewedBy: string;
  reviewNotes: string;
  createdAt: string;
  updatedAt: string;
}

export class CreateSubmissionInput {
  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  queryName!: string;

  @IsIn(["kis", "qa", "trake"])
  queryType!: QueryType;

  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  videoId!: string;

  @IsArray()
  @ArrayNotEmpty()
  @IsInt({ each: true })
  frameIds!: number[];

  @IsOptional()
  @IsString()
  @MaxLength(4000)
  answer?: string;

  @IsOptional()
  @IsString()
  @MaxLength(100)
  submittedBy?: string;

  @IsOptional()
  @IsIn(["pending", "confirmed", "review"])
  status?: SubmissionStatus;
}

export class UpdateSubmissionInput {
  @IsOptional()
  @IsIn(["pending", "confirmed", "review"])
  status?: SubmissionStatus;

  @IsOptional()
  @IsString()
  @MaxLength(100)
  reviewedBy?: string;

  @IsOptional()
  @IsString()
  @MaxLength(4000)
  reviewNotes?: string;
}

export interface ReorderItem {
  id: string;
  expectedVersion: number;
}

export interface ReorderInput {
  statusGroup: SubmissionStatus;
  items: ReorderItem[];
}
