import { describe, expect, it } from "vitest";

import { nextInfinitePaginationState } from "./infinite-pagination";

describe("infinite pagination", () => {
  it("requires the sentinel to leave before loading another page", () => {
    expect(nextInfinitePaginationState({ armed: true, isIntersecting: true }))
      .toEqual({ armed: false, shouldLoad: true });
    expect(nextInfinitePaginationState({ armed: false, isIntersecting: true }))
      .toEqual({ armed: false, shouldLoad: false });
    expect(nextInfinitePaginationState({ armed: false, isIntersecting: false }))
      .toEqual({ armed: true, shouldLoad: false });
  });
});
