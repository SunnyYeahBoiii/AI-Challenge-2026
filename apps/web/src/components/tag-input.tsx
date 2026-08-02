"use client";

import { useMemo, useState } from "react";
import { Icon } from "./icon";

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
  const [input, setInput] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const matches = useMemo(() => {
    const query = input.trim().toLocaleLowerCase();
    if (!query || !suggestions) {
      return [];
    }
    return suggestions
      .filter((suggestion) => !tags.includes(suggestion))
      .filter((suggestion) => suggestion.toLocaleLowerCase().includes(query))
      .slice(0, 8);
  }, [input, suggestions, tags]);

  const addTag = (value: string) => {
    if (!tags.includes(value)) {
      onChange([...tags, value]);
    }
    setInput("");
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setIsFocused(false);
      return;
    }
    if (event.key === "Enter" && input.trim()) {
      event.preventDefault();
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

  const showSuggestions = isFocused && matches.length > 0;

  return (
    <div className="relative">
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
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onKeyDown={handleKeyDown}
          placeholder={tags.length === 0 ? placeholder : ""}
          aria-autocomplete={suggestions ? "list" : undefined}
          aria-expanded={showSuggestions}
          className="flex-1 min-w-[100px] bg-transparent border-none outline-none text-body-sm placeholder:text-outline"
        />
      </div>
      {showSuggestions && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 top-full z-20 mt-1 max-h-48 overflow-y-auto rounded border border-outline-variant bg-surface-container-lowest py-1 shadow-lg"
        >
          {matches.map((suggestion) => (
            <li key={suggestion} role="option" aria-selected={false}>
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => addTag(suggestion)}
                className="w-full px-3 py-1.5 text-left text-body-sm text-on-surface hover:bg-surface-container-high"
              >
                {suggestion}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
