import { Body, Controller, Get, Param, Post, Put } from "@nestjs/common";
import { BoardService } from "./board.service";

@Controller("boards")
export class BoardController {
  constructor(private readonly boards: BoardService) {}

  @Get()
  async list() {
    return { boards: await this.boards.listBoards() };
  }

  @Post()
  create(@Body() body: { title?: string }) {
    return this.boards.createBoard(body?.title);
  }

  @Get(":id")
  get(@Param("id") id: string) {
    return this.boards.getBoard(id);
  }

  @Post(":id/events")
  addEvent(
    @Param("id") id: string,
    @Body() body: { labelText?: string },
  ) {
    return this.boards.addEvent(id, body?.labelText ?? "");
  }

  @Put(":id/events/reorder")
  reorder(
    @Param("id") id: string,
    @Body() body: { orderedEventIds: string[] },
  ) {
    return this.boards.reorderEvents(id, body.orderedEventIds ?? []);
  }
}
