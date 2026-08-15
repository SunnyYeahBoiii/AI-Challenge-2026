export type QueryType = "kis" | "qa" | "trake";

export interface QuerySnapshot {
  id: string;
  name: string;
  content: string;
  queryType: QueryType;
  createdAt: string;
  updatedAt: string;
}

export interface CreateQueryInput {
  name: string;
  content?: string;
  queryType?: QueryType;
}

export interface UpdateQueryInput {
  content?: string;
  queryType?: QueryType;
}
