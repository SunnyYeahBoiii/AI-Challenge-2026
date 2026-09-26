import { describe, expect, it } from "vitest";

import { levelOf } from "./video-id";

describe("levelOf", () => {
  it("keeps three-character levels intact", () => {
    expect(levelOf("L21_V001")).toBe("L21");
    expect(levelOf("M10_V031")).toBe("M10");
    expect(levelOf("S01-V001")).toBe("S01");
  });

  it("does not truncate four-character N levels", () => {
    expect(levelOf("N001-V001")).toBe("N001");
    expect(levelOf("N100-V012")).toBe("N100");
  });

  it("stays total for ids without a level prefix", () => {
    expect(levelOf("")).toBe("");
    expect(levelOf("1234")).toBe("");
  });
});
