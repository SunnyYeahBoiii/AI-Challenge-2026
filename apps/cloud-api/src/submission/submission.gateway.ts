import {
  ConnectedSocket,
  MessageBody,
  SubscribeMessage,
  WebSocketGateway,
  WebSocketServer,
  WsException,
} from "@nestjs/websockets";
import { Server } from "socket.io";
import { SubmissionService } from "./submission.service";
import type {
  CreateSubmissionInput,
  SubmissionSnapshot,
  UpdateSubmissionInput,
} from "./submission.types";

@WebSocketGateway({
  cors: { origin: true, credentials: true },
})
export class SubmissionGateway {
  @WebSocketServer()
  server!: Server;

  constructor(private readonly submissions: SubmissionService) {}

  private async run(fn: () => Promise<SubmissionSnapshot>): Promise<SubmissionSnapshot> {
    try {
      const snapshot = await fn();
      this.server.emit("submissions:changed", await this.submissions.listSubmissions());
      return snapshot;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Submission operation failed";
      throw new WsException(message);
    }
  }

  @SubscribeMessage("submissions:list")
  async handleList() {
    return this.submissions.listSubmissions();
  }

  @SubscribeMessage("submission:create")
  handleCreate(@MessageBody() body: CreateSubmissionInput) {
    return this.run(() => this.submissions.createSubmission(body));
  }

  @SubscribeMessage("submission:update")
  handleUpdate(
    @MessageBody() body: { id: string } & UpdateSubmissionInput,
  ) {
    const { id, ...input } = body;
    return this.run(() => this.submissions.updateSubmission(id, input));
  }

  @SubscribeMessage("submission:delete")
  async handleDelete(@MessageBody() body: { id: string }) {
    await this.submissions.deleteSubmission(body.id);
    this.server.emit("submissions:changed", await this.submissions.listSubmissions());
    return { ok: true };
  }
}
