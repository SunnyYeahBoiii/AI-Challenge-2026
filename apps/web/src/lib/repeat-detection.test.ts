import { describe, expect, it } from "vitest";

import {
  canonicalRepeatRequestKey,
  frameRepeatKey,
  repeatHoverPlacement,
  repeatHoverItems,
} from "./repeat-detection";

describe("repeat detection client helpers", () => {
  it("uses stable frame identities for returned repeat keys", () => {
    expect(frameRepeatKey({ video_id: "L23_V001", frame_index: 42 })).toBe("L23_V001:42");
  });

  it("deduplicates and order-normalizes a repeat request cache key", () => {
    expect(
      canonicalRepeatRequestKey([
        { video_id: "V2", frame_index: 5, timestamp: 3.5 },
        { video_id: "V1", frame_index: 3, timestamp: 1.5 },
        { video_id: "V2", frame_index: 5, timestamp: 3.5 },
      ]),
    ).toBe("V1:3@1.5|V2:5@3.5");
  });

  it("renders separate in-video and out-video witnesses with local thumbnail URLs", () => {
    expect(repeatHoverItems({
      video_id: "L21_V015",
      frame_index: 6191,
      in_video_highest_duplicate: { video_id: "L21_V015", frame_index: 6200 },
      in_video_furthest_duplicate: { video_id: "L21_V015", frame_index: 7000 },
      out_video_highest_duplicate: { video_id: "L21_V026", frame_index: 5852 },
    })).toEqual([
      expect.objectContaining({
        label: "IN-video Highest",
        identity: "frame_index 6200",
        thumbnailUrl: "/api/keyframes/L21/L21_V015/6200.webp",
      }),
      expect.objectContaining({
        label: "IN-video Furthest",
        identity: "frame_index 7000",
        thumbnailUrl: "/api/keyframes/L21/L21_V015/7000.webp",
      }),
      expect.objectContaining({
        label: "OUT-video Highest",
        identity: "L21_V026 / frame_index 5852",
        thumbnailUrl: "/api/keyframes/L21/L21_V026/5852.webp",
      }),
    ]);
  });

  it("deduplicates one frame selected as both highest and furthest", () => {
    expect(repeatHoverItems({
      video_id: "L21_V015",
      frame_index: 6191,
      in_video_highest_duplicate: { video_id: "L21_V015", frame_index: 7000 },
      in_video_furthest_duplicate: { video_id: "L21_V015", frame_index: 7000 },
    })).toEqual([
      expect.objectContaining({
        label: "IN-video Highest + Furthest",
        identity: "frame_index 7000",
      }),
    ]);
  });

  it("keeps two tiles when a shared in-video witness also has an out-video witness", () => {
    const items = repeatHoverItems({
      video_id: "L21_V015",
      frame_index: 6191,
      in_video_highest_duplicate: { video_id: "L21_V015", frame_index: 7000 },
      in_video_furthest_duplicate: { video_id: "L21_V015", frame_index: 7000 },
      out_video_highest_duplicate: { video_id: "L21_V026", frame_index: 5852 },
    });

    expect(items).toHaveLength(2);
    expect(items.map((item) => item.label)).toEqual([
      "IN-video Highest + Furthest",
      "OUT-video Highest",
    ]);
  });

  it("opens repeat evidence on the side with sufficient viewport room", () => {
    expect(repeatHoverPlacement({ left: 100, right: 220 }, 1280)).toBe("right");
    expect(repeatHoverPlacement({ left: 1000, right: 1120 }, 1280)).toBe("left");
    expect(repeatHoverPlacement({ left: 120, right: 240 }, 360)).toBe("right");
  });
});
