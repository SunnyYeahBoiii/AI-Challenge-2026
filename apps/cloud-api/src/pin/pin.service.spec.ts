import { describe, expect, it } from "bun:test";
import { PinService } from "./pin.service";
import type { PrismaService } from "../database/prisma.service";
import type { AddPinInput } from "./pin.types";

interface PinRow {
  id: string;
  videoId: string;
  frameIndex: number;
  timestamp: number;
  fps: number;
  thumbnailUrl: string;
  createdAt: string;
}

/** Just enough of `prisma.pin` for the service: the wall is a flat table. */
function fakePrisma(rows: PinRow[] = []) {
  return {
    pin: {
      findMany: async () => [...rows].sort((a, b) => a.createdAt.localeCompare(b.createdAt)),
      count: async () => rows.length,
      findUnique: async ({
        where,
      }: {
        where: { videoId_frameIndex: { videoId: string; frameIndex: number } };
      }) =>
        rows.find(
          (r) =>
            r.videoId === where.videoId_frameIndex.videoId &&
            r.frameIndex === where.videoId_frameIndex.frameIndex,
        ) ?? null,
      create: async ({ data }: { data: PinRow }) => {
        rows.push(data);
        return data;
      },
      deleteMany: async ({
        where,
      }: {
        where?: { videoId: string; frameIndex: number };
      } = {}) => {
        const kept = where
          ? rows.filter(
              (r) => !(r.videoId === where.videoId && r.frameIndex === where.frameIndex),
            )
          : [];
        const count = rows.length - kept.length;
        rows.splice(0, rows.length, ...kept);
        return { count };
      },
    },
    rows,
  };
}

function service(rows: PinRow[] = []) {
  const prisma = fakePrisma(rows);
  return {
    pins: new PinService(prisma as unknown as PrismaService),
    rows: prisma.rows,
  };
}

const frame: AddPinInput = {
  videoId: "L01_V001",
  frameIndex: 120,
  timestamp: 4.8,
  fps: 25,
  thumbnailUrl: "http://x/1.jpg",
};

describe("PinService", () => {
  it("pins a frame and returns the whole wall", async () => {
    const { pins } = service();
    const wall = await pins.add(frame);
    expect(wall).toHaveLength(1);
    expect(wall[0]).toMatchObject({ videoId: "L01_V001", frameIndex: 120, fps: 25 });
  });

  it("does not duplicate a frame two teammates pin at once", async () => {
    const { pins, rows } = service();
    await pins.add(frame);
    const wall = await pins.add({ ...frame, thumbnailUrl: "http://x/other.jpg" });
    expect(wall).toHaveLength(1);
    expect(rows[0].thumbnailUrl).toBe("http://x/1.jpg");
  });

  it("keeps pins of the same frame index in different videos apart", async () => {
    const { pins } = service();
    await pins.add(frame);
    const wall = await pins.add({ ...frame, videoId: "L01_V002" });
    expect(wall.map((p) => p.videoId)).toEqual(["L01_V001", "L01_V002"]);
  });

  it("lets anyone unpin, by video and frame rather than by id", async () => {
    const { pins } = service();
    await pins.add(frame);
    await pins.add({ ...frame, frameIndex: 300 });
    const wall = await pins.remove({ videoId: "L01_V001", frameIndex: 120 });
    expect(wall.map((p) => p.frameIndex)).toEqual([300]);
  });

  it("ignores an unpin of a frame that is not on the wall", async () => {
    const { pins } = service();
    await pins.add(frame);
    const wall = await pins.remove({ videoId: "L01_V001", frameIndex: 999 });
    expect(wall).toHaveLength(1);
  });

  it("clears the whole wall", async () => {
    const { pins } = service();
    await pins.add(frame);
    await pins.add({ ...frame, frameIndex: 300 });
    expect(await pins.clear()).toEqual([]);
  });

  it("rejects a blank video id", async () => {
    const { pins } = service();
    await expect(pins.add({ ...frame, videoId: "  " })).rejects.toThrow("videoId is required");
  });

  it("rejects a fractional frame index", async () => {
    const { pins } = service();
    await expect(pins.add({ ...frame, frameIndex: 12.5 })).rejects.toThrow(
      "frameIndex must be a non-negative integer",
    );
  });
});
