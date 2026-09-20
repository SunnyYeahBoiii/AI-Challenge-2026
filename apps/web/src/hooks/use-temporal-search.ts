"use client";

import { useCallback, useRef, useState } from "react";

import type { SearchFilter } from "@/components/filter-panel";
import {
  emptySearchResult,
  videoFramesResponse,
} from "@/lib/temporal-response";
import {
  multiBoxSearch,
  searchVideoFrames,
  type TemporalSearchResponse,
} from "@/lib/api";

/** Temporal search state and the (race-guarded) search/clear actions. */
export function useTemporalSearch() {
  const [searchResult, setSearchResult] = useState<TemporalSearchResponse>(
    emptySearchResult(),
  );
  const [queryCount, setQueryCount] = useState(0);
  const [hasSearched, setHasSearched] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const searchIdRef = useRef(0);

  const handleSearch = useCallback(async (filter: SearchFilter) => {
    const currentSearchId = ++searchIdRef.current;
    setIsLoading(true);
    setSearchError(null);
    setHasSearched(true);
    try {
      if (filter.videoId) {
        const data = await searchVideoFrames(filter.videoId);
        if (currentSearchId !== searchIdRef.current) return;
        setSearchResult(videoFramesResponse(data.results, filter.mode));
        setQueryCount(1);
      } else {
        const enabledQueries = filter.queries.filter(
          (q) => q.enabled && Boolean(
            q.content.trim() || q.tags?.length || q.keywords?.length
          )
        );
        const boxQueries = enabledQueries.map((q) => ({
          text: q.type === "text" ? q.content : undefined,
          image: q.type === "image" ? q.content : undefined,
          tags: q.tags?.length ? q.tags : undefined,
          tag_match_mode: q.tags?.length ? (q.tagMatchMode ?? "and") : undefined,
          keywords: q.keywords?.length ? q.keywords : undefined,
          ocr_match_mode: q.keywords?.length ? (q.ocrMatchMode ?? "and") : undefined,
          asr_match_mode: q.keywords?.length ? (q.asrMatchMode ?? "and") : undefined,
          ocr_search_mode: q.keywords?.length ? (q.ocrSearchMode ?? "exact") : undefined,
          asr_search_mode: q.keywords?.length ? (q.asrSearchMode ?? "exact") : undefined,
          keyword_field_mode: q.keywords?.length ? (q.keywordFieldMode ?? "or") : undefined,
          topk: q.topK ?? 1500,
          enhance: q.enhance ?? false,
        }));
        const data = await multiBoxSearch({
          box_queries: boxQueries,
          mode: filter.mode,
          temporal_window_seconds: filter.temporalWindowSeconds,
        });
        if (currentSearchId !== searchIdRef.current) return;
        setSearchResult(data);
        setQueryCount(enabledQueries.length);
      }
    } catch (error) {
      if (currentSearchId !== searchIdRef.current) return;
      console.error("Search failed:", error);
      setSearchError(
        error instanceof Error
          ? error.message
          : "Search failed. Check the API connection and try again.",
      );
      setSearchResult(emptySearchResult(filter.mode));
      setQueryCount(0);
    } finally {
      if (currentSearchId === searchIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [setHasSearched, setQueryCount, setSearchResult]);

  const clearSearch = useCallback(() => {
    searchIdRef.current += 1;
    setSearchResult(emptySearchResult());
    setQueryCount(0);
    setSearchError(null);
    setHasSearched(false);
    setIsLoading(false);
  }, [setHasSearched, setQueryCount, setSearchResult]);

  return {
    searchResult,
    queryCount,
    hasSearched,
    isLoading,
    searchError,
    setSearchError,
    handleSearch,
    clearSearch,
  };
}
