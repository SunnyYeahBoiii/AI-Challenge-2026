import { Injectable, NotFoundException } from "@nestjs/common";
import { Response } from "express";
import archiver from "archiver";
import { v4 as uuid } from "uuid";
import { PrismaService } from "../database/prisma.service";
import type {
  CreateSubmissionInput,
  SubmissionSnapshot,
  UpdateSubmissionInput,
} from "./submission.types";

@Injectable()
export class SubmissionService {
  constructor(private readonly prisma: PrismaService) {}

  async listSubmissions(): Promise<SubmissionSnapshot[]> {
    const rows = await this.prisma.submission.findMany({
      orderBy: { createdAt: "desc" },
    });
    return rows.map(this.toSnapshot);
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
    const row = await this.prisma.submission.create({
      data: {
        id: uuid(),
        queryName: input.queryName,
        queryType: input.queryType,
        videoId: input.videoId,
        frameIds: JSON.stringify(input.frameIds),
        answer: input.answer ?? "",
        status: "pending",
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
    await this.prisma.submission.findUniqueOrThrow({ where: { id } });
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
    await this.prisma.submission.findUniqueOrThrow({ where: { id } });
    await this.prisma.submission.delete({ where: { id } });
  }

  async exportCsv(queryName?: string): Promise<string> {
    const where = queryName ? { queryName } : {};
    const rows = await this.prisma.submission.findMany({
      where,
      orderBy: { createdAt: "asc" },
    });
    return this.formatCsv(rows);
  }

  async exportZip(res: Response): Promise<void> {
    const rows = await this.prisma.submission.findMany({
      orderBy: [{ queryName: "asc" }, { createdAt: "asc" }],
    });
    const byQuery = new Map<string, typeof rows>();
    for (const row of rows) {
      const list = byQuery.get(row.queryName) ?? [];
      list.push(row);
      byQuery.set(row.queryName, list);
    }
    const archive = archiver("zip");
    archive.pipe(res);
    for (const [queryName, queryRows] of byQuery) {
      archive.append(this.formatCsv(queryRows), {
        name: `submission/${queryName}.csv`,
      });
    }
    await archive.finalize();
  }

  private formatCsv(rows: {
    queryType: string;
    videoId: string;
    frameIds: string;
    answer: string;
  }[]): string {
    const lines = rows.map((row) => {
      const frameIds = JSON.parse(row.frameIds) as number[];
      if (row.queryType === "trake") {
        return `${row.videoId},${frameIds.join(",")}`;
      }
      if (row.queryType === "qa") {
        const answer = row.answer.includes(",") || row.answer.includes('"')
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
    submittedBy: row.submittedBy,
    reviewedBy: row.reviewedBy,
    reviewNotes: row.reviewNotes,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  });
}
