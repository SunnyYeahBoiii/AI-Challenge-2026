import { BadRequestException, Injectable } from "@nestjs/common";
import { v4 as uuid } from "uuid";
import { PrismaService } from "../database/prisma.service";
import type { AddPinInput, PinSnapshot, RemovePinInput } from "./pin.types";

/** Guards the wall against a runaway client filling the table. */
const MAX_PINS = 500;

@Injectable()
export class PinService {
  constructor(private readonly prisma: PrismaService) {}

  async list(): Promise<PinSnapshot[]> {
    const rows = await this.prisma.pin.findMany({
      orderBy: { createdAt: "asc" },
    });
    return rows.map(toSnapshot);
  }

  /**
   * Pin a frame, or leave the existing pin alone if it is already up.
   *
   * The (videoId, frameIndex) uniqueness makes a second pin of the same frame
   * a no-op instead of a duplicate row, so two teammates clicking the same
   * keyframe cannot double it.
   */
  async add(input: AddPinInput): Promise<PinSnapshot[]> {
    const videoId = input.videoId?.trim();
    if (!videoId) throw new BadRequestException("videoId is required");
    if (!Number.isInteger(input.frameIndex) || input.frameIndex < 0) {
      throw new BadRequestException("frameIndex must be a non-negative integer");
    }
    const count = await this.prisma.pin.count();
    const existing = await this.prisma.pin.findUnique({
      where: { videoId_frameIndex: { videoId, frameIndex: input.frameIndex } },
    });
    if (!existing) {
      if (count >= MAX_PINS) {
        throw new BadRequestException(
          `Pin wall is full (${MAX_PINS}); clear some pins first`,
        );
      }
      await this.prisma.pin.create({
        data: {
          id: uuid(),
          videoId,
          frameIndex: input.frameIndex,
          timestamp: Number(input.timestamp) || 0,
          fps: Number(input.fps) || 0,
          thumbnailUrl: input.thumbnailUrl ?? "",
          createdAt: new Date().toISOString(),
        },
      });
    }
    return this.list();
  }

  /** Anyone may unpin anything: the wall has no owner by decision. */
  async remove(input: RemovePinInput): Promise<PinSnapshot[]> {
    await this.prisma.pin.deleteMany({
      where: { videoId: input.videoId, frameIndex: input.frameIndex },
    });
    return this.list();
  }

  async clear(): Promise<PinSnapshot[]> {
    await this.prisma.pin.deleteMany({});
    return this.list();
  }
}

function toSnapshot(row: {
  id: string;
  videoId: string;
  frameIndex: number;
  timestamp: number;
  fps: number;
  thumbnailUrl: string;
  createdAt: string;
}): PinSnapshot {
  return {
    id: row.id,
    videoId: row.videoId,
    frameIndex: row.frameIndex,
    timestamp: row.timestamp,
    fps: row.fps,
    thumbnailUrl: row.thumbnailUrl,
    createdAt: row.createdAt,
  };
}
