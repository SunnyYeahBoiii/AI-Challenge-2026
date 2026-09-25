import { describe, expect, it } from "bun:test";
import { BoardGateway } from "./board.gateway";
import { SHARED_BOARD_ID } from "./board.service";
import type { BoardService } from "./board.service";
import type { Server, Socket } from "socket.io";

describe("BoardGateway shared board", () => {
  it("joins every client to the shared room without a board code", async () => {
    const rooms: string[] = [];
    const broadcasts: string[] = [];
    const service = {
      getSharedBoard: async () => ({ id: SHARED_BOARD_ID }),
      addMember: async (id: string, name: string) => {
        expect(id).toBe(SHARED_BOARD_ID);
        return { id, members: [name] };
      },
      addEvent: async (id: string) => {
        expect(id).toBe(SHARED_BOARD_ID);
        return { id, members: [] };
      },
    } as unknown as BoardService;
    const gateway = new BoardGateway(service);
    gateway.server = {
      to: (room: string) => {
        broadcasts.push(room);
        return { emit: () => undefined };
      },
    } as unknown as Server;
    const client = {
      data: {},
      join: (room: string) => rooms.push(room),
      leave: () => undefined,
    } as unknown as Socket;

    await gateway.handleJoin(client, { displayName: "Alice" });
    await gateway.handleEventAdd({ labelText: "start" });

    expect(rooms).toEqual([SHARED_BOARD_ID]);
    expect(broadcasts).toEqual([SHARED_BOARD_ID, SHARED_BOARD_ID]);
  });
});
