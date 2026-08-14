import { Module } from "@nestjs/common";
import { SubmissionController } from "./submission.controller";
import { SubmissionGateway } from "./submission.gateway";
import { SubmissionService } from "./submission.service";

@Module({
  controllers: [SubmissionController],
  providers: [SubmissionService, SubmissionGateway],
  exports: [SubmissionService],
})
export class SubmissionModule {}
