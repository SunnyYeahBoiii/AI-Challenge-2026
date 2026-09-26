// Canonical parsing of FrameSeeker video identifiers.
//
// Level length varies: L21/M01/S01 are three characters, N001 is four. Slicing
// with slice(0, 3) truncated every N-series id to a level that does not exist on
// disk, so keyframe URLs 404'd for the whole N series.
const LEVEL_PATTERN = /^[A-Za-z]\d+/;

/** Return the level directory that owns `videoId` (e.g. `L21`, `N001`). */
export function levelOf(videoId: string): string {
  return LEVEL_PATTERN.exec(videoId)?.[0] ?? "";
}
