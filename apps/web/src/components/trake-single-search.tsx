"use client";

import { useState } from "react";
import { Icon } from "./icon";

interface TrakeSingleSearchProps {
  onSearch: (lines: string[]) => void;
  onClear: () => void;
  onValidationError: (message: string) => void;
  isLoading?: boolean;
}

export function TrakeSingleSearch({
  onSearch,
  onClear,
  onValidationError,
  isLoading,
}: TrakeSingleSearchProps) {
  const [text, setText] = useState("");

  const handleSearch = () => {
    const lines = text
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    if (lines.length === 0) {
      onValidationError("Enter at least one event (one per line).");
      return;
    }
    onSearch(lines);
  };

  const handleClear = () => {
    setText("");
    onClear();
  };

  return (
    <div className="w-sidebar-width shrink-0 h-screen overflow-y-auto bg-surface-container-lowest border-r border-outline-variant p-4 flex flex-col gap-3">
      <div className="text-label-md font-bold text-on-surface">
        TRAKE events
      </div>
      <p className="text-body-sm text-on-surface-variant">
        One event per line, in temporal order.
      </p>
      <textarea
        className="w-full flex-1 min-h-64 rounded border border-outline-variant bg-surface px-3 py-2 text-body-md text-on-surface focus:outline-none focus:ring-2 focus:ring-primary resize-y"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={"Cảnh 1: ...\nCảnh 2: ...\nCảnh 3: ..."}
        disabled={isLoading}
      />
      <div className="flex gap-2">
        <button
          onClick={handleSearch}
          disabled={isLoading}
          className="flex-1 flex items-center justify-center gap-1 px-4 py-2 rounded bg-primary text-on-primary text-label-md font-bold hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          <Icon name="search" size={18} />
          {isLoading ? "Searching..." : "Search"}
        </button>
        <button
          onClick={handleClear}
          disabled={isLoading}
          className="px-4 py-2 rounded border border-outline-variant text-label-md text-on-surface-variant hover:bg-surface-container transition-colors disabled:opacity-50"
        >
          Clear
        </button>
      </div>
    </div>
  );
}
