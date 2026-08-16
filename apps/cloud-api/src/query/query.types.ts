import { IsIn, IsNotEmpty, IsOptional, IsString, MaxLength } from "class-validator";

export type QueryType = "kis" | "qa" | "trake";

export interface QuerySnapshot {
  id: string;
  name: string;
  content: string;
  queryType: QueryType;
  createdAt: string;
  updatedAt: string;
}

export class CreateQueryInput {
  @IsString()
  @IsNotEmpty()
  @MaxLength(200)
  name!: string;

  @IsOptional()
  @IsString()
  @MaxLength(8000)
  content?: string;

  @IsOptional()
  @IsIn(["kis", "qa", "trake"])
  queryType?: QueryType;
}

export class UpdateQueryInput {
  @IsOptional()
  @IsString()
  @MaxLength(8000)
  content?: string;

  @IsOptional()
  @IsIn(["kis", "qa", "trake"])
  queryType?: QueryType;
}
