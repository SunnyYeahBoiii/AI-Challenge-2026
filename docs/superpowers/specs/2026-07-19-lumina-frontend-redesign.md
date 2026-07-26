# Lumina Frontend Redesign — Design Spec

## Overview

Restyle the Frame Seeker frontend to match the Lumina Search System design. Incremental approach: keep existing component structure, update theme, replace icons, wire React Query, clean dead code.

## Scope

- **In:** Queries page (main frame search), Keyframe detail dialog, DRES integration, submission flow
- **Out:** COCO search page, History tab, Collections tab, dark mode toggle

## Tech Decisions

| Decision | Choice |
|----------|--------|
| Framework | React 18 + Vite 7 (keep) |
| UI library | shadcn/ui (keep) |
| Styling | Tailwind CSS 3.4 + Lumina tokens |
| Icons | Material Symbols (Google) — replace lucide-react |
| State | React Query for API calls, React Context for DRES |
| Testing | Vitest + @testing-library/react |
| Router | None — state-based navigation |

## 1. Theme & Design Tokens

### Colors (Tailwind config)

```ts
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
  error: "#ba1a1a",
  "on-error": "#ffffff",
  background: "#f9f9fc",
  "on-background": "#1a1c1e",
  surface: "#f9f9fc",
  "on-surface": "#1a1c1e",
  "on-surface-variant": "#3f484c",
  "surface-variant": "#e2e2e5",
  "surface-dim": "#dadadc",
  "surface-bright": "#f9f9fc",
  "surface-container-lowest": "#ffffff",
  "surface-container-low": "#f3f3f6",
  "surface-container": "#eeeef0",
  "surface-container-high": "#e8e8ea",
  "surface-container-highest": "#e2e2e5",
  outline: "#6f787d",
  "outline-variant": "#bfc8cd",
}
```

### Typography

- **Font family:** Inter (UI), JetBrains Mono (code/data)
- **Sizes:**
  - `label-sm`: 11px/14px, weight 500
  - `label-md`: 12px/16px, weight 600, letter-spacing 0.02em
  - `body-sm`: 13px/18px, weight 400
  - `body-md`: 14px/20px, weight 400
  - `mono-sm`: 12px/16px, weight 400
  - `headline-sm`: 18px/24px, weight 600

### Spacing

- Base: 4px
- Sidebar width: 320px
- Topbar height: 64px
- Gutter: 16px
- Container padding: 24px
- Stack gap: 12px

### Border Radius

- `DEFAULT`: 0.25rem (4px)
- `lg`: 0.5rem (8px)
- `xl`: 0.75rem (12px)
- `full`: 9999px

### Depth

- Tonal layering, no heavy shadows
- 1px borders for panel separation
- Subtle shadow only on active/dragged cards

## 2. Layout Structure

```
+-------------------+----------------------------------------+
| Sidebar (320px)   | Top Bar (64px height)                   |
| [fixed, left]     | [sticky, full width]                    |
|                   +----------------------------------------+
| Video ID Search   |                                        |
| Query Mode Config | Main Content (fluid)                    |
| Query Cards       | Empty state OR results grid             |
| Clear/Enter btns  |                                        |
+-------------------+----------------------------------------+
```

### Top Bar

- Left: "Frame Seeker" logo text (`headline-sm`, bold, tracking-tight)
- Separator: `h-6 w-px bg-outline-variant`
- Grouped/Continuous toggle (pill buttons, only visible when results exist)
- Radio group: Track / QA / KIS (`label-sm`)
- Input fields: Frame ID, Video ID, Time (ms), Answer — `bg-surface-container-low`, bottom border style
- Submit button: `bg-primary-container text-on-primary-container`
- Separator
- DRES Settings button: outline style with settings icon

### Sidebar

- Background: `bg-surface-container-low`
- Right border: `border-outline-variant`
- Sections:
  1. Video ID Search (movie icon + input)
  2. Query Search Mode config (search icon, Sort By dropdown, TopK input)
  3. Queries list (scrollable, `gap-stack-gap`)
  4. Clear + Enter buttons (sticky bottom)
  5. Logo icon (bottom-left, small)

### Main Content

- Background: `bg-surface-container-lowest`
- Padding: `p-container-padding`
- Overflow: `overflow-y-auto`

## 3. Query Card Component

```
+------------------------------------------+
| [Toggle]          [Drag] [Image] [Delete] |
+------------------------------------------+
| [Textarea or Image upload]               |
+------------------------------------------+
| ▸ Tags                                   |
| ▸ Keywords                               |
+------------------------------------------+
```

### Header Row

- **Toggle:** Custom pill switch, `#87ceeb` when on, `#e2e2e5` when off
- **Drag handle:** `drag_indicator` icon, `text-outline hover:text-on-surface`
- **Image mode:** `image` icon, `text-outline hover:text-on-surface`
- **Delete:** `delete` icon, `text-error opacity-70 hover:opacity-100`

### Body

- Text mode: `Textarea` with `resize-none`, transparent background, no border
- Image mode: File upload with preview, dashed border drop zone

### Footer (expandable)

- Tags row: `sell` icon + "Tags" label, click to expand TagInput
- Keywords row: `key` icon + "Keywords" label, click to expand TagInput
- Collapsed by default, expand on click

### States

- Enabled: normal styling
- Disabled: `opacity-50` on body
- Active: subtle border highlight

## 4. Results Grid

### Grouped Mode (default)

- Frames grouped by `videoLink`
- Each group: separator line (`h-px bg-outline-variant`) + horizontal flex-wrap row
- Grid: `grid-cols-2 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7 gap-2`

### Continuous Mode

- All frames in a flat grid, no grouping
- Same responsive columns as grouped

### Frame Thumbnail

- `aspect-video`, `object-cover`, `rounded-sm` (4px)
- Border: `border-outline-variant`
- Hover: `border-primary` + play icon overlay (`bg-black/40`, `play_circle`)
- Click: open frame detail dialog

### Empty State

- Centered: "Start Searching" headline + instruction text

### Loading State

- Skeleton grid: `animate-pulse rounded bg-surface-container` with `aspect-video`

## 5. Keyframe Detail Dialog

Keep existing dialog layout, update theme:

- Full-screen modal: `max-w-8xl h-[90vh]`
- **Left panel (60-65%):** YouTube player (dark bg `#111111`), metadata overlay (Time/FPS/Frame in `mono-sm`), submission form below
- **Right panel (35-40%):** Similar frames grid (3 columns), scrollable
- **Submission form:** Track/QA/KIS radio, Frame ID / Video ID / Time inputs (dark theme), Submit button
- Theme tokens updated to Lumina palette

## 6. Icons — Material Symbols

Replace all lucide-react with Material Symbols (Google):

| Usage | Icon name |
|-------|-----------|
| Video ID search | `movie` |
| Query search mode | `search` |
| Drag handle | `drag_indicator` |
| Image mode | `image` |
| Delete query | `delete` |
| Tags | `sell` |
| Keywords | `key` |
| Add query | `add` |
| DRES settings | `settings` |
| Play overlay | `play_circle` |
| Selected frame | `check` |
| Close dialog | `close` |
| Filter | `filter_list` |

Load via Google Fonts `<link>` in `index.html`.

## 7. React Query Integration

### Queries to add

```ts
// Frame search
useQuery({ queryKey: ['frames', filter], queryFn: () => api.searchFrames(filter) })

// Frame details
useQuery({ queryKey: ['frame', frameId], queryFn: () => api.getFrameDetail(frameId) })

// DRES status
useQuery({ queryKey: ['dres-status'], queryFn: () => api.getDresStatus() })

// DRES evaluation
useQuery({ queryKey: ['dres-evaluation'], queryFn: () => api.getDresEvaluation() })
```

### Mutations to add

```ts
// DRES login
useMutation({ mutationFn: (creds) => api.dresLogin(creds) })

// DRES submit
useMutation({ mutationFn: (body) => api.dresSubmit(body) })
```

### Remove

- Raw `fetch` calls in `hooks/useFrameSearch.ts`
- Raw `fetch` calls in `hooks/useFrameDetails.ts`
- Duplicate `hooks/useDresSubmission.ts` (keep `DresContext`)

## 8. Cleanup

### Delete files

- `app/actions.ts` (empty `'use server'` stub)
- `app/frame-search.tsx` (unused)
- `app/flask-test.tsx` (unused)
- `components/FlaskTest.tsx` (unused)
- `components/FrameSearch.tsx` (duplicate types)
- `hooks/useDresSubmission.ts` (duplicate DRES logic)

### Fix

- `tailwind.config.ts:100`: `pluginmates` → `plugins` (fix tailwindcss-animate)

### Remove

- `"use client"` directives (Next.js leftovers)
- Unused dependencies: `recharts`, `date-fns`, `patch-package`, `react-day-picker`, `dotenv`
- Commented-out imports in `results-panel.tsx`
- React Query `QueryClientProvider` wrapping — keep and actually use it

## 9. Testing

### Setup

- Install `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`
- Add `vitest.config.ts`
- Add test scripts to `package.json`

### Tests to write

1. `QueryBox.test.tsx` — renders text/image modes, toggle enable/disable, add/remove tags
2. `ResultsPanel.test.tsx` — renders grouped/continuous modes, empty state, loading skeleton
3. `FilterPanel.test.tsx` — video ID input, sort/topK controls, clear/enter buttons
4. `TagInput.test.tsx` — add tag on Enter, remove tag, pending input commit

## File Changes Summary

| Action | File |
|--------|------|
| Update | `tailwind.config.ts` (Lumina tokens, fix plugins) |
| Update | `globals.css` (Lumina CSS variables) |
| Update | `index.html` (Material Symbols font) |
| Update | `lib/api.ts` (React Query hooks) |
| Update | `lib/types.ts` (keep, clean duplicates) |
| Update | `app/Home.tsx` (new layout) |
| Update | `components/filter-panel.tsx` (Lumina sidebar) |
| Update | `components/results-panel.tsx` (grouped/continuous, responsive grid) |
| Update | `components/query-box.tsx` (Lumina card style) |
| Update | `components/frame-detail-dialog.tsx` (theme update) |
| Update | `components/submit-bar.tsx` (integrate into top bar) |
| Update | `components/tag-input.tsx` (theme update) |
| Update | `components/dres-settings-dialog.tsx` (theme update) |
| Update | `components/submission-confirmation-dialog.tsx` (theme update) |
| Update | `contexts/DresContext.tsx` (React Query integration) |
| Create | `vitest.config.ts` |
| Create | `src/__tests__/QueryBox.test.tsx` |
| Create | `src/__tests__/ResultsPanel.test.tsx` |
| Create | `src/__tests__/FilterPanel.test.tsx` |
| Create | `src/__tests__/TagInput.test.tsx` |
| Delete | `app/actions.ts` |
| Delete | `app/frame-search.tsx` |
| Delete | `app/flask-test.tsx` |
| Delete | `components/FlaskTest.tsx` |
| Delete | `components/FrameSearch.tsx` |
| Delete | `hooks/useDresSubmission.ts` |
