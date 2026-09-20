import { Module } from "@nestjs/common";
import { PinGateway } from "./pin.gateway";
import { PinService } from "./pin.service";

@Module({
  providers: [PinService, PinGateway],
  exports: [PinService],
})
export class PinModule {}
