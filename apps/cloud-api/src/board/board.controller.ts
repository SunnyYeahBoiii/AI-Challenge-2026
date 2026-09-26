import { Body, Controller, Get, Post, Put } from "@nestjs/common";
import { BoardGateway } from "./board.gateway";
import { BoardService, SHARED_BOARD_ID } from "./board.service";
import {
  AddBoardEventInput,
  AddCandidateBody,
  ReorderBoardEventsInput,
} from "./board.types";

@Controller("boards")
export class BoardController {
  constructor(
    private readonly boards: BoardService,
    private readonly gateway: BoardGateway,
  ) {}

  @Get("shared")
  getShared() {
    return this.boards.getSharedBoard();
  }

  @Post("shared/events")
  addEvent(@Body() body: AddBoardEventInput) {
    return this.boards.addEvent(SHARED_BOARD_ID, body.labelText ?? "");
  }

  @Put("shared/events/reorder")
  reorder(@Body() body: ReorderBoardEventsInput) {
    return this.boards.reorderEvents(SHARED_BOARD_ID, body.orderedEventIds);
  }

  @Post("shared/candidates")
  async addCandidate(@Body() body: AddCandidateBody) {
    const snapshot = await this.boards.addCandidate(SHARED_BOARD_ID, body);
    return this.gateway.broadcast(snapshot);
  }
}
