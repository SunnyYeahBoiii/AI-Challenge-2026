"use client";

import { useCallback, useRef, useState } from "react";

import type { SearchFilter } from "@/components/filter-panel";
import type { KeywordSearchConfig } from "@/components/keyword-search-options";
import {
  emptySearchResult,
  videoFramesResponse,
} from "@/lib/temporal-response";
import {
  multiBoxSearch,
  searchVideoFrames,
  type TemporalSearchResponse,
} from "@/lib/api";

function toApiKeywordSearchConfig(config: KeywordSearchConfig) {
  return {
    query_type: config.queryType,
    fuzzy: config.fuzzy,
    operator: config.operator,
    minimum_should_match: config.minimumShouldMatch,
    prefix_length: config.prefixLength,
    max_expansions: config.maxExpansions,
    slop: config.slop,
  };
}

/** Temporal search state and the (race-guarded) search/clear actions. */
export function useTemporalSearch() {
  const [searchResult, setSearchResult] = useState<TemporalSearchResponse>(
    emptySearchResult(),
  );
  const [queryCount, setQueryCount] = useState(0);
  const [isVideoBrowse, setIsVideoBrowse] = useState(false);
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
        setIsVideoBrowse(true);
      } else {
        const enabledQueries = filter.queries.filter(
          (q) => q.enabled && Boolean(
            q.content.trim() || q.tags?.length || q.ocrKeywords?.length || q.asrKeywords?.length
          )
        );
        const boxQueries = enabledQueries.map((q) => ({
          text: q.type === "text" ? q.content : undefined,
          image: q.type === "image" ? q.content : undefined,
          tags: q.tags?.length ? q.tags : undefined,
          tag_match_mode: q.tags?.length ? (q.tagMatchMode ?? "and") : undefined,
          ocr_keywords: q.ocrKeywords?.length ? q.ocrKeywords : undefined,
          asr_keywords: q.asrKeywords?.length ? q.asrKeywords : undefined,
          ocr_match_mode: q.ocrKeywords?.length ? (q.ocrMatchMode ?? "and") : undefined,
          asr_match_mode: q.asrKeywords?.length ? (q.asrMatchMode ?? "and") : undefined,
          ocr_search_config: q.ocrKeywords?.length
            ? toApiKeywordSearchConfig(filter.ocrSearchConfig)
            : undefined,
          asr_search_config: q.asrKeywords?.length
            ? toApiKeywordSearchConfig(filter.asrSearchConfig)
            : undefined,
          topk: q.topK ?? 1000,
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
        setIsVideoBrowse(false);
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
      setIsVideoBrowse(false);
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
    setIsVideoBrowse(false);
    setSearchError(null);
    setHasSearched(false);
    setIsLoading(false);
  }, [setHasSearched, setQueryCount, setSearchResult]);

  return {
    searchResult,
    queryCount,
    isVideoBrowse,
    hasSearched,
    isLoading,
    searchError,
    setSearchError,
    handleSearch,
    clearSearch,
  };
}
