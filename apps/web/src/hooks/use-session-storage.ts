"use client";

import { useEffect, useState } from "react";

/**
 * useState mirrored into sessionStorage under `key`.
 *
 * Hydrates after mount (never during render, so SSR stays safe) and only
 * persists once hydration has settled — the initial value is never written
 * over a stored one.
 */
export function useSessionStorageState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(initial);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const stored = sessionStorage.getItem(key);
    if (stored !== null) {
      try {
        setValue(JSON.parse(stored) as T);
      } catch {
        // Corrupted entry — fall back to the initial value.
      }
    }
    setHydrated(true);
  }, [key]);

  useEffect(() => {
    if (!hydrated) return;
    sessionStorage.setItem(key, JSON.stringify(value));
  }, [hydrated, key, value]);

  return [value, setValue] as const;
}
