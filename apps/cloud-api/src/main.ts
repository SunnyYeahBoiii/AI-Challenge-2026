import "dotenv/config";
import { ValidationPipe } from "@nestjs/common";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app.module";

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.useGlobalPipes(
    new ValidationPipe({ whitelist: true, transform: true }),
  );
  // No auth by decision (ADR 0005): the service is reachable only over the
  // team tailnet. Nothing uses cookies, so credentials stay off to avoid the
  // any-origin + credentials combination.
  app.enableCors({ origin: true });
  const port = Number(process.env.CLOUD_API_PORT || 5002);
  await app.listen(port);
  console.log(`cloud-api listening on http://localhost:${port}`);
}

bootstrap();
