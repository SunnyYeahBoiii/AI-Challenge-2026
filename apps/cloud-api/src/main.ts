import "dotenv/config";
import { ValidationPipe } from "@nestjs/common";
import { NestFactory } from "@nestjs/core";
import { AppModule } from "./app.module";

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.useGlobalPipes(
    new ValidationPipe({ whitelist: true, transform: true }),
  );
  app.enableCors({ origin: true, credentials: true });
  const port = Number(process.env.CLOUD_API_PORT || 5002);
  await app.listen(port);
  console.log(`cloud-api listening on http://localhost:${port}`);
}

bootstrap();
