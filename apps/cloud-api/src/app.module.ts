import { Module } from "@nestjs/common";
import { DatabaseModule } from "./database/database.module";
import { BoardModule } from "./board/board.module";

@Module({
  imports: [DatabaseModule, BoardModule],
})
export class AppModule {}
