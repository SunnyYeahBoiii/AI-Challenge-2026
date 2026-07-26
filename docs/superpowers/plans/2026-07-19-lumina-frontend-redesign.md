# Lumina Frontend Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Frame Seeker frontend to match the Lumina Search System design — new color palette, Material Symbols icons, React Query for API calls, and cleaned-up dead code.

**Architecture:** Incremental restyle of existing React + Vite + shadcn/ui + Tailwind app. Update Tailwind theme tokens, replace icons, wire React Query, clean dead code. No new framework, no router.

**Tech Stack:** React 18, Vite 7, Tailwind CSS 3.4, shadcn/ui, Material Symbols, React Query, Vitest

## Global Constraints

- React 18 + Vite 7 (no framework change)
- shadcn/ui components (reuse, don't replace)
- Tailwind CSS 3.4 with Lumina design tokens
- Material Symbols (Google) for all icons
- React Query for API state management
- Vitest + @testing-library/react for testing
- No router — state-based navigation
- Only Queries page in scope (skip History/Collections/COCO)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `tailwind.config.ts` | Lumina color tokens, typography, spacing, border radius |
| `globals.css` | CSS custom properties matching Lumina palette |
| `index.html` | Add Material Symbols Google Fonts link |
| `lib/api.ts` | Add React Query hooks (useQuery/useMutation wrappers) |
| `lib/types.ts` | Keep, clean duplicate type definitions |
| `app/Home.tsx` | Restructure layout: top bar + sidebar + main content |
| `components/filter-panel.tsx` | Lumina sidebar: video ID, query mode, query cards list |
| `components/query-box.tsx` | Lumina query card: toggle, drag, image mode, delete, expandable tags/keywords |
| `components/results-panel.tsx` | Grouped/Continuous modes, responsive grid (2-7 cols) |
| `components/submit-bar.tsx` | Merge into top bar (remove as separate component) |
| `components/frame-detail-dialog.tsx` | Theme update to Lumina palette |
| `components/tag-input.tsx` | Theme update |
| `components/dres-settings-dialog.tsx` | Theme update |
| `components/submission-confirmation-dialog.tsx` | Theme update |
| `contexts/DresContext.tsx` | React Query integration for DRES |
| `hooks/useFrameSearch.ts` | Replace raw fetch with React Query |
| `hooks/useFrameDetails.ts` | Replace raw fetch with React Query |
| `vitest.config.ts` | Vitest configuration |
| `src/__tests__/*.test.tsx` | Component tests |

---

## Task 1: Clean Dead Code & Fix Config

Remove unused files and fix the tailwindcss-animate plugin typo before restyling.

**Files:**
- Delete: `app/actions.ts`, `app/frame-search.tsx`, `app/flask-test.tsx`, `components/FlaskTest.tsx`, `components/FrameSearch.tsx`, `hooks/useDresSubmission.ts`
- Modify: `tailwind.config.ts:100` (fix `pluginmates` → `plugins`)
- Modify: all files with `"use client"` directives (remove them)

- [ ] **Step 1: Delete unused files**

```bash
cd /Users/sunny/workspace/AIChallenge2025/frontend
rm -f src/app/actions.ts src/app/frame-search.tsx src/app/flask-test.tsx
rm -f src/components/FlaskTest.tsx src/components/FrameSearch.tsx
rm -f src/hooks/useDresSubmission.ts
```

- [ ] **Step 2: Fix tailwind.config.ts plugin typo**

In `tailwind.config.ts`, line 100, change `pluginmates` to `plugins`:

```ts
// Before
pluginmates: [require("tailwindcss-animate")],

// After
plugins: [require("tailwindcss-animate")],
```

- [ ] **Step 3: Remove "use client" directives**

Search and remove all `"use client"` directives from:
- `src/app/Home.tsx`
- `src/components/filter-panel.tsx`
- `src/components/results-panel.tsx`
- `src/components/query-box.tsx`
- `src/components/submit-bar.tsx`
- `src/components/frame-detail-dialog.tsx`
- `src/components/tag-input.tsx`
- `src/components/dres-settings-dialog.tsx`
- `src/components/submission-confirmation-dialog.tsx`
- `src/contexts/DresContext.tsx`

- [ ] **Step 4: Remove unused dependencies from package.json**

```bash
cd /Users/sunny/workspace/AIChallenge2025/frontend
npm uninstall recharts date-fns patch-package react-day-picker dotenv 2>/dev/null || true
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dead code, fix tailwindcss-animate plugin"
```

---

## Task 2: Update Theme & Design Tokens

Replace the old shadcn/ui CSS variables with Lumina palette tokens.

**Files:**
- Modify: `tailwind.config.ts` (extend colors, fonts, spacing, borderRadius)
- Modify: `src/globals.css` (replace CSS custom properties)

- [ ] **Step 1: Update tailwind.config.ts with Lumina tokens**

Replace the `theme.extend` section in `tailwind.config.ts`:

```ts
theme: {
  extend: {
    colors: {
      primary: "#0c6780",
      "on-primary": "#ffffff",
      "primary-container": "#87ceeb",
      "on-primary-container": "#005870",
      "inverse-primary": "#89d0ed",
      secondary: "#0058bc",
      "on-secondary": "#ffffff",
      "secondary-container": "#0070eb",
      "on-secondary-container": "#fefcff",
      tertiary: "#5c5f61",
      "on-tertiary": "#ffffff",
      "tertiary-container": "#c2c5c7",
      "on-tertiary-container": "#4e5254",
      error: "#ba1a1a",
      "on-error": "#ffffff",
      "error-container": "#ffdad6",
      "on-error-container": "#93000a",
      background: "#f9f9fc",
      "on-background": "#1a1c1e",
      surface: "#f9f9fc",
      "on-surface": "#1a1c1e",
      "on-surface-variant": "#3f484c",
      "surface-variant": "#e2e2e5",
      "surface-dim": "#dadadc",
      "surface-bright": "#f9f9fc",
      "surface-tint": "#0c6780",
      "surface-container-lowest": "#ffffff",
      "surface-container-low": "#f3f3f6",
      "surface-container": "#eeeef0",
      "surface-container-high": "#e8e8ea",
      "surface-container-highest": "#e2e2e5",
      outline: "#6f787d",
      "outline-variant": "#bfc8cd",
      "inverse-surface": "#2f3133",
      "inverse-on-surface": "#f0f0f3",
    },
    borderRadius: {
      DEFAULT: "0.25rem",
      lg: "0.5rem",
      xl: "0.75rem",
      full: "9999px",
    },
    spacing: {
      "sidebar-width": "320px",
      "stack-gap": "12px",
      "topbar-height": "64px",
      "container-padding": "24px",
      gutter: "16px",
    },
    fontFamily: {
      "label-sm": ["Inter"],
      "label-md": ["Inter"],
      "body-md": ["Inter"],
      "body-sm": ["Inter"],
      "mono-sm": ["JetBrains Mono"],
      "headline-sm": ["Inter"],
    },
    fontSize: {
      "label-sm": ["11px", { lineHeight: "14px", fontWeight: "500" }],
      "label-md": ["12px", { lineHeight: "16px", letterSpacing: "0.02em", fontWeight: "600" }],
      "body-sm": ["13px", { lineHeight: "18px", fontWeight: "400" }],
      "body-md": ["14px", { lineHeight: "20px", fontWeight: "400" }],
      "mono-sm": ["12px", { lineHeight: "16px", fontWeight: "400" }],
      "headline-sm": ["18px", { lineHeight: "24px", fontWeight: "600" }],
    },
  },
},
```

- [ ] **Step 2: Update globals.css with Lumina CSS variables**

Replace all CSS custom properties in `src/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 210 20% 98%;
    --foreground: 210 30% 11%;
    --card: 210 20% 98%;
    --card-foreground: 210 30% 11%;
    --popover: 0 0% 100%;
    --popover-foreground: 210 30% 11%;
    --primary: 188 100% 25%;
    --primary-foreground: 0 0% 100%;
    --secondary: 217 100% 42%;
    --secondary-foreground: 0 0% 100%;
    --muted: 210 20% 96%;
    --muted-foreground: 210 10% 46%;
    --accent: 188 76% 77%;
    --accent-foreground: 188 100% 20%;
    --destructive: 0 84% 60%;
    --destructive-foreground: 0 0% 100%;
    --border: 210 15% 75%;
    --input: 210 15% 75%;
    --ring: 188 100% 25%;
    --radius: 0.25rem;
  }
}
```

- [ ] **Step 3: Verify build still works**

```bash
cd /Users/sunny/workspace/AIChallenge2025/frontend
npx vite build
```

Expected: Build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
git add tailwind.config.ts src/globals.css
git commit -m "feat: update theme to Lumina design tokens"
```

---

## Task 3: Add Material Symbols & Remove lucide-react

Switch icon system from lucide-react to Material Symbols (Google).

**Files:**
- Modify: `index.html` (add Google Fonts link for Material Symbols)
- Create: `src/components/icon.tsx` (Material Symbols wrapper component)

- [ ] **Step 1: Add Material Symbols to index.html**

In `index.html`, add inside `<head>`:

```html
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet" />
```

- [ ] **Step 2: Create Material Symbols wrapper component**

Create `src/components/icon.tsx`:

```tsx
interface IconProps {
  name: string;
  className?: string;
  size?: number;
  filled?: boolean;
}

export function Icon({ name, className = "", size = 24, filled = false }: IconProps) {
  return (
    <span
      className={`material-symbols-outlined ${className}`}
      style={{
        fontSize: size,
        fontVariationSettings: filled ? "'FILL' 1" : "'FILL' 0",
      }}
    >
      {name}
    </span>
  );
}
```

- [ ] **Step 3: Add CSS for Material Symbols**

Add to `globals.css`:

```css
.material-symbols-outlined {
  font-family: 'Material Symbols Outlined';
  font-weight: normal;
  font-style: normal;
  font-size: 24px;
  line-height: 1;
  letter-spacing: normal;
  text-transform: none;
  display: inline-block;
  white-space: nowrap;
  word-wrap: normal;
  direction: ltr;
  -webkit-font-feature-settings: 'liga';
  -webkit-font-smoothing: antialiased;
}
```

- [ ] **Step 4: Commit**

```bash
git add index.html src/components/icon.tsx src/globals.css
git commit -m "feat: add Material Symbols icon system"
```

---

## Task 4: Restyle FilterPanel (Sidebar)

Update the filter panel to match Lumina sidebar design.

**Files:**
- Modify: `src/components/filter-panel.tsx`

- [ ] **Step 1: Read current filter-panel.tsx**

Read the file to understand current structure before editing.

- [ ] **Step 2: Restyle FilterPanel with Lumina tokens**

Replace the component with Lumina-styled version. Key changes:
- Background: `bg-surface-container-low`
- Border: `border-r border-outline-variant`
- Width: `w-sidebar-width`
- Video ID section with `movie` icon
- Query Search Mode with `search` icon
- Sort By dropdown + TopK input
- Scrollable query cards area with `gap-stack-gap`
- Clear + Enter buttons at bottom
- Small logo icon at bottom-left

```tsx
import { useState, useCallback } from "react";
import { Icon } from "./icon";
import { QueryBox } from "./query-box";
import type { SearchFilter, BoxQuery } from "../lib/types";

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
      {/* Brand Header */}
      <div className="p-container-padding pb-2 border-b border-outline-variant">
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
      <div className="flex-1 overflow-y-auto sidebar-scroll p-stack-gap flex flex-col gap-stack-gap bg-surface-container-low">
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
```

- [ ] **Step 3: Commit**

```bash
git add src/components/filter-panel.tsx
git commit -m "feat: restyle FilterPanel with Lumina sidebar design"
```

---

## Task 5: Restyle QueryBox (Query Card)

Update the query card to match Lumina design with toggle, drag, image mode, delete, and expandable tags/keywords.

**Files:**
- Modify: `src/components/query-box.tsx`

- [ ] **Step 1: Read current query-box.tsx**

Read the file to understand current structure.

- [ ] **Step 2: Restyle QueryBox with Lumina card design**

```tsx
import { useState, useRef } from "react";
import { Icon } from "./icon";
import { TagInput } from "./tag-input";
import type { BoxQuery } from "../lib/types";

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
    <div className="bg-surface-container-lowest border border-outline-variant rounded shadow-sm overflow-hidden flex flex-col">
      {/* Header */}
      <div className="flex justify-between items-center p-2 border-b border-surface-variant bg-surface-bright">
        {/* Toggle */}
        <div className="relative inline-block w-[36px] h-[20px]">
          <input
            type="checkbox"
            checked={query.enabled}
            onChange={(e) => onUpdate({ enabled: e.target.checked })}
            className="toggle-checkbox absolute block w-4 h-4 rounded-full bg-white border-4 appearance-none cursor-pointer z-10 opacity-0"
          />
          <label className="toggle-label block overflow-hidden h-5 rounded-full bg-surface-variant cursor-pointer"></label>
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
      <div className="border-t border-surface-variant bg-surface-bright">
        <button
          onClick={() => setShowTags(!showTags)}
          className="w-full px-2 py-1.5 flex items-center gap-2 border-b border-surface-variant cursor-pointer hover:bg-surface-container-high transition-colors"
        >
          <Icon name="sell" size={14} className="text-outline" />
          <span className="font-label-sm text-label-sm text-on-surface-variant">Tags</span>
        </button>
        {showTags && (
          <div className="p-2">
            <TagInput
              tags={query.tags || []}
              onChange={(tags) => onUpdate({ tags })}
              placeholder="Add tag..."
            />
          </div>
        )}
        <button
          onClick={() => setShowKeywords(!showKeywords)}
          className="w-full px-2 py-1.5 flex items-center gap-2 cursor-pointer hover:bg-surface-container-high transition-colors rounded-b-lg"
        >
          <Icon name="key" size={14} className="text-outline" />
          <span className="font-label-sm text-label-sm text-on-surface-variant">Keywords</span>
        </button>
        {showKeywords && (
          <div className="p-2">
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
```

- [ ] **Step 3: Add toggle CSS to globals.css**

```css
.toggle-checkbox:checked {
  right: 0;
  border-color: theme('colors.primary');
}
.toggle-checkbox:checked + .toggle-label {
  background-color: theme('colors.primary');
}
.toggle-checkbox:checked + .toggle-label:after {
  transform: translateX(100%);
  border-color: white;
}
.toggle-label {
  width: 36px;
  height: 20px;
  background-color: theme('colors.surface-variant');
  border-radius: 9999px;
  position: relative;
  cursor: pointer;
  transition: background-color 0.2s ease-in-out;
}
.toggle-label:after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background-color: white;
  border-radius: 50%;
  transition: transform 0.2s ease-in-out;
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
}
```

- [ ] **Step 4: Commit**

```bash
git add src/components/query-box.tsx src/globals.css
git commit -m "feat: restyle QueryBox with Lumina card design"
```

---

## Task 6: Restyle ResultsPanel

Update results panel with Grouped/Continuous modes and responsive grid.

**Files:**
- Modify: `src/components/results-panel.tsx`

- [ ] **Step 1: Read current results-panel.tsx**

- [ ] **Step 2: Restyle ResultsPanel with Lumina design**

Add `viewMode` prop for Grouped/Continuous toggle. Update grid to responsive 2-7 columns.

```tsx
import { useMemo } from "react";
import { Icon } from "./icon";
import type { Frame } from "../lib/types";

interface ResultsPanelProps {
  frames: Frame[];
  viewMode: "grouped" | "continuous";
  onFrameSelect: (frame: Frame) => void;
  onFrameDetail: (frame: Frame) => void;
  isLoading?: boolean;
}

export function ResultsPanel({
  frames,
  viewMode,
  onFrameSelect,
  onFrameDetail,
  isLoading,
}: ResultsPanelProps) {
  const groupedFrames = useMemo(() => {
    if (viewMode === "continuous") return [frames];
    const groups = new Map<string, Frame[]>();
    frames.forEach((frame) => {
      const key = frame.videoLink;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(frame);
    });
    return Array.from(groups.values());
  }, [frames, viewMode]);

  if (isLoading) {
    return (
      <div className="p-container-padding">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7 gap-2">
          {Array.from({ length: 20 }).map((_, i) => (
            <div
              key={i}
              className="aspect-video bg-surface-container animate-pulse rounded-sm"
            />
          ))}
        </div>
      </div>
    );
  }

  if (frames.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md">
          <h2 className="font-headline-sm text-headline-sm font-bold text-on-surface mb-2">
            Start Searching
          </h2>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Use the filters on the left and press "Enter" to see results.
          </p>
        </div>
      </div>
    );
  }

  return (
    <main className="flex-1 bg-surface-container-lowest overflow-y-auto p-container-padding">
      <div className="flex flex-col gap-6">
        {groupedFrames.map((group, groupIndex) => (
          <div key={groupIndex} className="flex flex-col gap-2">
            {viewMode === "grouped" && (
              <div className="h-px bg-outline-variant w-full my-1" />
            )}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7 gap-2">
              {group.map((frame) => (
                <div
                  key={frame.frameId}
                  className="relative group cursor-pointer aspect-video bg-surface-container overflow-hidden border border-outline-variant rounded-sm hover:border-primary transition-colors"
                  onClick={() => onFrameSelect(frame)}
                >
                  <img
                    className="w-full h-full object-cover"
                    src={frame.thumbnailPath}
                    alt={`Frame ${frame.frameId}`}
                    loading="lazy"
                  />
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onFrameDetail(frame);
                      }}
                      className="text-white"
                    >
                      <Icon name="play_circle" size={32} className="text-white" filled />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add src/components/results-panel.tsx
git commit -m "feat: restyle ResultsPanel with grouped/continuous modes"
```

---

## Task 7: Restyle Home.tsx (Layout)

Update the main layout to match Lumina design with top bar + sidebar + main content.

**Files:**
- Modify: `src/app/Home.tsx`

- [ ] **Step 1: Read current Home.tsx**

- [ ] **Step 2: Restyle Home.tsx with Lumina layout**

Merge SubmitBar into top bar. Add Grouped/Continuous toggle.

```tsx
import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { FilterPanel } from "../components/filter-panel";
import { ResultsPanel } from "../components/results-panel";
import { FrameDetailDialog } from "../components/frame-detail-dialog";
import { DresSettingsDialog } from "../components/dres-settings-dialog";
import { SubmissionConfirmationDialog } from "../components/submission-confirmation-dialog";
import { PinnedFramePreview } from "../components/pinned-frame-preview";
import { Icon } from "../components/icon";
import { api } from "../lib/api";
import type { SearchFilter, Frame } from "../lib/types";

export function Home() {
  const [filter, setFilter] = useState<SearchFilter | null>(null);
  const [selectedFrame, setSelectedFrame] = useState<Frame | null>(null);
  const [submissionFrame, setSubmissionFrame] = useState<Frame | null>(null);
  const [pinnedFrame, setPinnedFrame] = useState<Frame | null>(null);
  const [showDresSettings, setShowDresSettings] = useState(false);
  const [showSubmitConfirm, setShowSubmitConfirm] = useState(false);
  const [viewMode, setViewMode] = useState<"grouped" | "continuous">("grouped");

  // Submission state
  const [submissionType, setSubmissionType] = useState<"track" | "qa" | "kis">("kis");
  const [frameId, setFrameId] = useState("");
  const [videoId, setVideoId] = useState("");
  const [timeMs, setTimeMs] = useState("");
  const [answer, setAnswer] = useState("");

  const { data: frames = [], isLoading } = useQuery({
    queryKey: ["frames", filter],
    queryFn: () => (filter ? api.searchFrames(filter) : Promise.resolve([])),
    enabled: !!filter,
  });

  const handleSearch = useCallback((newFilter: SearchFilter) => {
    setFilter(newFilter);
  }, []);

  const handleClear = useCallback(() => {
    setFilter(null);
    setSelectedFrame(null);
    setSubmissionFrame(null);
  }, []);

  const handleFrameSelect = useCallback((frame: Frame) => {
    setSubmissionFrame(frame);
    setFrameId(frame.frameId.toString());
    setVideoId(frame.videoLink);
    setTimeMs(frame.timeMs?.toString() || "");
  }, []);

  const handleFrameDetail = useCallback((frame: Frame) => {
    setSelectedFrame(frame);
  }, []);

  const handleSubmit = () => {
    setShowSubmitConfirm(true);
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <FilterPanel onSearch={handleSearch} onClear={handleClear} isLoading={isLoading} />

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        {/* Top Bar */}
        <header className="bg-surface-container-lowest border-b border-outline-variant flex justify-between items-center px-container-padding w-full h-topbar-height shrink-0 z-20">
          <div className="flex items-center gap-6">
            <span className="font-headline-sm text-headline-sm font-bold text-on-surface tracking-tight">
              Frame Seeker
            </span>
            <div className="h-6 w-px bg-outline-variant hidden md:block" />

            {/* View Mode Toggle */}
            {frames.length > 0 && (
              <div className="flex items-center gap-2 mr-2 bg-surface-container-low p-1 rounded-lg border border-outline-variant">
                <button
                  onClick={() => setViewMode("grouped")}
                  className={`px-3 py-1 rounded font-label-sm text-label-sm transition-colors ${
                    viewMode === "grouped"
                      ? "bg-primary-container text-on-primary-container"
                      : "hover:bg-surface-variant text-on-surface-variant"
                  }`}
                >
                  Grouped
                </button>
                <button
                  onClick={() => setViewMode("continuous")}
                  className={`px-3 py-1 rounded font-label-sm text-label-sm transition-colors ${
                    viewMode === "continuous"
                      ? "bg-primary-container text-on-primary-container"
                      : "hover:bg-surface-variant text-on-surface-variant"
                  }`}
                >
                  Continuous
                </button>
              </div>
            )}

            {/* Submission Type Radio */}
            <div className="flex items-center gap-2 mr-4 bg-surface-container-low p-1 rounded-lg border border-outline-variant">
              {(["track", "qa", "kis"] as const).map((type) => (
                <label key={type} className="flex items-center gap-1 px-2 cursor-pointer">
                  <input
                    type="radio"
                    name="search_type"
                    checked={submissionType === type}
                    onChange={() => setSubmissionType(type)}
                    className="text-primary focus:ring-primary h-3 w-3"
                  />
                  <span className="font-label-sm text-label-sm text-on-surface-variant">
                    {type.toUpperCase()}
                  </span>
                </label>
              ))}
            </div>

            {/* Submission Inputs */}
            <div className="flex gap-2">
              <input
                className="w-20 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1.5 font-mono-sm text-mono-sm focus:border-primary focus:ring-0 outline-none transition-colors"
                type="text"
                placeholder="Frame ID"
                value={frameId}
                onChange={(e) => setFrameId(e.target.value)}
              />
              <input
                className="w-48 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1.5 font-mono-sm text-mono-sm focus:border-primary focus:ring-0 outline-none transition-colors text-ellipsis overflow-hidden whitespace-nowrap"
                type="text"
                placeholder="Video ID"
                value={videoId}
                onChange={(e) => setVideoId(e.target.value)}
              />
              <input
                className="w-40 bg-surface-container-lowest border border-outline-variant rounded px-2 py-1.5 font-mono-sm text-mono-sm focus:border-primary focus:ring-0 outline-none transition-colors"
                type="text"
                placeholder="Time (ms)"
                value={timeMs}
                onChange={(e) => setTimeMs(e.target.value)}
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleSubmit}
              className="bg-primary-container text-on-primary-container font-label-md text-label-md px-4 py-1.5 rounded hover:bg-opacity-90 transition-colors"
            >
              Submit
            </button>
            <div className="h-6 w-px bg-outline-variant mx-2" />
            <button
              onClick={() => setShowDresSettings(true)}
              className="flex items-center gap-1.5 border border-outline-variant px-3 py-1.5 rounded bg-surface-container-lowest hover:bg-surface-container-low transition-colors font-label-md text-label-md text-on-surface-variant"
            >
              <Icon name="settings" size={18} />
              DRES Settings
            </button>
          </div>
        </header>

        {/* Results */}
        <ResultsPanel
          frames={frames}
          viewMode={viewMode}
          onFrameSelect={handleFrameSelect}
          onFrameDetail={handleFrameDetail}
          isLoading={isLoading}
        />
      </div>

      {/* Dialogs */}
      {selectedFrame && (
        <FrameDetailDialog
          frame={selectedFrame}
          onClose={() => setSelectedFrame(null)}
          onSubmit={(frame) => {
            setSubmissionFrame(frame);
            setSelectedFrame(null);
            setShowSubmitConfirm(true);
          }}
        />
      )}

      {pinnedFrame && (
        <PinnedFramePreview
          frame={pinnedFrame}
          onClose={() => setPinnedFrame(null)}
        />
      )}

      {showDresSettings && (
        <DresSettingsDialog onClose={() => setShowDresSettings(false)} />
      )}

      {showSubmitConfirm && submissionFrame && (
        <SubmissionConfirmationDialog
          frame={submissionFrame}
          submissionType={submissionType}
          onClose={() => setShowSubmitConfirm(false)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add src/app/Home.tsx
git commit -m "feat: restyle Home.tsx with Lumina layout and top bar"
```

---

## Task 8: Update Theme for Remaining Components

Apply Lumina theme to frame-detail-dialog, tag-input, dres-settings, submission-confirmation.

**Files:**
- Modify: `src/components/frame-detail-dialog.tsx`
- Modify: `src/components/tag-input.tsx`
- Modify: `src/components/dres-settings-dialog.tsx`
- Modify: `src/components/submission-confirmation-dialog.tsx`

- [ ] **Step 1: Update frame-detail-dialog.tsx theme**

Replace old color classes with Lumina tokens:
- `bg-background` → `bg-surface-container-lowest`
- `text-foreground` → `text-on-surface`
- `border-border` → `border-outline-variant`
- `bg-primary` → `bg-primary-container`
- `text-primary-foreground` → `text-on-primary-container`

- [ ] **Step 2: Update tag-input.tsx theme**

Replace old badge colors:
- `bg-primary/10` → `bg-primary-container/30`
- `text-primary` → `text-on-primary-container`

- [ ] **Step 3: Update dres-settings-dialog.tsx theme**

Replace dialog colors with Lumina tokens.

- [ ] **Step 4: Update submission-confirmation-dialog.tsx theme**

Replace dialog colors with Lumina tokens.

- [ ] **Step 5: Commit**

```bash
git add src/components/frame-detail-dialog.tsx src/components/tag-input.tsx
git add src/components/dres-settings-dialog.tsx src/components/submission-confirmation-dialog.tsx
git commit -m "feat: update remaining components with Lumina theme"
```

---

## Task 9: Wire React Query for API Calls

Replace raw fetch calls with React Query hooks.

**Files:**
- Modify: `src/lib/api.ts` (add React Query hooks)
- Modify: `src/hooks/useFrameSearch.ts` (use React Query)
- Modify: `src/hooks/useFrameDetails.ts` (use React Query)
- Modify: `src/contexts/DresContext.tsx` (use React Query)

- [ ] **Step 1: Add React Query hooks to api.ts**

```ts
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "./api";
import type { SearchFilter, Frame } from "./types";

export function useFrameSearch(filter: SearchFilter | null) {
  return useQuery({
    queryKey: ["frames", filter],
    queryFn: () => (filter ? api.searchFrames(filter) : Promise.resolve([])),
    enabled: !!filter,
  });
}

export function useFrameDetail(frameId: number | null) {
  return useQuery({
    queryKey: ["frame", frameId],
    queryFn: () => (frameId ? api.getFrameDetail(frameId) : Promise.resolve(null)),
    enabled: !!frameId,
  });
}

export function useDresStatus() {
  return useQuery({
    queryKey: ["dres-status"],
    queryFn: () => api.getDresStatus(),
    refetchInterval: 30000,
  });
}

export function useDresLogin() {
  return useMutation({
    mutationFn: (creds: { username: string; password: string }) =>
      api.dresLogin(creds.username, creds.password),
  });
}

export function useDresSubmit() {
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api.dresSubmit(body),
  });
}
```

- [ ] **Step 2: Update Home.tsx to use useFrameSearch hook**

Replace the inline useQuery with the hook from api.ts.

- [ ] **Step 3: Update DresContext to use React Query hooks**

Replace manual fetch calls with useDresStatus and useDresLogin hooks.

- [ ] **Step 4: Remove old hooks (useFrameSearch.ts, useFrameDetails.ts)**

These are now replaced by React Query hooks in api.ts.

- [ ] **Step 5: Commit**

```bash
git add src/lib/api.ts src/app/Home.tsx src/contexts/DresContext.tsx
git rm src/hooks/useFrameSearch.ts src/hooks/useFrameDetails.ts
git commit -m "feat: wire React Query for API calls"
```

---

## Task 10: Add Vitest & Write Tests

Set up Vitest and write tests for core components.

**Files:**
- Create: `vitest.config.ts`
- Create: `src/__tests__/QueryBox.test.tsx`
- Create: `src/__tests__/ResultsPanel.test.tsx`
- Create: `src/__tests__/FilterPanel.test.tsx`
- Create: `src/__tests__/TagInput.test.tsx`

- [ ] **Step 1: Install Vitest and testing libraries**

```bash
cd /Users/sunny/workspace/AIChallenge2025/frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

- [ ] **Step 2: Create vitest.config.ts**

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});
```

- [ ] **Step 3: Create test setup file**

Create `src/test/setup.ts`:

```ts
import "@testing-library/jest-dom";
```

- [ ] **Step 4: Add test scripts to package.json**

```json
{
  "scripts": {
    "test": "vitest",
    "test:run": "vitest run"
  }
}
```

- [ ] **Step 5: Write TagInput test**

Create `src/__tests__/TagInput.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { TagInput } from "../components/tag-input";

describe("TagInput", () => {
  it("adds tag on Enter", () => {
    const onChange = vi.fn();
    render(<TagInput tags={[]} onChange={onChange} placeholder="Add tag..." />);
    
    const input = screen.getByPlaceholderText("Add tag...");
    fireEvent.change(input, { target: { value: "test tag" } });
    fireEvent.keyDown(input, { key: "Enter" });
    
    expect(onChange).toHaveBeenCalledWith(["test tag"]);
  });

  it("removes tag on click", () => {
    const onChange = vi.fn();
    render(<TagInput tags={["tag1", "tag2"]} onChange={onChange} placeholder="Add tag..." />);
    
    const removeButton = screen.getByLabelText("Remove tag1");
    fireEvent.click(removeButton);
    
    expect(onChange).toHaveBeenCalledWith(["tag2"]);
  });
});
```

- [ ] **Step 6: Write QueryBox test**

Create `src/__tests__/QueryBox.test.tsx`:

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryBox } from "../components/query-box";
import type { BoxQuery } from "../lib/types";

const mockQuery: BoxQuery = {
  id: "1",
  type: "text",
  content: "",
  enabled: true,
};

describe("QueryBox", () => {
  it("renders text input by default", () => {
    render(
      <QueryBox query={mockQuery} onUpdate={vi.fn()} onRemove={vi.fn()} canRemove={true} />
    );
    expect(screen.getByPlaceholderText("Enter query text...")).toBeInTheDocument();
  });

  it("toggles enable/disable", () => {
    const onUpdate = vi.fn();
    render(
      <QueryBox query={mockQuery} onUpdate={onUpdate} onRemove={vi.fn()} canRemove={true} />
    );
    
    const toggle = screen.getByRole("checkbox");
    fireEvent.click(toggle);
    
    expect(onUpdate).toHaveBeenCalledWith({ enabled: false });
  });

  it("calls onRemove when delete clicked", () => {
    const onRemove = vi.fn();
    render(
      <QueryBox query={mockQuery} onUpdate={vi.fn()} onRemove={onRemove} canRemove={true} />
    );
    
    const deleteButton = screen.getByRole("button", { name: /delete/i });
    fireEvent.click(deleteButton);
    
    expect(onRemove).toHaveBeenCalled();
  });
});
```

- [ ] **Step 7: Write ResultsPanel test**

Create `src/__tests__/ResultsPanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { ResultsPanel } from "../components/results-panel";
import type { Frame } from "../lib/types";

const mockFrames: Frame[] = [
  { frameId: 1, videoLink: "K01_V001", thumbnailPath: "/thumb1.jpg", timeMs: 1000 },
  { frameId: 2, videoLink: "K01_V001", thumbnailPath: "/thumb2.jpg", timeMs: 2000 },
  { frameId: 3, videoLink: "K02_V001", thumbnailPath: "/thumb3.jpg", timeMs: 3000 },
];

describe("ResultsPanel", () => {
  it("shows empty state when no frames", () => {
    render(
      <ResultsPanel
        frames={[]}
        viewMode="grouped"
        onFrameSelect={vi.fn()}
        onFrameDetail={vi.fn()}
      />
    );
    expect(screen.getByText("Start Searching")).toBeInTheDocument();
  });

  it("renders frames in grouped mode", () => {
    render(
      <ResultsPanel
        frames={mockFrames}
        viewMode="grouped"
        onFrameSelect={vi.fn()}
        onFrameDetail={vi.fn()}
      />
    );
    expect(screen.getAllByRole("img")).toHaveLength(3);
  });

  it("shows loading skeleton", () => {
    render(
      <ResultsPanel
        frames={[]}
        viewMode="grouped"
        onFrameSelect={vi.fn()}
        onFrameDetail={vi.fn()}
        isLoading={true}
      />
    );
    expect(screen.queryByText("Start Searching")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 8: Run tests**

```bash
cd /Users/sunny/workspace/AIChallenge2025/frontend
npm run test:run
```

Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add vitest.config.ts src/test/ src/__tests__/ package.json
git commit -m "test: add Vitest and component tests"
```

---

## Task 11: Final Verification

Run build, lint, and typecheck to ensure everything works.

- [ ] **Step 1: Run TypeScript typecheck**

```bash
cd /Users/sunny/workspace/AIChallenge2025/frontend
npx tsc --noEmit
```

Expected: No type errors.

- [ ] **Step 2: Run ESLint**

```bash
npm run lint
```

Expected: No lint errors.

- [ ] **Step 3: Run build**

```bash
npx vite build
```

Expected: Build succeeds.

- [ ] **Step 4: Run all tests**

```bash
npm run test:run
```

Expected: All tests pass.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: Lumina frontend redesign complete"
```
