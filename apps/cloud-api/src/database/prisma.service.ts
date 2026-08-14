import { Injectable, OnModuleDestroy, OnModuleInit } from "@nestjs/common";
import { PrismaClient } from "@prisma/client";

@Injectable()
export class PrismaService
  extends PrismaClient
  implements OnModuleInit, OnModuleDestroy
{
  async onModuleInit() {
    await this.$connect();
    // Match prior node:sqlite defaults for single-process collab durability.
    await this.$queryRawUnsafe("PRAGMA journal_mode = WAL");
    await this.$queryRawUnsafe("PRAGMA foreign_keys = ON");
  }

  async onModuleDestroy() {
    await this.$disconnect();
  }
}
