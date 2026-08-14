import { Injectable, NotFoundException, ConflictException } from "@nestjs/common";
import { v4 as uuid } from "uuid";
import { PrismaService } from "../database/prisma.service";
import type {
  CreateQueryInput,
  QuerySnapshot,
  UpdateQueryInput,
} from "./query.types";

@Injectable()
export class QueryService {
  constructor(private readonly prisma: PrismaService) {}

  async listQueries(): Promise<QuerySnapshot[]> {
    const rows = await this.prisma.query.findMany({
      orderBy: { name: "asc" },
    });
    return rows.map(this.toSnapshot);
  }

  async getQuery(id: string): Promise<QuerySnapshot> {
    const row = await this.prisma.query.findUnique({ where: { id } });
    if (!row) throw new NotFoundException("Query not found");
    return this.toSnapshot(row);
  }

  async getQueryByName(name: string): Promise<QuerySnapshot> {
    const row = await this.prisma.query.findUnique({ where: { name } });
    if (!row) throw new NotFoundException("Query not found");
    return this.toSnapshot(row);
  }

  async createQuery(input: CreateQueryInput): Promise<QuerySnapshot> {
    const existing = await this.prisma.query.findUnique({
      where: { name: input.name },
    });
    if (existing) throw new ConflictException("Query name already exists");

    const now = new Date().toISOString();
    const row = await this.prisma.query.create({
      data: {
        id: uuid(),
        name: input.name,
        content: input.content ?? "",
        queryType: input.queryType ?? "kis",
        createdAt: now,
        updatedAt: now,
      },
    });
    return this.toSnapshot(row);
  }

  async updateQuery(
    id: string,
    input: UpdateQueryInput,
  ): Promise<QuerySnapshot> {
    await this.prisma.query.findUniqueOrThrow({ where: { id } });
    const row = await this.prisma.query.update({
      where: { id },
      data: {
        ...(input.content !== undefined ? { content: input.content } : {}),
        ...(input.queryType !== undefined ? { queryType: input.queryType } : {}),
        updatedAt: new Date().toISOString(),
      },
    });
    return this.toSnapshot(row);
  }

  async deleteQuery(id: string): Promise<void> {
    await this.prisma.query.findUniqueOrThrow({ where: { id } });
    await this.prisma.query.delete({ where: { id } });
  }

  private toSnapshot = (row: {
    id: string;
    name: string;
    content: string;
    queryType: string;
    createdAt: string;
    updatedAt: string;
  }): QuerySnapshot => ({
    id: row.id,
    name: row.name,
    content: row.content,
    queryType: row.queryType as QuerySnapshot["queryType"],
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  });
}
