import {
  BadRequestException,
  Injectable,
  NotFoundException,
} from "@nestjs/common";
import { randomInt } from "node:crypto";
import { v4 as uuid } from "uuid";
import { PrismaService } from "../database/prisma.service";
import type {
  AddCandidateInput,
  BoardEventSnapshot,
  BoardSnapshot,
  CandidateSnapshot,
  SelectionSnapshot,
  SetSelectionInput,
} from "./board.types";

/** Ambiguity-safe alphabet for shareable 6-char board codes. */
const BOARD_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

@Injectable()
export class BoardService {
  /** boardId -> display names currently connected */
  private readonly presence = new Map<string, Set<string>>();

  constructor(private readonly prisma: PrismaService) {}

  private async newBoardId(): Promise<string> {
    for (let attempt = 0; attempt < 32; attempt++) {
      let id = "";
      for (let i = 0; i < 6; i++) {
        id += BOARD_ID_ALPHABET[randomInt(BOARD_ID_ALPHABET.length)];
      }
      const existing = await this.prisma.board.findUnique({
        where: { id },
        select: { id: true },
      });
      if (!existing) return id;
    }
    throw new BadRequestException("Could not allocate a unique board id");
  }

  async createBoard(title = "TRAKE Board"): Promise<BoardSnapshot> {
    const now = new Date().toISOString();
    const id = await this.newBoardId();
    await this.prisma.board.create({
      data: {
        id,
        title,
        targetVideoId: null,
        createdAt: now,
        updatedAt: now,
      },
    });
    return this.getBoard(id);
  }

  async listBoards(): Promise<
    Array<{ id: string; title: string; updatedAt: string }>
  > {
    const rows = await this.prisma.board.findMany({
      orderBy: { updatedAt: "desc" },
      take: 50,
      select: { id: true, title: true, updatedAt: true },
    });
    return rows;
  }

  async getBoard(boardId: string): Promise<BoardSnapshot> {
    const id = this.normalizeBoardId(boardId);
    const board = await this.prisma.board.findUnique({
      where: { id },
      include: {
        events: {
          orderBy: { position: "asc" },
          include: {
            candidates: { orderBy: { createdAt: "asc" } },
            selection: true,
          },
        },
      },
    });
    if (!board) throw new NotFoundException("Board not found");

    const eventSnaps: BoardEventSnapshot[] = board.events.map((ev, index) => ({
      id: ev.id,
      position: ev.position,
      labelText: ev.labelText,
      displayLabel: `E${index + 1}`,
      candidates: ev.candidates.map(this.toCandidateSnapshot),
      selection: ev.selection ? this.toSelectionSnapshot(ev.selection) : null,
    }));

    return {
      id: board.id,
      title: board.title,
      targetVideoId: board.targetVideoId,
      createdAt: board.createdAt,
      updatedAt: board.updatedAt,
      events: eventSnaps,
      members: [...(this.presence.get(id) ?? [])],
    };
  }

  async addMember(boardId: string, name: string): Promise<BoardSnapshot> {
    const id = this.normalizeBoardId(boardId);
    await this.requireBoard(id);
    if (!this.presence.has(id)) this.presence.set(id, new Set());
    this.presence.get(id)!.add(name);
    return this.getBoard(id);
  }

  async removeMember(
    boardId: string,
    name: string,
  ): Promise<BoardSnapshot | null> {
    const id = this.normalizeBoardId(boardId);
    this.presence.get(id)?.delete(name);
    try {
      return await this.getBoard(id);
    } catch {
      return null;
    }
  }

  async addEvent(boardId: string, labelText = ""): Promise<BoardSnapshot> {
    const id = this.normalizeBoardId(boardId);
    await this.requireBoard(id);
    const agg = await this.prisma.event.aggregate({
      where: { boardId: id },
      _max: { position: true },
    });
    const nextPos = (agg._max.position ?? -1) + 1;
    const now = new Date().toISOString();
    await this.prisma.event.create({
      data: {
        id: uuid(),
        boardId: id,
        position: nextPos,
        labelText,
        createdAt: now,
      },
    });
    await this.touchBoard(id);
    return this.getBoard(id);
  }

  async removeEvent(boardId: string, eventId: string): Promise<BoardSnapshot> {
    const id = this.normalizeBoardId(boardId);
    await this.assertEventOnBoard(id, eventId);
    await this.prisma.event.delete({ where: { id: eventId } });
    await this.reindexPositions(id);
    await this.refreshTargetVideo(id);
    await this.touchBoard(id);
    return this.getBoard(id);
  }

  async reorderEvents(
    boardId: string,
    orderedEventIds: string[],
  ): Promise<BoardSnapshot> {
    const id = this.normalizeBoardId(boardId);
    const events = await this.prisma.event.findMany({
      where: { boardId: id },
      select: { id: true },
    });
    const existing = new Set(events.map((e) => e.id));
    if (
      orderedEventIds.length !== existing.size ||
      orderedEventIds.some((eid) => !existing.has(eid))
    ) {
      throw new BadRequestException("orderedEventIds must list every event once");
    }
    await this.prisma.$transaction(
      orderedEventIds.map((eventId, i) =>
        this.prisma.event.update({
          where: { id: eventId },
          data: { position: i },
        }),
      ),
    );
    await this.touchBoard(id);
    return this.getBoard(id);
  }

  async updateEventText(
    boardId: string,
    eventId: string,
    labelText: string,
  ): Promise<BoardSnapshot> {
    const id = this.normalizeBoardId(boardId);
    await this.assertEventOnBoard(id, eventId);
    await this.prisma.event.update({
      where: { id: eventId },
      data: { labelText },
    });
    await this.touchBoard(id);
    return this.getBoard(id);
  }

  async addCandidate(
    boardId: string,
    input: AddCandidateInput,
  ): Promise<BoardSnapshot> {
    const id = this.normalizeBoardId(boardId);
    await this.assertEventOnBoard(id, input.eventId);
    const now = new Date().toISOString();
    await this.prisma.candidate.create({
      data: {
        id: uuid(),
        eventId: input.eventId,
        videoId: input.videoId,
        ptsTime: input.ptsTime,
        previewFrameId: input.previewFrameId,
        fps: input.fps,
        frameIdx: input.frameIdx,
        thumbnailUrl: input.thumbnailUrl ?? "",
        addedBy: input.addedBy ?? "",
        createdAt: now,
      },
    });
    await this.touchBoard(id);
    return this.getBoard(id);
  }

  async removeCandidate(
    boardId: string,
    candidateId: string,
  ): Promise<BoardSnapshot> {
    const id = this.normalizeBoardId(boardId);
    const row = await this.prisma.candidate.findUnique({
      where: { id: candidateId },
      include: { event: { select: { boardId: true } } },
    });
    if (!row || row.event.boardId !== id) {
      throw new NotFoundException("Candidate not found");
    }
    await this.prisma.candidate.delete({ where: { id: candidateId } });
    await this.touchBoard(id);
    return this.getBoard(id);
  }

  async setSelection(
    boardId: string,
    input: SetSelectionInput,
  ): Promise<BoardSnapshot> {
    const id = this.normalizeBoardId(boardId);
    await this.assertEventOnBoard(id, input.eventId);
    const board = await this.requireBoard(id);
    if (board.targetVideoId && board.targetVideoId !== input.videoId) {
      throw new BadRequestException(
        `Selection must use Target Video ${board.targetVideoId}`,
      );
    }
    const now = new Date().toISOString();
    await this.prisma.selection.upsert({
      where: { eventId: input.eventId },
      create: {
        eventId: input.eventId,
        candidateId: input.candidateId ?? null,
        videoId: input.videoId,
        ptsTime: input.ptsTime,
        previewFrameId: input.previewFrameId,
        fps: input.fps,
        updatedBy: input.updatedBy ?? "",
        updatedAt: now,
      },
      update: {
        candidateId: input.candidateId ?? null,
        videoId: input.videoId,
        ptsTime: input.ptsTime,
        previewFrameId: input.previewFrameId,
        fps: input.fps,
        updatedBy: input.updatedBy ?? "",
        updatedAt: now,
      },
    });
    if (!board.targetVideoId) {
      await this.prisma.board.update({
        where: { id },
        data: { targetVideoId: input.videoId },
      });
    }
    await this.touchBoard(id);
    return this.getBoard(id);
  }

  async clearSelection(
    boardId: string,
    eventId: string,
  ): Promise<BoardSnapshot> {
    const id = this.normalizeBoardId(boardId);
    await this.assertEventOnBoard(id, eventId);
    await this.prisma.selection.deleteMany({ where: { eventId } });
    await this.refreshTargetVideo(id);
    await this.touchBoard(id);
    return this.getBoard(id);
  }

  private async requireBoard(boardId: string) {
    const board = await this.prisma.board.findUnique({
      where: { id: this.normalizeBoardId(boardId) },
    });
    if (!board) throw new NotFoundException("Board not found");
    return board;
  }

  private normalizeBoardId(boardId: string): string {
    return boardId.trim().toUpperCase();
  }

  private async assertEventOnBoard(boardId: string, eventId: string) {
    const ev = await this.prisma.event.findUnique({ where: { id: eventId } });
    if (!ev || ev.boardId !== boardId) {
      throw new NotFoundException("Event not found on board");
    }
    return ev;
  }

  private async reindexPositions(boardId: string) {
    const events = await this.prisma.event.findMany({
      where: { boardId },
      orderBy: { position: "asc" },
      select: { id: true },
    });
    await this.prisma.$transaction(
      events.map((e, i) =>
        this.prisma.event.update({
          where: { id: e.id },
          data: { position: i },
        }),
      ),
    );
  }

  /** Keep Target Video in sync with remaining selections (by event order). */
  private async refreshTargetVideo(boardId: string): Promise<void> {
    const row = await this.prisma.selection.findFirst({
      where: { event: { boardId } },
      orderBy: { event: { position: "asc" } },
      select: { videoId: true },
    });
    await this.prisma.board.update({
      where: { id: boardId },
      data: { targetVideoId: row?.videoId ?? null },
    });
  }

  private async touchBoard(boardId: string) {
    await this.prisma.board.update({
      where: { id: boardId },
      data: { updatedAt: new Date().toISOString() },
    });
  }

  private toCandidateSnapshot = (c: {
    id: string;
    videoId: string;
    ptsTime: number;
    previewFrameId: string;
    fps: number;
    frameIdx: number;
    thumbnailUrl: string;
    addedBy: string;
    createdAt: string;
  }): CandidateSnapshot => ({
    id: c.id,
    videoId: c.videoId,
    ptsTime: c.ptsTime,
    previewFrameId: c.previewFrameId,
    fps: c.fps,
    frameIdx: c.frameIdx,
    thumbnailUrl: c.thumbnailUrl,
    addedBy: c.addedBy,
    createdAt: c.createdAt,
  });

  private toSelectionSnapshot = (s: {
    eventId: string;
    candidateId: string | null;
    videoId: string;
    ptsTime: number;
    previewFrameId: string;
    fps: number;
    updatedBy: string;
    updatedAt: string;
  }): SelectionSnapshot => ({
    eventId: s.eventId,
    candidateId: s.candidateId,
    videoId: s.videoId,
    ptsTime: s.ptsTime,
    previewFrameId: s.previewFrameId,
    fps: s.fps,
    updatedBy: s.updatedBy,
    updatedAt: s.updatedAt,
  });
}
