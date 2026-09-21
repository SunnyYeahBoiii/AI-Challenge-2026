export interface InfinitePaginationInput {
  armed: boolean;
  isIntersecting: boolean;
}

export interface InfinitePaginationState {
  armed: boolean;
  shouldLoad: boolean;
}

/** A sentinel must leave its prefetch area before it can request another page. */
export function nextInfinitePaginationState({
  armed,
  isIntersecting,
}: InfinitePaginationInput): InfinitePaginationState {
  if (!isIntersecting) return { armed: true, shouldLoad: false };
  if (!armed) return { armed: false, shouldLoad: false };
  return { armed: false, shouldLoad: true };
}
