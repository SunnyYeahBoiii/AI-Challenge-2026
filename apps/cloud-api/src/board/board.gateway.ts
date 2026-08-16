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
import { BoardService } from "./board.service";
import type {
  AddCandidateInput,
  BoardSnapshot,
  SetSelectionInput,
} from "./board.types";

type JoinPayload = { boardId: string; displayName: string };

@WebSocketGateway({
  cors: { origin: true, credentials: true },
})
export class BoardGateway implements OnGatewayDisconnect {
  @WebSocketServer()
  server!: Server;

  constructor(private readonly boards: BoardService) {}

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
  handleJoin(
    @ConnectedSocket() client: Socket,
    @MessageBody() body: JoinPayload,
  ) {
    const { boardId: rawBoardId, displayName } = body;
    const boardId = rawBoardId.trim().toUpperCase();
    const name = (displayName || "anon").slice(0, 64);
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
  handleEventAdd(
    @MessageBody() body: { boardId: string; labelText?: string },
  ) {
    return this.run(body.boardId, () =>
      this.boards.addEvent(body.boardId, body.labelText ?? ""),
    );
  }

  @SubscribeMessage("event:remove")
  handleEventRemove(
    @MessageBody() body: { boardId: string; eventId: string },
  ) {
    return this.run(body.boardId, () =>
      this.boards.removeEvent(body.boardId, body.eventId),
    );
  }

  @SubscribeMessage("event:reorder")
  handleEventReorder(
    @MessageBody() body: { boardId: string; orderedEventIds: string[] },
  ) {
    return this.run(body.boardId, () =>
      this.boards.reorderEvents(body.boardId, body.orderedEventIds),
    );
  }

  @SubscribeMessage("event:updateText")
  handleEventUpdateText(
    @MessageBody()
    body: { boardId: string; eventId: string; labelText: string },
  ) {
    return this.run(body.boardId, () =>
      this.boards.updateEventText(body.boardId, body.eventId, body.labelText),
    );
  }

  @SubscribeMessage("candidate:add")
  handleCandidateAdd(
    @MessageBody() body: { boardId: string } & AddCandidateInput,
  ) {
    const { boardId, ...input } = body;
    return this.run(boardId, () => this.boards.addCandidate(boardId, input));
  }

  @SubscribeMessage("candidate:remove")
  handleCandidateRemove(
    @MessageBody() body: { boardId: string; candidateId: string },
  ) {
    return this.run(body.boardId, () =>
      this.boards.removeCandidate(body.boardId, body.candidateId),
    );
  }

  @SubscribeMessage("selection:set")
  handleSelectionSet(
    @MessageBody() body: { boardId: string } & SetSelectionInput,
  ) {
    const { boardId, ...input } = body;
    return this.run(boardId, () => this.boards.setSelection(boardId, input));
  }

  @SubscribeMessage("selection:clear")
  handleSelectionClear(
    @MessageBody() body: { boardId: string; eventId: string },
  ) {
    return this.run(body.boardId, () =>
      this.boards.clearSelection(body.boardId, body.eventId),
    );
  }
}
