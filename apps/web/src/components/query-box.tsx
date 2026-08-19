"use client";

import { useState, useRef } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Icon } from "./icon";
import { TagInput } from "./tag-input";
import { Toggle } from "./toggle";
import { MatchModeToggle } from "./match-mode-toggle";
import { KeywordSearchOptions, type KeywordSearchConfig } from "./keyword-search-options";
import { COCO_CLASS_NAMES } from "@/lib/coco-classes";

export interface BoxQuery {
  id: string;
  type: "text" | "image";
  content: string;
  enabled: boolean;
  tags?: string[];
  tagMatchMode?: "and" | "or";
  ocrKeywords?: string[];
  ocrMatchMode?: "and" | "or";
  ocrSearchConfig?: KeywordSearchConfig;
  asrKeywords?: string[];
  asrMatchMode?: "and" | "or";
  asrSearchConfig?: KeywordSearchConfig;
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

type SortableBindings = ReturnType<typeof useSortable> | null;

/** Static box for SSR / pre-hydrate — same markup, no dnd-kit IDs. */
export function QueryBoxStatic(props: QueryBoxProps) {
  return <QueryBoxInner {...props} sortable={null} />;
}

/** Sortable box — must render inside DndContext + SortableContext. */
export function QueryBox(props: QueryBoxProps) {
  const sortable = useSortable({ id: props.query.id });
  return <QueryBoxInner {...props} sortable={sortable} />;
}

function QueryBoxInner({
  query,
  index,
  onUpdate,
  onRemove,
  canRemove,
  sortable,
}: QueryBoxProps & { sortable: SortableBindings }) {
  const style = sortable
    ? {
        transform: CSS.Transform.toString(sortable.transform),
        transition: sortable.transition,
        opacity: sortable.isDragging ? 0.5 : 1,
      }
    : undefined;
  const [showTags, setShowTags] = useState(false);
  const [showKeywords, setShowKeywords] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const hasVectorQuery = Boolean(query.content.trim());

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

  const nodeRef = sortable?.setNodeRef;

  return (
    <div
      ref={nodeRef}
      style={style}
      className="bg-surface-container-lowest border border-outline-variant rounded-lg shadow-sm overflow-hidden flex flex-col shrink-0 relative"
    >
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
            {...(sortable?.attributes ?? {})}
            {...(sortable?.listeners ?? {})}
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
            max={5000}
            aria-label={hasVectorQuery ? "Raw Milvus Top K candidates" : "Maximum filter matches"}
            title={
              hasVectorQuery
                ? "Raw Milvus candidates before object and OCR/ASR post-filters (1–5000)"
                : "Maximum matching frames returned by this filter-only box (1–5000)"
            }
            value={query.topK ?? 1000}
            onChange={(e) =>
              onUpdate({ topK: Math.min(5000, Math.max(1, Number(e.target.value) || 1)) })
            }
          />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-label-sm text-on-surface-variant">AI Enhance</span>
          <Toggle
            checked={query.enhance ?? true}
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
            <MatchModeToggle
              label="Match tags"
              mode={query.tagMatchMode ?? "and"}
              onChange={(tagMatchMode) => onUpdate({ tagMatchMode })}
            />
          </div>
        )}
        <button
          onClick={() => setShowKeywords(!showKeywords)}
          className="w-full px-3 py-2 flex items-center gap-2 cursor-pointer hover:bg-surface-container-high transition-colors rounded-b-lg"
        >
          <Icon name="key" size={14} className="text-outline" />
          <span className="text-label-sm text-on-surface-variant">
            Keywords
            {((query.ocrKeywords?.length ?? 0) + (query.asrKeywords?.length ?? 0)) > 0 &&
              ` (${(query.ocrKeywords?.length ?? 0) + (query.asrKeywords?.length ?? 0)})`}
          </span>
          <Icon
            name={showKeywords ? "expand_less" : "expand_more"}
            size={16}
            className="text-outline ml-auto"
          />
        </button>
        {showKeywords && (
          <div className="p-3 space-y-3">
            <div>
              <span className="text-label-sm text-on-surface-variant">OCR</span>
              <TagInput
                tags={query.ocrKeywords || []}
                onChange={(ocrKeywords) => onUpdate({ ocrKeywords })}
                placeholder="Add OCR keyword..."
              />
              <MatchModeToggle
                label="OCR keyword relation"
                mode={query.ocrMatchMode ?? "and"}
                onChange={(ocrMatchMode) => onUpdate({ ocrMatchMode })}
              />
              <KeywordSearchOptions
                source="OCR"
                config={query.ocrSearchConfig}
                onChange={(ocrSearchConfig) => onUpdate({ ocrSearchConfig })}
              />
            </div>
            <div>
              <span className="text-label-sm text-on-surface-variant">ASR</span>
              <TagInput
                tags={query.asrKeywords || []}
                onChange={(asrKeywords) => onUpdate({ asrKeywords })}
                placeholder="Add ASR keyword..."
              />
              <MatchModeToggle
                label="ASR keyword relation"
                mode={query.asrMatchMode ?? "and"}
                onChange={(asrMatchMode) => onUpdate({ asrMatchMode })}
              />
              <KeywordSearchOptions
                source="ASR"
                config={query.asrSearchConfig}
                onChange={(asrSearchConfig) => onUpdate({ asrSearchConfig })}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
