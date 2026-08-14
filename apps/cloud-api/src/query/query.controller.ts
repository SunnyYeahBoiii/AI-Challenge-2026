import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Post,
  Put,
} from "@nestjs/common";
import { QueryService } from "./query.service";
import type { CreateQueryInput, UpdateQueryInput } from "./query.types";

@Controller("queries")
export class QueryController {
  constructor(private readonly queries: QueryService) {}

  @Get()
  async list() {
    return { queries: await this.queries.listQueries() };
  }

  @Get(":id")
  async get(@Param("id") id: string) {
    return this.queries.getQuery(id);
  }

  @Post()
  async create(@Body() body: CreateQueryInput) {
    return this.queries.createQuery(body);
  }

  @Put(":id")
  async update(@Param("id") id: string, @Body() body: UpdateQueryInput) {
    return this.queries.updateQuery(id, body);
  }

  @Delete(":id")
  async remove(@Param("id") id: string) {
    await this.queries.deleteQuery(id);
    return { ok: true };
  }
}
