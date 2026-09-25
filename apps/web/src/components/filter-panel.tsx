"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { DragStartEvent, DragEndEvent, Modifier } from "@dnd-kit/core";
import { DndContext, closestCenter, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy, arrayMove } from "@dnd-kit/sortable";
import { Icon } from "./icon";
import { QueryBox, QueryBoxStatic, type BoxQuery } from "./query-box";
import { listVideos } from "@/lib/api";
import type { VideoResult } from "@/lib/api";
import { VIDEO_CATEGORIES, prefixesForVideoCategory, type VideoCategoryId, type VideoPrefix } from "@/lib/video-categories";

export interface SearchFilter {
  videoId?: string;
  videoPrefixes: VideoPrefix[];
  queries: BoxQuery[];
  mode: "parallel" | "sequential";
  temporalWindowSeconds: number;
}

interface FilterPanelProps {
  onSearch: (filter: SearchFilter) => void;
  onClear: () => void;
  onValidationError: (message: string) => void;
  isLoading?: boolean;
  gridCols?: number;
  onGridColsChange?: (cols: number) => void;
}

function createDefaultQuery(id: string): BoxQuery {
  return {
    id,
    type: "text",
    content: "",
    enabled: true,
    topK: 1500,
    enhance: false,
    keywordFieldMode: "or",
    ocrMatchMode: "and",
    asrMatchMode: "and",
    ocrSearchMode: "exact",
    asrSearchMode: "exact",
  };
}

export function FilterPanel({
  onSearch,
  onClear,
  onValidationError,
  isLoading,
  gridCols = 6,
  onGridColsChange,
}: FilterPanelProps) {
  const [videoId, setVideoId] = useState("");
  const [videoCategory, setVideoCategory] = useState<VideoCategoryId | "">("");
  const [queriesVisible, setQueriesVisible] = useState(true);
  const [queries, setQueries] = useState<BoxQuery[]>([
    createDefaultQuery("1"),
  ]);
  const [mode, setMode] = useState<"parallel" | "sequential">("parallel");
  const [temporalWindowSeconds, setTemporalWindowSeconds] = useState(90);
  const [suggestions, setSuggestions] = useState<VideoResult[]>([]);
  const [searchingVideos, setSearchingVideos] = useState(false);
  const videoInputRef = useRef<HTMLInputElement>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [dndReady, setDndReady] = useState(false);
  const isDraggingRef = useRef(false);

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
      q.keywords?.length
    )
  );

  const canSearch = videoId.trim().length > 0 || queries.some(isSearchable);
  const videoPrefixes = prefixesForVideoCategory(videoCategory);

  const handleSearch = useCallback(() => {
    if (videoId.trim()) {
      onSearch({ videoId: videoId.trim(), videoPrefixes, queries: [], mode, temporalWindowSeconds });
      return;
    }
    const enabledQueries = queries.filter(isSearchable);
    if (enabledQueries.length > 0) {
      onSearch({ videoPrefixes, queries: enabledQueries, mode, temporalWindowSeconds });
    } else {
      onValidationError("Enter a Video ID or at least one enabled query with content");
    }
  }, [videoId, videoCategory, queries, mode, temporalWindowSeconds, onSearch, onValidationError]);

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
    onSearch({ videoId: video.video_id, videoPrefixes, queries: [], mode, temporalWindowSeconds });
  };

  const addQuery = () => {
    setQueriesVisible(true);
    setQueries((prev) => [
      ...prev,
      createDefaultQuery(Date.now().toString()),
    ]);
  };

  const updateQuery = (id: string, updates: Partial<BoxQuery>) => {
    setQueries((prev) => prev.map((q) => (q.id === id ? { ...q, ...updates } : q)));
  };

  const removeQuery = (id: string) => {
    setQueries((prev) => prev.filter((q) => q.id !== id));
  };

  const handleClear = useCallback(() => {
    setVideoId("");
    setVideoCategory("");
    setQueries([createDefaultQuery("1")]);
    setMode("parallel");
    setTemporalWindowSeconds(90);
  }, []);

  return (
    <aside className="bg-surface-container-low border-r border-outline-variant flex flex-col h-screen w-sidebar-width flex-shrink-0 z-10 overflow-hidden">
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
            onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
          />
          {/* Autocomplete dropdown */}
          {showSuggestions && (
            <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-surface-container-lowest border border-outline-variant rounded-lg shadow-lg max-h-60 overflow-y-auto">
              {suggestions.map((v) => (
                <button
                  key={v.video_id}
                  className="w-full text-left px-3 py-2 hover:bg-surface-container-high border-b border-outline-variant last:border-b-0 transition-colors flex flex-col gap-0.5"
                  onClick={() => selectVideo(v)}
                >
                  <span className="text-label-sm text-on-surface">{v.video_id}</span>
                  <span className="text-body-xs text-on-surface-variant truncate">{v.title || v.description}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="mb-4">
          <label htmlFor="video-category" className="text-label-md text-on-surface-variant flex items-center gap-1 mb-2">
            <Icon name="filter_list" size={16} /> Loại video
          </label>
          <select
            id="video-category"
            value={videoCategory}
            onChange={(event) => setVideoCategory(event.target.value as VideoCategoryId | "")}
            className="w-full rounded border border-outline-variant bg-surface-container-lowest px-2 py-2 text-body-sm text-on-surface outline-none focus:border-primary"
          >
            <option value="">Tất cả loại video</option>
            {VIDEO_CATEGORIES.map((category) => (
              <option key={category.id} value={category.id}>
                {category.label} ({category.description})
              </option>
            ))}
          </select>
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
          <div className="flex justify-between items-center gap-3">
            <label htmlFor="temporal-window" className="text-label-sm text-on-surface-variant">
              Max consecutive gap
            </label>
            <div className="flex items-center gap-1">
              <input
                id="temporal-window"
                type="number"
                min={0.1}
                step={1}
                value={temporalWindowSeconds}
                onChange={(event) =>
                  setTemporalWindowSeconds(Math.max(0.1, Number(event.target.value) || 0.1))
                }
                className="w-20 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1 font-mono text-mono-sm outline-none focus:border-primary text-right"
              />
              <span className="text-label-xs text-on-surface-variant">sec</span>
            </div>
          </div>
        </div>

        {/* Grid Columns */}
        {onGridColsChange && (
          <div className="mb-4">
            <label className="text-label-md text-on-surface-variant flex items-center gap-1 mb-1">
              <Icon name="grid_view" size={16} /> Grid Columns
            </label>
            <div className="flex items-center gap-2">
              <input
                type="range"
                min={2}
                max={12}
                value={gridCols}
                onChange={(e) => onGridColsChange(Number(e.target.value))}
                className="flex-1 accent-primary"
              />
              <span className="text-label-sm text-on-surface-variant w-4 text-center">{gridCols}</span>
            </div>
          </div>
        )}
      </div>

      {/* Queries List */}
      <div className={`${queriesVisible ? "flex-1 min-h-0 overflow-y-auto" : "shrink-0"} custom-scrollbar p-stack-gap flex flex-col gap-stack-gap bg-surface-container-low`}>
        <div className="flex justify-between items-center px-1 shrink-0">
          <button
            type="button"
            onClick={() => setQueriesVisible((visible) => !visible)}
            aria-expanded={queriesVisible}
            aria-controls="query-input-area"
            className="flex items-center gap-1 text-label-md text-on-surface hover:text-primary transition-colors"
          >
            <Icon name={queriesVisible ? "expand_less" : "expand_more"} size={18} />
            Queries ({queries.length})
          </button>
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
        <div id="query-input-area" className={queriesVisible ? "flex flex-col gap-stack-gap" : "hidden"}>
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
                  />
                ))}
              </div>
            )}
        </div>
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
