"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./icon";

interface DropdownPosition {
  top: number;
  left: number;
  width: number;
}

interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  suggestions?: readonly string[];
  allowCustomValues?: boolean;
}

export function TagInput({
  tags,
  onChange,
  placeholder = "Add tag...",
  suggestions,
  allowCustomValues = true,
}: TagInputProps) {
  const tagInputRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLUListElement>(null);
  const [input, setInput] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [dropdownPosition, setDropdownPosition] = useState<DropdownPosition | null>(null);
  const matches = useMemo(() => {
    const query = input.trim().toLocaleLowerCase();
    if (!query || !suggestions) {
      return [];
    }
    return suggestions
      .filter((suggestion) => !tags.includes(suggestion))
      .filter((suggestion) => suggestion.toLocaleLowerCase().includes(query))
      .slice(0, 24);
  }, [input, suggestions, tags]);
  const activeSuggestion = activeIndex >= 0 ? matches[activeIndex] : undefined;

  useEffect(() => {
    setActiveIndex(-1);
  }, [input]);

  const showSuggestions = isFocused && matches.length > 0;

  useEffect(() => {
    if (activeIndex < 0) {
      return;
    }
    dropdownRef.current
      ?.querySelector(`#tag-suggestion-${activeIndex}`)
      ?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  useEffect(() => {
    if (!showSuggestions) {
      setDropdownPosition(null);
      return;
    }

    const updatePosition = () => {
      const rect = tagInputRef.current?.getBoundingClientRect();
      if (rect) {
        setDropdownPosition({
          top: rect.bottom + 8,
          left: rect.left - 8,
          width: rect.width + 16,
        });
      }
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [showSuggestions]);

  const addTag = (value: string) => {
    if (!tags.includes(value)) {
      onChange([...tags, value]);
    }
    setInput("");
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" && matches.length > 0) {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % matches.length);
      return;
    }
    if (event.key === "ArrowUp" && matches.length > 0) {
      event.preventDefault();
      setActiveIndex((index) => (index <= 0 ? matches.length - 1 : index - 1));
      return;
    }
    if (event.key === "Escape") {
      setIsFocused(false);
      setActiveIndex(-1);
      return;
    }
    if ((event.key === "Enter" || event.key === ",") && input.trim()) {
      event.preventDefault();
      if (activeSuggestion) {
        addTag(activeSuggestion);
        return;
      }
      const typedValue = input.trim();
      const canonicalValue = suggestions?.find(
        (suggestion) => suggestion.toLocaleLowerCase() === typedValue.toLocaleLowerCase()
      );
      if (canonicalValue) {
        addTag(canonicalValue);
        return;
      }
      if (allowCustomValues) {
        addTag(typedValue);
      }
    }
  };

  const removeTag = (tag: string) => {
    onChange(tags.filter((item) => item !== tag));
  };

  return (
    <div ref={tagInputRef} className="relative">
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag) => (
          <span
            key={tag}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 border border-primary/30 text-on-surface text-label-sm"
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(tag)}
              className="text-on-surface-variant hover:text-error transition-colors"
              aria-label={`Remove ${tag}`}
            >
              <Icon name="close" size={14} />
            </button>
          </span>
        ))}
        <div className="relative min-w-[140px] flex-1">
          <input
            type="text"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => {
              setIsFocused(false);
              setActiveIndex(-1);
            }}
            onKeyDown={handleKeyDown}
            placeholder={tags.length === 0 ? placeholder : ""}
            aria-autocomplete={suggestions ? "list" : undefined}
            aria-controls={showSuggestions ? "tag-suggestions" : undefined}
            aria-activedescendant={
              activeSuggestion ? `tag-suggestion-${activeIndex}` : undefined
            }
            aria-expanded={showSuggestions}
            className="relative z-10 w-full bg-transparent border-none outline-none text-body-sm placeholder:text-outline"
          />
        </div>
      </div>
      {showSuggestions &&
        dropdownPosition &&
        createPortal(
        <ul
          ref={dropdownRef}
          id="tag-suggestions"
          role="listbox"
          style={dropdownPosition}
          className="fixed z-50 h-80 overflow-y-auto rounded-xl border border-outline-variant bg-surface-container-lowest p-1.5 shadow-xl"
        >
          <li className="flex items-center justify-between px-2 py-1.5 text-label-xs text-on-surface-variant">
            <span>COCO classes</span>
            <span>↑↓ navigate · Enter select</span>
          </li>
          {matches.map((suggestion, index) => (
            <li
              key={suggestion}
              id={`tag-suggestion-${index}`}
              role="option"
              aria-selected={activeSuggestion === suggestion}
            >
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => addTag(suggestion)}
                onMouseEnter={() => setActiveIndex(index)}
                className={`w-full rounded-lg px-2 py-2 text-left text-body-sm transition-colors ${
                  activeSuggestion === suggestion
                    ? "bg-primary text-on-primary"
                    : "text-on-surface hover:bg-surface-container-high"
                }`}
              >
                {suggestion}
              </button>
            </li>
          ))}
        </ul>,
        document.body
      )}
    </div>
  );
}
