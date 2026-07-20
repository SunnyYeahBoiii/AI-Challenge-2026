"use client";

import { useState } from "react";
import { Icon } from "./icon";

interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}

export function TagInput({ tags, onChange, placeholder = "Add tag..." }: TagInputProps) {
  const [input, setInput] = useState("");

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && input.trim()) {
      e.preventDefault();
      onChange([...tags, input.trim()]);
      setInput("");
    }
  };

  const removeTag = (tag: string) => {
    onChange(tags.filter((t) => t !== tag));
  };

  return (
    <div className="flex flex-wrap gap-1.5">
      {tags.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 border border-primary/30 text-on-surface font-label-sm text-label-sm"
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
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={tags.length === 0 ? placeholder : ""}
        className="flex-1 min-w-[100px] bg-transparent border-none outline-none font-body-sm text-body-sm placeholder:text-outline"
      />
    </div>
  );
}
