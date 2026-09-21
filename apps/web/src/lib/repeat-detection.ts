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

/** Cache key for a nested repeat lookup that omits its source frame. */
export function nestedRepeatRequestKey(
  frame: { video_id: string; frame_index: number },
  excludedSource: { video_id: string; frame_index: number },
): string {
  return `${frameRepeatKey(frame)}!${frameRepeatKey(excludedSource)}`;
}

export interface RepeatHoverItem {
  key: string;
  videoId: string;
  frameIndex: number;
  label: string;
  identity: string;
  cosine: number;
  thumbnailUrl: string;
}

export type RepeatHoverPlacement = "left" | "right";

export interface RepeatPopoverPosition {
  left: number;
  top: number;
}

export const SIGLIP2_DUPLICATE_COSINE_LABEL = "SigLIP2 duplicate cosine";

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

/** Keep a portalled evidence card in the current viewport. */
export function repeatPopoverPosition(
  rect: Pick<DOMRect, "top" | "left" | "right">,
  viewport: { width: number; height: number },
  popoverHeight: number,
  cardWidth = 224,
  gap = 12,
  margin = 8,
): RepeatPopoverPosition {
  const placement = repeatHoverPlacement(rect, viewport.width, cardWidth, gap);
  const requestedLeft = placement === "right" ? rect.right + gap : rect.left - cardWidth - gap;
  return {
    left: Math.min(Math.max(requestedLeft, margin), Math.max(margin, viewport.width - cardWidth - margin)),
    top: Math.min(Math.max(rect.top, margin), Math.max(margin, viewport.height - popoverHeight - margin)),
  };
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
      videoId: highest.video_id,
      frameIndex: highest.frame_index,
      label: "IN-video Highest + Furthest",
      identity: `frame_index ${highest.frame_index}`,
      cosine: highest.cosine,
      thumbnailUrl: thumbnailUrl(highest),
    });
  } else {
    if (highest) {
      items.push({
        key: `in-highest:${frameRepeatKey(highest)}`,
        videoId: highest.video_id,
        frameIndex: highest.frame_index,
        label: "IN-video Highest",
        identity: `frame_index ${highest.frame_index}`,
        cosine: highest.cosine,
        thumbnailUrl: thumbnailUrl(highest),
      });
    }
    if (furthest) {
      items.push({
        key: `in-furthest:${frameRepeatKey(furthest)}`,
        videoId: furthest.video_id,
        frameIndex: furthest.frame_index,
        label: "IN-video Furthest",
        identity: `frame_index ${furthest.frame_index}`,
        cosine: furthest.cosine,
        thumbnailUrl: thumbnailUrl(furthest),
      });
    }
  }
  const outside = details.out_video_highest_duplicate;
  if (outside) {
    items.push({
      key: `out:${frameRepeatKey(outside)}`,
      videoId: outside.video_id,
      frameIndex: outside.frame_index,
      label: "OUT-video Highest",
      identity: `${outside.video_id} / frame_index ${outside.frame_index}`,
      cosine: outside.cosine,
      thumbnailUrl: thumbnailUrl(outside),
    });
  }
  return items;
}
import type { RepeatFrameDetails, RepeatFrameReference } from "./api";
