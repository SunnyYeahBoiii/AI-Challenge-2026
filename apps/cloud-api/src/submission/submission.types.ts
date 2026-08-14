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
  submittedBy: string;
  reviewedBy: string;
  reviewNotes: string;
  createdAt: string;
  updatedAt: string;
}

export interface CreateSubmissionInput {
  queryName: string;
  queryType: QueryType;
  videoId: string;
  frameIds: number[];
  answer?: string;
  submittedBy?: string;
}

export interface UpdateSubmissionInput {
  status?: SubmissionStatus;
  reviewedBy?: string;
  reviewNotes?: string;
}
