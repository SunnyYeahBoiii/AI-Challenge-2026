import { describe, expect, it } from "bun:test";
import { BoardService, SHARED_BOARD_ID } from "./board.service";
import type { PrismaService } from "../database/prisma.service";

describe("BoardService shared board", () => {
  it("creates one persistent board and returns it for every visitor", async () => {
    const rows = new Map<string, {
      id: string;
      title: string;
      targetVideoId: null;
      createdAt: string;
      updatedAt: string;
      events: [];
    }>();
    const prisma = {
      board: {
        upsert: async ({ where, create }: {
          where: { id: string };
          create: { id: string; title: string; targetVideoId: null; createdAt: string; updatedAt: string };
        }) => {
          if (!rows.has(where.id)) rows.set(where.id, { ...create, events: [] });
        },
        findUnique: async ({ where }: { where: { id: string } }) =>
          rows.get(where.id) ?? null,
      },
    } as unknown as PrismaService;
    const service = new BoardService(prisma);

    const first = await service.getSharedBoard();
    const second = await service.getSharedBoard();

    expect(rows.size).toBe(1);
    expect(first.id).toBe(SHARED_BOARD_ID);
    expect(second.id).toBe(first.id);
    expect(second.createdAt).toBe(first.createdAt);
  });
});
