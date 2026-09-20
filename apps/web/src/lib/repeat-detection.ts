/** Stable identity for a frame in repeat-detection results and caches. */
export function frameRepeatKey(frame: {
  video_id: string;
  frame_index: number;
}): string {
  return `${frame.video_id}:${frame.frame_index}`;
}

/** Order-independent, deduplicated cache key for one exact repeat batch. */
export function canonicalRepeatRequestKey(
  frames: Array<{ video_id: string; frame_index: number; timestamp: number }>,
): string {
  const timestampsByFrame = new Map<string, number>();
  for (const frame of frames) {
    timestampsByFrame.set(frameRepeatKey(frame), frame.timestamp);
  }
  return [...timestampsByFrame.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, timestamp]) => `${key}@${timestamp}`)
    .join("|");
}

export interface RepeatHoverItem {
  key: string;
  label: string;
  identity: string;
  thumbnailUrl: string;
}

export type RepeatHoverPlacement = "left" | "right";

/** Choose the roomier side of a hovered result card for its repeat evidence. */
export function repeatHoverPlacement(
  rect: Pick<DOMRect, "left" | "right">,
  viewportWidth: number,
  cardWidth = 224,
  gap = 12,
): RepeatHoverPlacement {
  const roomOnRight = viewportWidth - rect.right;
  const roomOnLeft = rect.left;
  if (roomOnRight >= cardWidth + gap || roomOnRight >= roomOnLeft) return "right";
  return "left";
}

function sameFrame(left: RepeatFrameReference, right: RepeatFrameReference): boolean {
  return left.video_id === right.video_id && left.frame_index === right.frame_index;
}

function thumbnailUrl(reference: RepeatFrameReference): string {
  return `/api/keyframes/${reference.video_id}/${reference.frame_index}`;
}

/**
 * Produce at most three display tiles from the API witnesses. The API preserves
 * both in-video choices so that the UI can merge their labels when they match.
 */
export function repeatHoverItems(details: RepeatFrameDetails): RepeatHoverItem[] {
  const highest = details.in_video_highest_duplicate;
  const furthest = details.in_video_furthest_duplicate;
  const items: RepeatHoverItem[] = [];
  if (highest && furthest && sameFrame(highest, furthest)) {
    items.push({
      key: `in:${frameRepeatKey(highest)}`,
      label: "IN-video Highest + Furthest",
      identity: `frame_index ${highest.frame_index}`,
      thumbnailUrl: thumbnailUrl(highest),
    });
  } else {
    if (highest) {
      items.push({
        key: `in-highest:${frameRepeatKey(highest)}`,
        label: "IN-video Highest",
        identity: `frame_index ${highest.frame_index}`,
        thumbnailUrl: thumbnailUrl(highest),
      });
    }
    if (furthest) {
      items.push({
        key: `in-furthest:${frameRepeatKey(furthest)}`,
        label: "IN-video Furthest",
        identity: `frame_index ${furthest.frame_index}`,
        thumbnailUrl: thumbnailUrl(furthest),
      });
    }
  }
  const outside = details.out_video_highest_duplicate;
  if (outside) {
    items.push({
      key: `out:${frameRepeatKey(outside)}`,
      label: "OUT-video Highest",
      identity: `${outside.video_id} / frame_index ${outside.frame_index}`,
      thumbnailUrl: thumbnailUrl(outside),
    });
  }
  return items;
}
import type { RepeatFrameDetails, RepeatFrameReference } from "./api";
