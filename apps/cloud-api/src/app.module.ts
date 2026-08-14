import { Module } from "@nestjs/common";
import { DatabaseModule } from "./database/database.module";
import { BoardModule } from "./board/board.module";
import { SubmissionModule } from "./submission/submission.module";
import { QueryModule } from "./query/query.module";

@Module({
  imports: [DatabaseModule, BoardModule, SubmissionModule, QueryModule],
})
export class AppModule {}
