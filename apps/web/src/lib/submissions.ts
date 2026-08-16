import { cloudApiHttpBase } from "./cloud-api";

export type QueryType = "kis" | "qa" | "trake";
export type SubmissionStatus = "pending" | "confirmed" | "review";

export interface Submission {
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

export async function listSubmissions(): Promise<Submission[]> {
  const res = await fetch(`${cloudApiHttpBase()}/submissions`);
  if (!res.ok) throw new Error(`List submissions failed: ${res.status}`);
  const data = await res.json();
  return data.submissions;
}

export async function createSubmission(input: {
  queryName: string;
  queryType: QueryType;
  videoId: string;
  frameIds: number[];
  answer?: string;
  submittedBy?: string;
}): Promise<Submission> {
  const res = await fetch(`${cloudApiHttpBase()}/submissions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(`Create submission failed: ${res.status}`);
  return res.json();
}

export async function updateSubmission(
  id: string,
  input: {
    status?: SubmissionStatus;
    reviewedBy?: string;
    reviewNotes?: string;
  },
): Promise<Submission> {
  const res = await fetch(`${cloudApiHttpBase()}/submissions/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(`Update submission failed: ${res.status}`);
  return res.json();
}

export async function deleteSubmission(id: string): Promise<void> {
  const res = await fetch(`${cloudApiHttpBase()}/submissions/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Delete submission failed: ${res.status}`);
}

export function getExportUrl(queryName?: string): string {
  const params = queryName ? `?query=${encodeURIComponent(queryName)}` : "";
  return `${cloudApiHttpBase()}/submissions/export${params}`;
}

export function getExportAllUrl(): string {
  return `${cloudApiHttpBase()}/submissions/export-all`;
}

export async function downloadExport(url: string, filename: string): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

export interface Query {
  id: string;
  name: string;
  content: string;
  queryType: QueryType;
  createdAt: string;
  updatedAt: string;
}

export async function listQueries(): Promise<Query[]> {
  const res = await fetch(`${cloudApiHttpBase()}/queries`);
  if (!res.ok) throw new Error(`List queries failed: ${res.status}`);
  const data = await res.json();
  return data.queries;
}

export async function createQuery(input: {
  name: string;
  content?: string;
  queryType?: QueryType;
}): Promise<Query> {
  const res = await fetch(`${cloudApiHttpBase()}/queries`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(`Create query failed: ${res.status}`);
  return res.json();
}

export async function deleteQuery(id: string): Promise<void> {
  const res = await fetch(`${cloudApiHttpBase()}/queries/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Delete query failed: ${res.status}`);
}
