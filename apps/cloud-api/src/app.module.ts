import { Module } from "@nestjs/common";
import { DatabaseModule } from "./database/database.module";
import { BoardModule } from "./board/board.module";
import { PinModule } from "./pin/pin.module";

@Module({
  imports: [DatabaseModule, BoardModule, PinModule],
})
export class AppModule {}
