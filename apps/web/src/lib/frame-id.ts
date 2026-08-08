// floor(timestamp * fps), unrounded -- matches BTC's frame_idx exactly (verified against 530k records).
export function computeFrameId(timestampSec: number, fps: number): number {
  const rawFrame = timestampSec * fps;
  return Math.floor(Number(rawFrame.toFixed(6)));
}
