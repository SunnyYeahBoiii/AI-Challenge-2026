"use client";

import { useState, useRef } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Icon } from "./icon";
import { TagInput } from "./tag-input";
import { Toggle } from "./toggle";
import { COCO_CLASS_NAMES } from "@/lib/coco-classes";

export interface BoxQuery {
  id: string;
  type: "text" | "image";
  content: string;
  enabled: boolean;
  tags?: string[];
  tagMatchMode?: "and" | "or";
  keywords?: string[];
  topK?: number;
  enhance?: boolean;
}

interface QueryBoxProps {
  query: BoxQuery;
  index: number;
  onUpdate: (updates: Partial<BoxQuery>) => void;
  onRemove: () => void;
  canRemove: boolean;
}

export function QueryBox({ query, index, onUpdate, onRemove, canRemove }: QueryBoxProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: query.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  const [showTags, setShowTags] = useState(false);
  const [showKeywords, setShowKeywords] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (ev) => {
        onUpdate({ type: "image", content: ev.target?.result as string });
      };
      reader.readAsDataURL(file);
    }
  };

  return (
    <div ref={setNodeRef} style={style} className="bg-surface-container-lowest border border-outline-variant rounded-lg shadow-sm overflow-hidden flex flex-col shrink-0 relative">
      {/* Index badge */}
      <div className="absolute top-1 left-1 z-10 w-5 h-5 rounded bg-primary text-on-primary flex items-center justify-center text-label-xs">
        {index + 1}
      </div>
      {/* Header */}
      <div className="flex justify-between items-center p-2 pl-7 border-b border-surface-variant bg-surface-bright rounded-t-lg">
        {/* Toggle */}
        <Toggle
          checked={query.enabled}
          onChange={(enabled) => onUpdate({ enabled })}
          label={`Query ${index + 1} enabled`}
        />
        {/* Actions */}
        <div className="flex gap-1">
          <button
            aria-label="Drag to reorder"
            className="text-outline hover:text-on-surface transition-colors p-1 cursor-grab active:cursor-grabbing"
            {...attributes}
            {...listeners}
          >
            <Icon name="drag_indicator" size={16} />
          </button>
          <button
            onClick={() => {
              if (query.type === "text") {
                onUpdate({ type: "image", content: "" });
                fileInputRef.current?.click();
              } else {
                onUpdate({ type: "text", content: "" });
              }
            }}
            aria-label={query.type === "text" ? "Switch to image query" : "Switch to text query"}
            className="text-outline hover:text-on-surface transition-colors p-1"
          >
            <Icon name={query.type === "text" ? "image" : "text_fields"} size={16} />
          </button>
          {canRemove && (
            <button
              onClick={onRemove}
              aria-label="Remove query"
              className="text-error opacity-70 hover:opacity-100 transition-colors p-1"
            >
              <Icon name="delete" size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="p-3 bg-surface-container-lowest">
        {query.type === "text" ? (
          <textarea
            className="w-full h-20 resize-none bg-transparent border-none focus:ring-0 p-0 text-body-sm outline-none"
            placeholder="Enter query text..."
            value={query.content}
            onChange={(e) => onUpdate({ content: e.target.value })}
          />
        ) : (
          <div className="relative">
            {query.content ? (
              <div className="relative">
                <img
                  src={query.content}
                  alt="Query"
                  className="w-full h-20 object-cover rounded"
                />
                <button
                  onClick={() => onUpdate({ content: "" })}
                  className="absolute top-1 right-1 bg-black/50 rounded-full p-0.5"
                >
                  <Icon name="close" size={14} className="text-white" />
                </button>
              </div>
            ) : (
              <div
                onClick={() => fileInputRef.current?.click()}
                className="w-full h-20 border-2 border-dashed border-outline-variant rounded flex items-center justify-center cursor-pointer hover:bg-surface-container-high transition-colors"
              >
                <Icon name="image" size={24} className="text-outline" />
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleImageUpload}
            />
          </div>
        )}
      </div>

      {/* Top K & AI Enhance */}
      <div className="flex justify-between items-center px-3 py-2 border-t border-surface-variant">
        <div className="flex items-center gap-2">
          <span className="text-label-sm text-on-surface-variant">Top K</span>
          <input
            className="w-16 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1 font-mono text-mono-sm outline-none focus:border-primary text-right"
            type="number"
            min={1}
            aria-label="Top K results"
            value={query.topK ?? 100}
            onChange={(e) => onUpdate({ topK: Math.max(1, Number(e.target.value) || 1) })}
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-label-sm text-on-surface-variant">AI Enhance</span>
          <Toggle
            checked={query.enhance ?? false}
            onChange={(enhance) => onUpdate({ enhance })}
            label="AI Enhance"
          />
        </div>
      </div>

      {/* Footer - Expandable Tags/Keywords */}
      <div className="bg-surface-bright rounded-b-lg border-t border-surface-variant">
        <button
          onClick={() => setShowTags(!showTags)}
          className="w-full px-3 py-2 flex items-center gap-2 border-b border-surface-variant cursor-pointer hover:bg-surface-container-high transition-colors"
        >
          <Icon name="sell" size={14} className="text-outline" />
          <span className="text-label-sm text-on-surface-variant">
            Tags {query.tags && query.tags.length > 0 && `(${query.tags.length})`}
          </span>
          <Icon
            name={showTags ? "expand_less" : "expand_more"}
            size={16}
            className="text-outline ml-auto"
          />
        </button>
        {showTags && (
          <div className="p-3 border-b border-surface-variant">
            <TagInput
              tags={query.tags || []}
              onChange={(tags) => onUpdate({ tags })}
              placeholder="Search COCO class..."
              suggestions={COCO_CLASS_NAMES}
              allowCustomValues={false}
            />
            <div className="mt-3 flex items-center gap-2">
              <span className="text-label-sm text-on-surface-variant">Match tags</span>
              <div className="flex overflow-hidden rounded border border-outline-variant">
                {(["and", "or"] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => onUpdate({ tagMatchMode: mode })}
                    className={`px-2 py-1 text-label-xs uppercase transition-colors ${
                      (query.tagMatchMode ?? "and") === mode
                        ? "bg-primary text-on-primary"
                        : "text-on-surface-variant hover:bg-surface-container-high"
                    }`}
                    aria-pressed={(query.tagMatchMode ?? "and") === mode}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
        <button
          onClick={() => setShowKeywords(!showKeywords)}
          className="w-full px-3 py-2 flex items-center gap-2 cursor-pointer hover:bg-surface-container-high transition-colors rounded-b-lg"
        >
          <Icon name="key" size={14} className="text-outline" />
          <span className="text-label-sm text-on-surface-variant">
            Keywords {query.keywords && query.keywords.length > 0 && `(${query.keywords.length})`}
          </span>
          <Icon
            name={showKeywords ? "expand_less" : "expand_more"}
            size={16}
            className="text-outline ml-auto"
          />
        </button>
        {showKeywords && (
          <div className="p-3">
            <TagInput
              tags={query.keywords || []}
              onChange={(keywords) => onUpdate({ keywords })}
              placeholder="Add keyword..."
            />
          </div>
        )}
      </div>
    </div>
  );
}
