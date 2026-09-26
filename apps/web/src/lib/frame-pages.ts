/**
 * Pagination over a video's keyframe strip.
 *
 * The strip shows a fixed page of frames at a time. Paging is a browsing
 * action only: it never changes the selected frame and never seeks the video.
 * Seeking stays the exclusive job of clicking a thumbnail.
 */

/** Frames visible at once — the existing strip width. */
export const KEYFRAME_PAGE_SIZE = 5;

/**
 * Highest page start reachable by stepping in whole pages.
 *
 * Deliberately `floor((total - 1) / pageSize) * pageSize` and not
 * `total - pageSize`: that would put the last start mid-page, so with 11
 * frames the starts would run 0, 5, 6 and the final page would overlap the
 * one before it. Rounding down to a whole page keeps every step exactly
 * `pageSize` wide and lets the last page be short instead of overlapping.
 */
export function maxPageStart(total: number, pageSize: number = KEYFRAME_PAGE_SIZE): number {
  if (total <= 1) return 0;
  return Math.floor((total - 1) / pageSize) * pageSize;
}

export function clampPageStart(
  start: number,
  total: number,
  pageSize: number = KEYFRAME_PAGE_SIZE,
): number {
  if (total <= 0) return 0;
  return Math.min(Math.max(0, start), maxPageStart(total, pageSize));
}

export function nextPageStart(
  current: number,
  total: number,
  pageSize: number = KEYFRAME_PAGE_SIZE,
): number {
  return clampPageStart(current + pageSize, total, pageSize);
}

export function previousPageStart(
  current: number,
  pageSize: number = KEYFRAME_PAGE_SIZE,
): number {
  return Math.max(0, current - pageSize);
}

export interface PageBounds {
  start: number;
  end: number;
  count: number;
}

/** The slice a page renders. A short final page is kept short, never padded. */
export function pageBounds(
  pageStart: number,
  total: number,
  pageSize: number = KEYFRAME_PAGE_SIZE,
): PageBounds {
  const start = clampPageStart(pageStart, total, pageSize);
  const end = Math.min(start + pageSize, total);
  return { start, end, count: Math.max(0, end - start) };
}

/**
 * Where the selected frame sits inside the visible page, or -1 when paging has
 * moved its thumbnail off-screen. The selection itself is unaffected.
 */
export function offsetInPage(
  pageStart: number,
  indexInList: number,
  pageSize: number = KEYFRAME_PAGE_SIZE,
): number {
  const offset = indexInList - pageStart;
  return offset >= 0 && offset < pageSize ? offset : -1;
}

/**
 * Page start that keeps `indexInList` visible, used when playback moves the
 * current frame off the page the user is looking at.
 */
export function pageStartForIndex(
  indexInList: number,
  total: number,
  pageSize: number = KEYFRAME_PAGE_SIZE,
): number {
  return clampPageStart(indexInList - Math.floor(pageSize / 2), total, pageSize);
}

/**
 * Whether the video has frames past the loaded window.
 *
 * The backend returns `frames[max(0, pos - range) .. pos + range]` and clamps
 * at both ends, so a window that came back with fewer than `range` frames
 * after its centre was clamped there and this is the last one. A full
 * half-window means the centre was not near the end, so more pages may exist.
 */
export function hasFramesAfterWindow(
  results: readonly { frame_index: number }[],
  centerFrameIndex: number,
  range: number,
): boolean {
  if (results.length === 0) return false;
  const pos = results.findIndex((f) => f.frame_index === centerFrameIndex);
  // Centre missing means the caller changed videos mid-flight; stay permissive.
  if (pos < 0) return true;
  return results.length - 1 - pos >= range;
}

export interface NextPageDecision {
  /** Page to show now, or null when a fetch has to happen first. */
  pageStart: number | null;
  /** Frame to request a fresh window around, or null. */
  fetchAfter: number | null;
}

/**
 * What a "next page" press should do.
 *
 * Usually it is a pure page move. Only on the last page of the loaded window
 * does it need the backend, and then it names the last frame it holds so the
 * new window can be aimed at the frames that follow it.
 */
export function resolveNextPage(
  pageStartIndex: number,
  frames: readonly { frame_index: number }[],
  hasFramesAfter: boolean,
  pageSize: number = KEYFRAME_PAGE_SIZE,
): NextPageDecision {
  const next = nextPageStart(pageStartIndex, frames.length, pageSize);
  if (next !== pageStartIndex) return { pageStart: next, fetchAfter: null };

  const tail = frames[frames.length - 1];
  if (!tail || !hasFramesAfter) return { pageStart: null, fetchAfter: null };
  return { pageStart: null, fetchAfter: tail.frame_index };
}

/**
 * Where the page lands once a window arrives.
 *
 * A paged fetch passes the frame the user paged away from in `pendingAfter`,
 * and continues just past it so the new page moves forward rather than
 * repeating. Any other fetch re-centres on its own frame, which is where the
 * pre-pagination centred strip already put it.
 */
export function pageStartAfterFetch(
  results: readonly { frame_index: number }[],
  fetchFrameIndex: number,
  pendingAfter: number | null = null,
  pageSize: number = KEYFRAME_PAGE_SIZE,
): number {
  if (pendingAfter !== null) {
    const after = results.findIndex((f) => f.frame_index === pendingAfter);
    if (after >= 0) return clampPageStart(after + 1, results.length, pageSize);
  }
  return pageStartForIndex(
    results.findIndex((f) => f.frame_index === fetchFrameIndex),
    results.length,
    pageSize,
  );
}
