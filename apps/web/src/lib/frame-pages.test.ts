import { describe, expect, it } from "vitest";

import {
  KEYFRAME_PAGE_SIZE,
  clampPageStart,
  hasFramesAfterWindow,
  maxPageStart,
  nextPageStart,
  offsetInPage,
  pageBounds,
  pageStartAfterFetch,
  pageStartForIndex,
  previousPageStart,
  resolveNextPage,
} from "./frame-pages";

// Frame indices are only ever compared for equality here, so plain numbers
// stand in for FrameResult.
const frames = (n: number, from = 0) =>
  Array.from({ length: n }, (_, i) => ({ frame_index: from + i }));

describe("page arithmetic", () => {
  it("steps exactly one page at a time", () => {
    expect(nextPageStart(0, 40)).toBe(5);
    expect(nextPageStart(5, 40)).toBe(10);
    expect(previousPageStart(10)).toBe(5);
    expect(previousPageStart(5)).toBe(0);
  });

  it("stops at the first page instead of wrapping", () => {
    expect(previousPageStart(0)).toBe(0);
  });

  it("keeps whole pages when the count divides evenly", () => {
    expect(maxPageStart(40)).toBe(35);
    expect(nextPageStart(30, 40)).toBe(35);
    expect(nextPageStart(35, 40)).toBe(35);
  });

  it("advances by a full page instead of overlapping near the end", () => {
    // 11 frames must page 0 -> 5 -> 10, not 0 -> 5 -> 6.
    expect(maxPageStart(11)).toBe(10);
    expect(nextPageStart(0, 11)).toBe(5);
    expect(nextPageStart(5, 11)).toBe(10);
    expect(nextPageStart(10, 11)).toBe(10);
  });

  it("treats a list shorter than one page as a single page", () => {
    expect(maxPageStart(3)).toBe(0);
    expect(nextPageStart(0, 3)).toBe(0);
    expect(previousPageStart(0)).toBe(0);
  });

  it("clamps a page start into range", () => {
    expect(clampPageStart(-5, 40)).toBe(0);
    expect(clampPageStart(999, 40)).toBe(35);
    expect(clampPageStart(3, 0)).toBe(0);
  });
});

describe("pageBounds", () => {
  it("slices a full page", () => {
    expect(pageBounds(0, 40)).toEqual({ start: 0, end: 5, count: 5 });
    expect(pageBounds(10, 40)).toEqual({ start: 10, end: 15, count: 5 });
  });

  it("returns a short final page without padding or duplicating", () => {
    // 13 frames: starts 0, 5, 10 — the last page holds the 3 that remain.
    expect(pageBounds(10, 13)).toEqual({ start: 10, end: 13, count: 3 });
    expect(pageBounds(10, 11)).toEqual({ start: 10, end: 11, count: 1 });
  });

  it("never overlaps the page before it", () => {
    for (let total = 6; total <= 30; total++) {
      const starts: number[] = [];
      for (let s = 0; s <= maxPageStart(total); s = nextPageStart(s, total)) {
        if (starts.includes(s)) break;
        starts.push(s);
      }
      for (let i = 1; i < starts.length; i++) {
        expect(starts[i] - starts[i - 1]).toBe(KEYFRAME_PAGE_SIZE);
      }
    }
  });

  it("reports fewer frames than a page when the list runs out", () => {
    expect(pageBounds(0, 3)).toEqual({ start: 0, end: 3, count: 3 });
    expect(pageBounds(0, 0)).toEqual({ start: 0, end: 0, count: 0 });
  });
});

describe("offsetInPage", () => {
  it("locates the selected frame inside the page", () => {
    expect(offsetInPage(5, 7)).toBe(2);
    expect(offsetInPage(0, 0)).toBe(0);
  });

  it("reports -1 when the selected frame is on another page", () => {
    expect(offsetInPage(5, 2)).toBe(-1);
    expect(offsetInPage(5, 10)).toBe(-1);
  });
});

describe("pageStartForIndex", () => {
  it("centres the page on a frame", () => {
    expect(pageStartForIndex(12, 40)).toBe(10);
  });

  it("clamps at both ends of the list", () => {
    expect(pageStartForIndex(0, 40)).toBe(0);
    expect(pageStartForIndex(39, 40)).toBe(35);
  });
});

describe("hasFramesAfterWindow", () => {
  it("reports more frames when the window was not clamped at the end", () => {
    // Centre at offset 5 of 11 with range 5: five frames follow, so the
    // backend did not clamp and later pages exist.
    expect(hasFramesAfterWindow(frames(11), 5, 5)).toBe(true);
  });

  it("reports no more frames when the window was clamped at the end", () => {
    // Centre near the end: only three frames follow, fewer than the range.
    const window = frames(9, 0);
    expect(hasFramesAfterWindow(window, 5, 5)).toBe(false);
  });

  it("handles an empty window and a missing centre", () => {
    expect(hasFramesAfterWindow([], 5, 5)).toBe(false);
    expect(hasFramesAfterWindow(frames(11), 999, 5)).toBe(true);
  });
});

describe("KEYFRAME_PAGE_SIZE", () => {
  it("stays at the strip width the viewer already had", () => {
    expect(KEYFRAME_PAGE_SIZE).toBe(5);
  });
});

describe("resolveNextPage", () => {
  const window11 = frames(11);

  it("moves a page without asking the backend when the window allows it", () => {
    expect(resolveNextPage(0, window11, true)).toEqual({ pageStart: 5, fetchAfter: null });
    expect(resolveNextPage(5, window11, true)).toEqual({ pageStart: 10, fetchAfter: null });
  });

  it("stops at the end of the video without fetching", () => {
    // Last page of the window and the video has nothing after it.
    expect(resolveNextPage(10, window11, false)).toEqual({ pageStart: null, fetchAfter: null });
  });

  it("asks for a window past the last frame it holds when more video remains", () => {
    const decision = resolveNextPage(10, window11, true);
    expect(decision.pageStart).toBeNull();
    expect(decision.fetchAfter).toBe(10);
  });

  it("does nothing on an empty window", () => {
    expect(resolveNextPage(0, [], true)).toEqual({ pageStart: null, fetchAfter: null });
  });
});

describe("pageStartAfterFetch", () => {
  it("continues just past the frame a page action left behind", () => {
    // New window 6..16, user paged away from frame 10.
    expect(pageStartAfterFetch(frames(11, 6), 6, 10)).toBe(5);
  });

  it("re-centres on the fetched frame for an ordinary fetch", () => {
    expect(pageStartAfterFetch(frames(11, 0), 5)).toBe(3);
  });

  it("re-centres when the paged frame is missing from the new window", () => {
    expect(pageStartAfterFetch(frames(11, 0), 5, 999)).toBe(3);
  });

  it("clamps the continue position to a whole page at the end", () => {
    // Paging away from the very last frame leaves one short page.
    expect(pageStartAfterFetch(frames(6, 100), 105, 105)).toBe(5);
  });
});
