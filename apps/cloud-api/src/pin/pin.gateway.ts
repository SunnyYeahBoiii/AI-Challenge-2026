import {
  ConnectedSocket,
  MessageBody,
  OnGatewayConnection,
  SubscribeMessage,
  WebSocketGateway,
  WebSocketServer,
  WsException,
} from "@nestjs/websockets";
import { Server, Socket } from "socket.io";
import { PinService } from "./pin.service";
import type { AddPinInput, PinSnapshot, RemovePinInput } from "./pin.types";

/** One shared wall for the whole team, so one room. */
const PIN_ROOM = "pins";

/**
 * Realtime pin wall. Unauthenticated like BoardGateway (ADR 0005: the service
 * is reachable only over the team tailnet), so any connected client may pin,
 * unpin or clear.
 */
@WebSocketGateway({ cors: { origin: true } })
export class PinGateway implements OnGatewayConnection {
  @WebSocketServer()
  server!: Server;

  constructor(private readonly pins: PinService) {}

  handleConnection(client: Socket) {
    client.join(PIN_ROOM);
  }

  private async run(fn: () => Promise<PinSnapshot[]>): Promise<PinSnapshot[]> {
    try {
      const pins = await fn();
      this.server.to(PIN_ROOM).emit("pins:changed", pins);
      return pins;
    } catch (err) {
      throw new WsException(
        err instanceof Error ? err.message : "Pin operation failed",
      );
    }
  }

  /** Sends the wall back on the same `pins:changed` channel the broadcasts
   * use, so the client needs one handler rather than an ack path as well. */
  @SubscribeMessage("pin:list")
  async handleList(@ConnectedSocket() client: Socket) {
    client.join(PIN_ROOM);
    client.emit("pins:changed", await this.pins.list());
  }

  @SubscribeMessage("pin:add")
  handleAdd(@MessageBody() body: AddPinInput) {
    return this.run(() => this.pins.add(body));
  }

  @SubscribeMessage("pin:remove")
  handleRemove(@MessageBody() body: RemovePinInput) {
    return this.run(() => this.pins.remove(body));
  }

  @SubscribeMessage("pin:clear")
  handleClear() {
    return this.run(() => this.pins.clear());
  }
}
