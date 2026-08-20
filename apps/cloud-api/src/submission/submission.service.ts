import {
  ConflictException,
  Injectable,
  NotFoundException,
} from "@nestjs/common";
import { Response } from "express";
import archiver from "archiver";
import { v4 as uuid } from "uuid";
import { PrismaService } from "../database/prisma.service";
import type {
  CreateSubmissionInput,
  ReorderInput,
  SubmissionSnapshot,
  UpdateSubmissionInput,
} from "./submission.types";

const STATUS_PRIORITY: Record<string, number> = {
  confirmed: 0,
  review: 1,
  pending: 2,
};

function sortByStatusThenSort(a: SubmissionSnapshot, b: SubmissionSnapshot) {
  const sa = STATUS_PRIORITY[a.status] ?? 9;
  const sb = STATUS_PRIORITY[b.status] ?? 9;
  if (sa !== sb) return sa - sb;
  return a.sortOrder - b.sortOrder;
}

/** Makes a query name safe to embed in filenames: strips header control
 * characters (CRLF), path separators, and traversal sequences. */
export function sanitizeFileToken(value: string): string {
  return (
    value
      .replace(/[\r\n\t"]+/g, " ")
      .replace(/[/\\]+/g, "-")
      .replace(/\.{2,}/g, ".")
      .replace(/[^\w\-.() ]+/g, "_")
      .trim() || "unnamed"
  );
}

@Injectable()
export class SubmissionService {
  constructor(private readonly prisma: PrismaService) {}

  async listSubmissions(): Promise<SubmissionSnapshot[]> {
    const rows = await this.prisma.submission.findMany();
    return rows.map(this.toSnapshot).sort(sortByStatusThenSort);
  }

  async getSubmission(id: string): Promise<SubmissionSnapshot> {
    const row = await this.prisma.submission.findUnique({ where: { id } });
    if (!row) throw new NotFoundException("Submission not found");
    return this.toSnapshot(row);
  }

  async createSubmission(
    input: CreateSubmissionInput,
  ): Promise<SubmissionSnapshot> {
    const now = new Date().toISOString();
    const maxSort = await this.prisma.submission.aggregate({
      where: { status: "pending" },
      _max: { sortOrder: true },
    });
    const row = await this.prisma.submission.create({
      data: {
        id: uuid(),
        queryName: input.queryName,
        queryType: input.queryType,
        videoId: input.videoId,
        frameIds: JSON.stringify(input.frameIds),
        answer: input.answer ?? "",
        status: "pending",
        sortOrder: (maxSort._max.sortOrder ?? -1) + 1,
        version: 0,
        submittedBy: input.submittedBy ?? "",
        reviewedBy: "",
        reviewNotes: "",
        createdAt: now,
        updatedAt: now,
      },
    });
    return this.toSnapshot(row);
  }

  async updateSubmission(
    id: string,
    input: UpdateSubmissionInput,
  ): Promise<SubmissionSnapshot> {
    const existing = await this.prisma.submission.findUnique({ where: { id } });
    if (!existing) throw new NotFoundException("Submission not found");
    const row = await this.prisma.submission.update({
      where: { id },
      data: {
        ...(input.status !== undefined ? { status: input.status } : {}),
        ...(input.reviewedBy !== undefined
          ? { reviewedBy: input.reviewedBy }
          : {}),
        ...(input.reviewNotes !== undefined
          ? { reviewNotes: input.reviewNotes }
          : {}),
        updatedAt: new Date().toISOString(),
      },
    });
    return this.toSnapshot(row);
  }

  async deleteSubmission(id: string): Promise<void> {
    const existing = await this.prisma.submission.findUnique({ where: { id } });
    if (!existing) throw new NotFoundException("Submission not found");
    await this.prisma.submission.delete({ where: { id } });
  }

  async reorderInGroup(input: ReorderInput): Promise<SubmissionSnapshot[]> {
    const ids = input.items.map((i) => i.id);
    const rows = await this.prisma.submission.findMany({
      where: { id: { in: ids } },
    });

    const versionMap = new Map(rows.map((r) => [r.id, r.version]));
    for (const item of input.items) {
      if (versionMap.get(item.id) !== item.expectedVersion) {
        throw new ConflictException(
          `Version mismatch on ${item.id}: expected ${item.expectedVersion}, got ${versionMap.get(item.id)}`,
        );
      }
    }

    await this.prisma.$transaction(
      input.items.map((item, idx) =>
        this.prisma.submission.update({
          where: { id: item.id },
          data: {
            sortOrder: idx,
            version: { increment: 1 },
            updatedAt: new Date().toISOString(),
          },
        }),
      ),
    );

    const all = await this.prisma.submission.findMany();
    return all.map(this.toSnapshot).sort(sortByStatusThenSort);
  }

  async exportCsv(queryName?: string): Promise<string> {
    const where = queryName ? { queryName } : {};
    const rows = await this.prisma.submission.findMany({ where });
    const snapshots = rows.map(this.toSnapshot).sort(sortByStatusThenSort);
    return this.formatCsv(snapshots);
  }

  async exportZip(res: Response): Promise<void> {
    const rows = await this.prisma.submission.findMany();
    const snapshots = rows.map(this.toSnapshot).sort(sortByStatusThenSort);

    const byQuery = new Map<string, SubmissionSnapshot[]>();
    for (const s of snapshots) {
      const list = byQuery.get(s.queryName) ?? [];
      list.push(s);
      byQuery.set(s.queryName, list);
    }

    const archive = archiver("zip");
    archive.on("error", () => res.destroy());
    archive.pipe(res);
    for (const [queryName, queryRows] of byQuery) {
      archive.append(this.formatCsv(queryRows), {
        name: `submission/${sanitizeFileToken(queryName)}.csv`,
      });
    }
    await archive.finalize();
  }

  private formatCsv(rows: SubmissionSnapshot[]): string {
    const lines = rows.map((row) => {
      const frameIds = row.frameIds;
      if (row.queryType === "trake") {
        return `${row.videoId},${frameIds.join(",")}`;
      }
      if (row.queryType === "qa") {
        const answer =
          row.answer.includes(",") || row.answer.includes('"')
            ? `"${row.answer.replace(/"/g, '""')}"`
            : row.answer;
        return `${row.videoId},${frameIds[0] ?? ""},${answer}`;
      }
      return `${row.videoId},${frameIds[0] ?? ""}`;
    });
    return lines.join("\n");
  }

  private toSnapshot = (row: {
    id: string;
    queryName: string;
    queryType: string;
    videoId: string;
    frameIds: string;
    answer: string;
    status: string;
    sortOrder: number;
    version: number;
    submittedBy: string;
    reviewedBy: string;
    reviewNotes: string;
    createdAt: string;
    updatedAt: string;
  }): SubmissionSnapshot => ({
    id: row.id,
    queryName: row.queryName,
    queryType: row.queryType as SubmissionSnapshot["queryType"],
    videoId: row.videoId,
    frameIds: JSON.parse(row.frameIds) as number[],
    answer: row.answer,
    status: row.status as SubmissionSnapshot["status"],
    sortOrder: row.sortOrder,
    version: row.version,
    submittedBy: row.submittedBy,
    reviewedBy: row.reviewedBy,
    reviewNotes: row.reviewNotes,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  });
}
