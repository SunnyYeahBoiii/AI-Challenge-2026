import { describe, expect, it } from "bun:test";
import { BoardController } from "./board.controller";
import { BoardGateway } from "./board.gateway";
import { SHARED_BOARD_ID } from "./board.service";
import type { BoardService } from "./board.service";
import type { AddCandidateBody } from "./board.types";
import type { Server } from "socket.io";

describe("BoardController REST candidate", () => {
  it("adds a candidate to the shared board and broadcasts the snapshot", async () => {
    const emitted: Array<[string, string]> = [];
    const service = {
      addCandidate: async (id: string) => ({ id, events: [] }),
    } as unknown as BoardService;
    const gateway = new BoardGateway(service);
    gateway.server = {
      to: (room: string) => ({
        emit: (event: string) => emitted.push([room, event]),
      }),
    } as unknown as Server;
    const controller = new BoardController(service, gateway);

    const snapshot = await controller.addCandidate({
      eventId: "e1",
      videoId: "L21_V001",
      ptsTime: 12.5,
      previewFrameId: "300",
      fps: 25,
      frameIdx: 300,
      addedBy: "agent",
    } satisfies AddCandidateBody);

    expect(snapshot.id).toBe(SHARED_BOARD_ID);
    expect(emitted).toEqual([[SHARED_BOARD_ID, "board:state"]]);
  });
});
