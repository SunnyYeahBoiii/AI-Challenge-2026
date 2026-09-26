import {
  ConnectedSocket,
  MessageBody,
  OnGatewayDisconnect,
  SubscribeMessage,
  WebSocketGateway,
  WebSocketServer,
  WsException,
} from "@nestjs/websockets";
import { Server, Socket } from "socket.io";
import { BoardService, SHARED_BOARD_ID } from "./board.service";
import type {
  AddCandidateInput,
  BoardSnapshot,
  SetSelectionInput,
} from "./board.types";

type JoinPayload = { displayName: string };

@WebSocketGateway({
  cors: { origin: true },
})
export class BoardGateway implements OnGatewayDisconnect {
  @WebSocketServer()
  server!: Server;

  constructor(private readonly boards: BoardService) {}

  /** Push a snapshot produced outside a socket handler (REST) to the room. */
  broadcast(snapshot: BoardSnapshot): BoardSnapshot {
    this.server.to(snapshot.id).emit("board:state", snapshot);
    return snapshot;
  }

  private async run(
    boardId: string,
    fn: () => Promise<BoardSnapshot>,
  ): Promise<BoardSnapshot> {
    try {
      const snapshot = await fn();
      this.server.to(boardId).emit("board:state", snapshot);
      return snapshot;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Board operation failed";
      throw new WsException(message);
    }
  }

  async handleDisconnect(client: Socket) {
    const boardId = client.data.boardId as string | undefined;
    const displayName = client.data.displayName as string | undefined;
    if (!boardId || !displayName) return;
    const snapshot = await this.boards.removeMember(boardId, displayName);
    if (snapshot) {
      this.server.to(boardId).emit("board:state", snapshot);
      this.server.to(boardId).emit("member:leave", { displayName });
    }
  }

  @SubscribeMessage("board:join")
  async handleJoin(
    @ConnectedSocket() client: Socket,
    @MessageBody() body: JoinPayload,
  ) {
    const boardId = SHARED_BOARD_ID;
    const { displayName } = body;
    const name = (displayName || "anon").slice(0, 64);
    await this.boards.getSharedBoard();
    if (client.data.boardId) {
      client.leave(client.data.boardId);
    }
    client.join(boardId);
    client.data.boardId = boardId;
    client.data.displayName = name;
    return this.run(boardId, () => this.boards.addMember(boardId, name));
  }

  @SubscribeMessage("board:rename")
  handleRename(
    @ConnectedSocket() client: Socket,
    @MessageBody() body: { displayName: string },
  ) {
    const boardId = client.data.boardId as string | undefined;
    const oldName = client.data.displayName as string | undefined;
    if (!boardId || !oldName) return;
    const name = (body.displayName || "anon").slice(0, 64);
    client.data.displayName = name;
    return this.run(boardId, () =>
      this.boards.renameMember(boardId, oldName, name),
    );
  }

  @SubscribeMessage("event:add")
  handleEventAdd(@MessageBody() body: { labelText?: string }) {
    return this.run(SHARED_BOARD_ID, () =>
      this.boards.addEvent(SHARED_BOARD_ID, body.labelText ?? ""),
    );
  }

  @SubscribeMessage("event:remove")
  handleEventRemove(@MessageBody() body: { eventId: string }) {
    return this.run(SHARED_BOARD_ID, () =>
      this.boards.removeEvent(SHARED_BOARD_ID, body.eventId),
    );
  }

  @SubscribeMessage("event:reorder")
  handleEventReorder(@MessageBody() body: { orderedEventIds: string[] }) {
    return this.run(SHARED_BOARD_ID, () =>
      this.boards.reorderEvents(SHARED_BOARD_ID, body.orderedEventIds),
    );
  }

  @SubscribeMessage("event:updateText")
  handleEventUpdateText(
    @MessageBody()
    body: { eventId: string; labelText: string },
  ) {
    return this.run(SHARED_BOARD_ID, () =>
      this.boards.updateEventText(SHARED_BOARD_ID, body.eventId, body.labelText),
    );
  }

  @SubscribeMessage("candidate:add")
  handleCandidateAdd(@MessageBody() body: AddCandidateInput) {
    return this.run(SHARED_BOARD_ID, () =>
      this.boards.addCandidate(SHARED_BOARD_ID, body),
    );
  }

  @SubscribeMessage("candidate:remove")
  handleCandidateRemove(@MessageBody() body: { candidateId: string }) {
    return this.run(SHARED_BOARD_ID, () =>
      this.boards.removeCandidate(SHARED_BOARD_ID, body.candidateId),
    );
  }

  @SubscribeMessage("selection:set")
  handleSelectionSet(@MessageBody() body: SetSelectionInput) {
    return this.run(SHARED_BOARD_ID, () =>
      this.boards.setSelection(SHARED_BOARD_ID, body),
    );
  }

  @SubscribeMessage("selection:clear")
  handleSelectionClear(@MessageBody() body: { eventId: string }) {
    return this.run(SHARED_BOARD_ID, () =>
      this.boards.clearSelection(SHARED_BOARD_ID, body.eventId),
    );
  }
}
