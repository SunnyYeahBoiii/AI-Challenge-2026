"use client";

import { useState, useCallback } from "react";
import { Icon } from "./icon";
import { QueryBox, type BoxQuery } from "./query-box";

export interface SearchFilter {
  videoId?: string;
  queries: BoxQuery[];
  sortBy: "frame_id" | "score";
  topK: number;
}

interface FilterPanelProps {
  onSearch: (filter: SearchFilter) => void;
  onClear: () => void;
  isLoading?: boolean;
}

export function FilterPanel({ onSearch, onClear, isLoading }: FilterPanelProps) {
  const [videoId, setVideoId] = useState("");
  const [queries, setQueries] = useState<BoxQuery[]>([
    { id: "1", type: "text", content: "", enabled: true },
  ]);
  const [sortBy, setSortBy] = useState<"frame_id" | "score">("frame_id");
  const [topK, setTopK] = useState(100);

  const handleSearch = useCallback(() => {
    if (videoId.trim()) {
      onSearch({ videoId: videoId.trim(), queries: [], sortBy, topK: 10000 });
    } else {
      const enabledQueries = queries.filter((q) => q.enabled && q.content);
      if (enabledQueries.length > 0) {
        onSearch({ queries: enabledQueries, sortBy, topK });
      }
    }
  }, [videoId, queries, sortBy, topK, onSearch]);

  const addQuery = () => {
    setQueries((prev) => [
      ...prev,
      { id: Date.now().toString(), type: "text", content: "", enabled: true },
    ]);
  };

  const updateQuery = (id: string, updates: Partial<BoxQuery>) => {
    setQueries((prev) => prev.map((q) => (q.id === id ? { ...q, ...updates } : q)));
  };

  const removeQuery = (id: string) => {
    setQueries((prev) => prev.filter((q) => q.id !== id));
  };

  return (
    <aside className="bg-surface-container-low border-r border-outline-variant flex flex-col h-screen overflow-y-auto w-sidebar-width flex-shrink-0 z-10 custom-scrollbar">
      {/* Top Section */}
      <div className="p-container-padding pb-2 border-b border-outline-variant">
        {/* Video ID Search */}
        <div className="mb-4">
          <label className="font-label-md text-label-md text-on-surface-variant flex items-center gap-1 mb-1">
            <Icon name="movie" size={16} /> Video ID Search
          </label>
          <input
            className="w-full bg-surface-container-lowest border-b border-outline-variant focus:border-primary bg-transparent px-0 py-1.5 font-body-sm text-body-sm outline-none transition-colors placeholder:text-outline"
            placeholder="Enter Video ID [e.g., K01_V001]"
            value={videoId}
            onChange={(e) => setVideoId(e.target.value)}
          />
        </div>

        {/* Query Search Mode */}
        <div className="mb-4">
          <label className="font-label-md text-label-md text-on-surface-variant flex items-center gap-1 mb-2">
            <Icon name="search" size={16} /> Query Search Mode
          </label>
          <div className="flex justify-between items-center mb-2">
            <span className="font-label-sm text-label-sm text-on-surface-variant">Sort By</span>
            <select
              className="bg-surface-container-lowest border border-outline-variant rounded px-2 py-1 font-label-sm text-label-sm outline-none focus:border-primary"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as "frame_id" | "score")}
            >
              <option value="frame_id">Frame ID</option>
              <option value="score">Score</option>
            </select>
          </div>
          <div className="flex justify-between items-center">
            <span className="font-label-sm text-label-sm text-on-surface-variant">Top K</span>
            <input
              className="w-20 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1 font-mono-sm text-mono-sm outline-none focus:border-primary text-right"
              type="number"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            />
          </div>
        </div>
      </div>

      {/* Queries List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-stack-gap flex flex-col gap-stack-gap bg-surface-container-low">
        <div className="flex justify-between items-center px-1">
          <h3 className="font-label-md text-label-md text-on-surface">Queries</h3>
          <button
            onClick={addQuery}
            className="text-on-surface-variant hover:text-primary transition-colors"
          >
            <Icon name="add" size={18} />
          </button>
        </div>
        {queries.map((query) => (
          <QueryBox
            key={query.id}
            query={query}
            onUpdate={(updates) => updateQuery(query.id, updates)}
            onRemove={() => removeQuery(query.id)}
            canRemove={queries.length > 1}
          />
        ))}
      </div>

      {/* Action Buttons */}
      <div className="p-4 border-t border-outline-variant bg-surface-container-lowest flex gap-2">
        <button
          onClick={onClear}
          className="flex-1 bg-surface-container hover:bg-surface-variant border border-outline-variant text-on-surface font-label-md text-label-md py-2 rounded transition-colors"
        >
          Clear
        </button>
        <button
          onClick={handleSearch}
          disabled={isLoading}
          className="flex-1 bg-primary-container hover:bg-opacity-90 text-on-primary-container font-label-md text-label-md py-2 rounded transition-colors disabled:opacity-50"
        >
          {isLoading ? "Searching..." : "Enter"}
        </button>
      </div>
    </aside>
  );
}
