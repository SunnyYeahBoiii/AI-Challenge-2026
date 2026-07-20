"use client";

import { useState, useRef } from "react";
import { Icon } from "./icon";
import { TagInput } from "./tag-input";

export interface BoxQuery {
  id: string;
  type: "text" | "image";
  content: string;
  enabled: boolean;
  tags?: string[];
  keywords?: string[];
}

interface QueryBoxProps {
  query: BoxQuery;
  onUpdate: (updates: Partial<BoxQuery>) => void;
  onRemove: () => void;
  canRemove: boolean;
}

export function QueryBox({ query, onUpdate, onRemove, canRemove }: QueryBoxProps) {
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
    <div className="bg-surface-container-lowest border border-outline-variant rounded-lg shadow-sm overflow-hidden flex flex-col shrink-0">
      {/* Header */}
      <div className="flex justify-between items-center p-2 border-b border-surface-variant bg-surface-bright rounded-t-lg">
        {/* Toggle */}
        <div className="relative inline-block w-[36px] h-[20px]">
          <input
            type="checkbox"
            checked={query.enabled}
            onChange={(e) => onUpdate({ enabled: e.target.checked })}
            className="toggle-checkbox absolute block w-4 h-4 rounded-full bg-white border-4 appearance-none cursor-pointer z-10 opacity-0"
          />
          <label className="toggle-label block overflow-hidden h-5 rounded-full bg-surface-variant cursor-pointer" />
        </div>
        {/* Actions */}
        <div className="flex gap-1">
          <button className="text-outline hover:text-on-surface transition-colors p-1">
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
            className="text-outline hover:text-on-surface transition-colors p-1"
          >
            <Icon name="image" size={16} />
          </button>
          {canRemove && (
            <button
              onClick={onRemove}
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
            className="w-full h-20 resize-none bg-transparent border-none focus:ring-0 p-0 font-body-sm text-body-sm outline-none"
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

      {/* Footer - Expandable Tags/Keywords */}
      <div className="bg-surface-bright rounded-b-lg border-t border-surface-variant">
        <button
          onClick={() => setShowTags(!showTags)}
          className="w-full px-3 py-2 flex items-center gap-2 border-b border-surface-variant cursor-pointer hover:bg-surface-container-high transition-colors"
        >
          <Icon name="sell" size={14} className="text-outline" />
          <span className="font-label-sm text-label-sm text-on-surface-variant">
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
              placeholder="Add tag..."
            />
          </div>
        )}
        <button
          onClick={() => setShowKeywords(!showKeywords)}
          className="w-full px-3 py-2 flex items-center gap-2 cursor-pointer hover:bg-surface-container-high transition-colors rounded-b-lg"
        >
          <Icon name="key" size={14} className="text-outline" />
          <span className="font-label-sm text-label-sm text-on-surface-variant">
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
