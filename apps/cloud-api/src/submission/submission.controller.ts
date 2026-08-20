import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Post,
  Put,
  Query,
  Res,
} from "@nestjs/common";
import { Response } from "express";
import { SubmissionService, sanitizeFileToken } from "./submission.service";
import {
  CreateSubmissionInput,
  ReorderInput,
  UpdateSubmissionInput,
} from "./submission.types";

@Controller("submissions")
export class SubmissionController {
  constructor(private readonly submissions: SubmissionService) {}

  @Get()
  async list() {
    return { submissions: await this.submissions.listSubmissions() };
  }

  @Get("export")
  async exportCsv(
    @Query("query") queryName: string | undefined,
    @Res() res: Response,
  ) {
    const csv = await this.submissions.exportCsv(queryName);
    const fileToken = sanitizeFileToken(queryName ?? "submissions-all");
    res.setHeader("Content-Type", "text/csv; charset=utf-8");
    res.setHeader(
      "Content-Disposition",
      `attachment; filename="${fileToken}.csv"`,
    );
    res.send(csv);
  }

  @Get("export-all")
  async exportAllZip(@Res() res: Response) {
    res.setHeader("Content-Type", "application/zip");
    res.setHeader(
      "Content-Disposition",
      'attachment; filename="submission.zip"',
    );
    await this.submissions.exportZip(res);
  }

  @Get(":id")
  async get(@Param("id") id: string) {
    return this.submissions.getSubmission(id);
  }

  @Post()
  async create(@Body() body: CreateSubmissionInput) {
    return this.submissions.createSubmission(body);
  }

  @Put(":id")
  async update(
    @Param("id") id: string,
    @Body() body: UpdateSubmissionInput,
  ) {
    return this.submissions.updateSubmission(id, body);
  }

  @Put("reorder/group")
  async reorder(@Body() body: ReorderInput) {
    return this.submissions.reorderInGroup(body);
  }

  @Delete(":id")
  async remove(@Param("id") id: string) {
    await this.submissions.deleteSubmission(id);
    return { ok: true };
  }
}
