"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { DragStartEvent, DragEndEvent, Modifier } from "@dnd-kit/core";
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy, arrayMove } from "@dnd-kit/sortable";
import { Icon } from "./icon";
import { QueryBox, QueryBoxStatic, type BoxQuery, type KeywordFocusRequest } from "./query-box";
import type { KeywordSearchConfig } from "./keyword-search-options";
import { listVideos } from "@/lib/api";
import type { VideoResult } from "@/lib/api";

export interface SearchFilter {
  videoId?: string;
  queries: BoxQuery[];
  mode: "parallel" | "sequential";
  temporalWindowSeconds: number;
  ocrSearchConfig: KeywordSearchConfig;
  asrSearchConfig: KeywordSearchConfig;
}

interface FilterPanelProps {
  onSearch: (filter: SearchFilter) => void;
  onClear: () => void;
  onValidationError: (message: string) => void;
  isLoading?: boolean;
  temporalWindowSeconds: number;
  ocrSearchConfig: KeywordSearchConfig;
  asrSearchConfig: KeywordSearchConfig;
  gridCols?: number;
  onGridColsChange?: (cols: number) => void;
}

export function FilterPanel({
  onSearch,
  onClear,
  onValidationError,
  isLoading,
  temporalWindowSeconds,
  ocrSearchConfig,
  asrSearchConfig,
  gridCols = 6,
  onGridColsChange,
}: FilterPanelProps) {
  const [videoId, setVideoId] = useState("");
  const [queries, setQueries] = useState<BoxQuery[]>([
    { id: "1", type: "text", content: "", enabled: true, topK: 1000, enhance: false },
  ]);
  const [mode, setMode] = useState<"parallel" | "sequential">("parallel");
  const [suggestions, setSuggestions] = useState<VideoResult[]>([]);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(0);
  const [searchingVideos, setSearchingVideos] = useState(false);
  const videoInputRef = useRef<HTMLInputElement>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [dndReady, setDndReady] = useState(false);
  const isDraggingRef = useRef(false);
  const [activeQueryId, setActiveQueryId] = useState("1");
  const keywordFocusTokenRef = useRef(0);
  const [keywordFocusRequest, setKeywordFocusRequest] = useState<KeywordFocusRequest | null>(null);

  useEffect(() => {
    setDndReady(true);
  }, []);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  const restrictToVerticalAxis: Modifier = ({ transform }) => ({
    ...transform,
    x: 0,
  });

  const handleDragStart = useCallback(() => {
    isDraggingRef.current = true;
  }, []);

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    isDraggingRef.current = false;
    const { active, over } = event;
    if (over && active.id !== over.id) {
      setQueries((prev) => {
        const oldIndex = prev.findIndex((q) => q.id === active.id);
        const newIndex = prev.findIndex((q) => q.id === over.id);
        return arrayMove(prev, oldIndex, newIndex);
      });
    }
  }, []);

  useEffect(() => {
    const preventHorizontalScroll = (e: WheelEvent) => {
      if (isDraggingRef.current && Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        e.preventDefault();
      }
    };
    const preventTouchScroll = (e: TouchEvent) => {
      if (isDraggingRef.current) e.preventDefault();
    };
    document.addEventListener("wheel", preventHorizontalScroll, { passive: false, capture: true });
    document.addEventListener("touchmove", preventTouchScroll, { passive: false, capture: true });
    return () => {
      document.removeEventListener("wheel", preventHorizontalScroll, { capture: true } as EventListenerOptions);
      document.removeEventListener("touchmove", preventTouchScroll, { capture: true } as EventListenerOptions);
    };
  }, []);

  const isSearchable = (q: BoxQuery) => Boolean(
    q.enabled && (
      q.content.trim() ||
      q.tags?.length ||
      q.ocrKeywords?.length ||
      q.asrKeywords?.length
    )
  );

  const canSearch = videoId.trim().length > 0 || queries.some(isSearchable);

  const handleSearch = useCallback(() => {
    if (videoId.trim()) {
      onSearch({
        videoId: videoId.trim(),
        queries: [],
        mode,
        temporalWindowSeconds,
        ocrSearchConfig,
        asrSearchConfig,
      });
      return;
    }
    const enabledQueries = queries.filter(isSearchable);
    if (enabledQueries.length > 0) {
      onSearch({
        queries: enabledQueries,
        mode,
        temporalWindowSeconds,
        ocrSearchConfig,
        asrSearchConfig,
      });
    } else {
      onValidationError("Enter a Video ID or at least one enabled query with content");
    }
  }, [
    videoId,
    queries,
    mode,
    temporalWindowSeconds,
    ocrSearchConfig,
    asrSearchConfig,
    onSearch,
    onValidationError,
  ]);

  // Ctrl+Enter / Cmd+Enter triggers search from anywhere on the page.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        if (!isLoading) {
          handleSearch();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isLoading, handleSearch]);

  useEffect(() => {
    if (videoId.trim().length < 2) {
      setSuggestions([]);
      setActiveSuggestionIndex(0);
      setShowSuggestions(false);
      return;
    }
    const timer = setTimeout(async () => {
      setSearchingVideos(true);
      try {
        const data = await listVideos({ q: videoId.trim(), size: 10 });
        const unique = data.videos.filter(
          (v, i, arr) => arr.findIndex((x) => x.video_id === v.video_id) === i
        );
        setSuggestions(unique);
        setActiveSuggestionIndex(0);
        setShowSuggestions(unique.length > 0);
      } catch {
        setSuggestions([]);
      } finally {
        setSearchingVideos(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [videoId]);

  const selectVideo = (video: VideoResult) => {
    setVideoId(video.video_id);
    setShowSuggestions(false);
    setSuggestions([]);
    onSearch({
      videoId: video.video_id,
      queries: [],
      mode,
      temporalWindowSeconds,
      ocrSearchConfig,
      asrSearchConfig,
    });
  };

  const addQuery = () => {
    const id = Date.now().toString();
    setQueries((prev) => [
      ...prev,
      { id, type: "text", content: "", enabled: true, topK: 1000, enhance: false },
    ]);
    setActiveQueryId(id);
    requestAnimationFrame(() => document.getElementById(`query-text-${id}`)?.focus());
  };

  useEffect(() => {
    document.getElementById("query-text-1")?.focus();
  }, []);

  const updateQuery = (id: string, updates: Partial<BoxQuery>) => {
    setQueries((prev) => prev.map((q) => (q.id === id ? { ...q, ...updates } : q)));
  };

  const removeQuery = (id: string) => {
    setQueries((prev) => {
      const next = prev.filter((q) => q.id !== id);
      if (activeQueryId === id) setActiveQueryId(next[0]?.id ?? "");
      return next;
    });
  };

  const handleClear = useCallback(() => {
    setVideoId("");
    setQueries([{ id: "1", type: "text", content: "", enabled: true, topK: 1000, enhance: false }]);
    setActiveQueryId("1");
    setMode("parallel");
  }, []);

  const focusQuery = useCallback((id: string) => {
    setActiveQueryId(id);
    document.getElementById(`query-text-${id}`)?.focus();
  }, []);

  const focusKeyword = useCallback((source: KeywordFocusRequest["source"]) => {
    const queryId = activeQueryId || queries[0]?.id;
    if (!queryId) return;
    setActiveQueryId(queryId);
    keywordFocusTokenRef.current += 1;
    setKeywordFocusRequest({
      queryId,
      source,
      token: keywordFocusTokenRef.current,
    });
  }, [activeQueryId, queries]);

  const reorderActiveQuery = useCallback((direction: -1 | 1) => {
    setQueries((prev) => {
      const index = prev.findIndex((query) => query.id === activeQueryId);
      const nextIndex = Math.min(Math.max(index + direction, 0), prev.length - 1);
      if (index < 0 || index === nextIndex) return prev;
      return arrayMove(prev, index, nextIndex);
    });
  }, [activeQueryId]);

  useEffect(() => {
    const isEditableTarget = (target: EventTarget | null) =>
      target instanceof HTMLElement &&
      (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

    const onKeyDown = (event: KeyboardEvent) => {
      if (!event.altKey || event.ctrlKey || event.shiftKey || event.metaKey) return;
      if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;
      const isInFilterPanel = event.target instanceof Element && Boolean(event.target.closest("[data-filter-panel]"));

      if (event.key.toLowerCase() === "v") {
        event.preventDefault();
        videoInputRef.current?.focus();
        return;
      }
      if (event.key.toLowerCase() === "q") {
        event.preventDefault();
        focusQuery(activeQueryId || queries[0]?.id || "");
        return;
      }
      if (/^[1-9]$/.test(event.key)) {
        const query = queries[Number(event.key) - 1];
        if (!query) return;
        event.preventDefault();
        focusQuery(query.id);
        return;
      }
      if (event.key.toLowerCase() === "o" || event.key.toLowerCase() === "s") {
        event.preventDefault();
        focusKeyword(event.key.toLowerCase() === "o" ? "ocr" : "asr");
        return;
      }
      if (event.key.toLowerCase() === "n") {
        event.preventDefault();
        addQuery();
        return;
      }
      if (event.key.toLowerCase() === "e") {
        const activeQuery = queries.find((query) => query.id === activeQueryId);
        if (!activeQuery) return;
        event.preventDefault();
        updateQuery(activeQuery.id, { enhance: !(activeQuery.enhance ?? false) });
        return;
      }
      if (isEditableTarget(event.target) && event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
      if (event.key === "ArrowUp" && isInFilterPanel) {
        event.preventDefault();
        reorderActiveQuery(-1);
        return;
      }
      if (event.key === "ArrowDown" && isInFilterPanel) {
        event.preventDefault();
        reorderActiveQuery(1);
        return;
      }
      if (event.key === "[" || event.key === "{") {
        event.preventDefault();
        onGridColsChange?.(Math.max(2, gridCols - 1));
        return;
      }
      if (event.key === "]" || event.key === "}") {
        event.preventDefault();
        onGridColsChange?.(Math.min(12, gridCols + 1));
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [activeQueryId, addQuery, focusKeyword, focusQuery, gridCols, onGridColsChange, queries, reorderActiveQuery]);

  return (
    <aside data-filter-panel className="bg-surface-container-low border-r border-outline-variant flex flex-col h-screen w-sidebar-width flex-shrink-0 z-10 overflow-hidden">
      {/* Top Section */}
      <div className="p-container-padding pb-2 border-b border-outline-variant">
        {/* Video ID Search */}
        <div className="mb-4 relative">
          <label className="text-label-md text-on-surface-variant flex items-center gap-1 mb-1">
            <Icon name="movie" size={16} /> Video ID Search
          </label>
          <input
            ref={videoInputRef}
            className="w-full bg-surface-container-lowest border-b border-outline-variant focus:border-primary bg-transparent px-0 py-1.5 text-body-sm outline-none transition-colors placeholder:text-outline"
            placeholder="Type to search videos..."
            value={videoId}
            onChange={(e) => setVideoId(e.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown" && suggestions.length > 0) {
                event.preventDefault();
                setActiveSuggestionIndex((index) => Math.min(index + 1, suggestions.length - 1));
                return;
              }
              if (event.key === "ArrowUp" && suggestions.length > 0) {
                event.preventDefault();
                setActiveSuggestionIndex((index) => Math.max(index - 1, 0));
                return;
              }
              if (event.key === "Escape") {
                setShowSuggestions(false);
                return;
              }
              if (event.key === "Enter" && suggestions.length > 0) {
                event.preventDefault();
                selectVideo(suggestions[activeSuggestionIndex] ?? suggestions[0]);
              }
            }}
            onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
          />
          {/* Autocomplete dropdown */}
          {showSuggestions && (
            <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-surface-container-lowest border border-outline-variant rounded-lg shadow-lg max-h-60 overflow-y-auto">
              {suggestions.map((v, index) => (
                <button
                  key={v.video_id}
                  className={`w-full text-left px-3 py-2 border-b border-outline-variant last:border-b-0 transition-colors flex flex-col gap-0.5 ${
                    index === activeSuggestionIndex ? "bg-primary-container/40" : "hover:bg-surface-container-high"
                  }`}
                  onClick={() => selectVideo(v)}
                >
                  <span className="text-label-sm text-on-surface">{v.video_id}</span>
                  <span className="text-body-xs text-on-surface-variant truncate">{v.title || v.description}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Temporal Search */}
        <div className="mb-4">
          <label className="text-label-md text-on-surface-variant flex items-center gap-1 mb-2">
            <Icon name="timeline" size={16} /> Temporal Search
          </label>
          <div className="flex justify-between items-center mb-2">
            <span className="text-label-sm text-on-surface-variant">Query Mode</span>
            <div className="flex bg-surface-container-lowest border border-outline-variant rounded overflow-hidden">
              <button
                onClick={() => setMode("parallel")}
                title="Retrieve boxes independently in parallel, then retain frames on complete ordered paths"
                className={`px-2 py-1 text-label-xs transition-colors ${
                  mode === "parallel"
                    ? "bg-primary text-on-primary"
                    : "hover:bg-surface-container-high text-on-surface-variant"
                }`}
              >
                Parallel
              </button>
              <button
                onClick={() => setMode("sequential")}
                title="Retrieve each later box only inside videos with a reachable result from the previous box"
                className={`px-2 py-1 text-label-xs transition-colors ${
                  mode === "sequential"
                    ? "bg-primary text-on-primary"
                    : "hover:bg-surface-container-high text-on-surface-variant"
                }`}
              >
                Sequential
              </button>
            </div>
          </div>
        </div>

      </div>

      {/* Queries List */}
      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar p-stack-gap flex flex-col gap-stack-gap bg-surface-container-low">
        <div className="flex justify-between items-center px-1 shrink-0">
          <h3 className="text-label-md text-on-surface">Queries</h3>
          <div className="flex items-center gap-1">
            <button
              onClick={handleClear}
              aria-label="Clear queries"
              title="Clear queries"
              className="text-on-surface-variant hover:text-error transition-colors"
            >
              <Icon name="delete" size={18} />
            </button>
            <button
              onClick={addQuery}
              aria-label="Add query"
              className="text-on-surface-variant hover:text-primary transition-colors"
            >
              <Icon name="add" size={18} />
            </button>
          </div>
        </div>
        {dndReady ? (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            modifiers={[restrictToVerticalAxis]}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={queries.map((q) => q.id)} strategy={verticalListSortingStrategy}>
              <div className="flex flex-col gap-stack-gap">
                {queries.map((query, index) => (
                  <QueryBox
                    key={query.id}
                    query={query}
                    index={index}
                    onUpdate={(updates) => updateQuery(query.id, updates)}
                    onRemove={() => removeQuery(query.id)}
                    canRemove={queries.length > 1}
                    onFocus={() => setActiveQueryId(query.id)}
                    keywordFocusRequest={keywordFocusRequest}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        ) : (
          <div className="flex flex-col gap-stack-gap">
            {queries.map((query, index) => (
              <QueryBoxStatic
                key={query.id}
                query={query}
                index={index}
                onUpdate={(updates) => updateQuery(query.id, updates)}
                onRemove={() => removeQuery(query.id)}
                canRemove={queries.length > 1}
                onFocus={() => setActiveQueryId(query.id)}
                keywordFocusRequest={keywordFocusRequest}
              />
            ))}
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="p-4 border-t border-outline-variant bg-surface-container-lowest flex gap-2">
        <button
          onClick={onClear}
          className="flex-1 bg-surface-container hover:bg-surface-variant border border-outline-variant text-on-surface text-label-md py-2 rounded transition-colors"
        >
          Clear
        </button>
        <button
          onClick={handleSearch}
          disabled={isLoading || !canSearch}
          title="Search (Ctrl+Enter)"
          className="flex-1 bg-primary-container hover:bg-primary-fixed text-on-primary-container text-label-md py-2 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1.5"
        >
          <Icon name="search" size={16} />
          {isLoading ? "Searching..." : "Search"}
        </button>
      </div>
    </aside>
  );
}
