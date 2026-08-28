# Search Settings and Keyboard Navigation

## Purpose

This change consolidates search-wide controls in the **Setting** dialog and
adds keyboard-first controls for constructing queries and inspecting frames.
The goal is to keep each Query Box focused on query content while making
behaviour that applies to every search explicit in one place.

## Setting dialog

The former **Model Settings** entry is now named **Setting**. It still owns
model selection, model load/unload, and an optional Milvus collection override.
It also now contains the following search-wide controls:

| Control | Default | Scope |
| --- | --- | --- |
| Keyboard seek step | `0.2` seconds | Frame Detail precise seeking |
| Max consecutive gap | `90` seconds | Temporal search path construction |
| OCR query mode | `Match phrase` | Every OCR keyword filter |
| ASR query mode | `Match` | Every ASR keyword filter |

OCR and ASR each retain their advanced Elasticsearch options: token operator,
minimum should match, fuzzy matching, prefix length, maximum expansions, and
phrase slop. The dialog is scrollable so all controls remain available on
short viewports.

OCR and ASR settings are stored in `sessionStorage` under `ocrSearchConfig`
and `asrSearchConfig`. They remain active after closing the dialog or opening a
new Query Box, but reset when the browser session ends.

### Search request mapping

Each Query Box still owns its OCR/ASR keyword lists and the AND/OR relationship
between keyword chips. Query mode and advanced options are now global rather
than per-box. When a box has OCR or ASR keywords, the active global setting is
translated from the frontend camelCase shape to the backend API's snake_case
shape and included in that source's `*_search_config` field. No search config
is sent for an empty keyword source.

## Query construction improvements

The sidebar now tracks an active Query Box. New text boxes are focused
immediately, and the first query is focused when the page loads. The active box
is updated whenever focus enters it.

| Shortcut | Action |
| --- | --- |
| `Alt + Q` | Focus the active query text input |
| `Alt + V` | Focus Video ID search |
| `Alt + 1` ... `Alt + 9` | Focus query by position |
| `Alt + O` / `Alt + S` | Open and focus OCR / ASR keyword input in the active query |
| `Alt + N` | Add and focus a new query |
| `Alt + E` | Toggle AI Enhance for the active query |
| `Alt + Up` / `Alt + Down` | Move the active query within the sidebar |
| `Alt + [` / `Alt + ]` | Decrease / increase result grid columns |
| `Ctrl + Enter` | Run search |

Keyword inputs now accept an explicit DOM id for keyboard focus. When a
keyword input is empty, `Backspace` removes its most recent keyword chip.

The Video ID autocomplete supports `ArrowUp`, `ArrowDown`, `Enter`, and
`Escape`. The highlighted suggestion is the one submitted on `Enter`.

## Search defaults and layout

AI Enhance is now opt-in for newly created and cleared Query Boxes. The maximum
consecutive temporal gap was moved from the sidebar to Setting, where it is
shared by all searches. The sidebar retains its temporal mode selector and the
keyboard grid controls.

## Frame Detail navigation

Frame Detail now accepts the configurable keyboard seek step and shares frame
selection logic between filmstrip clicks and keyboard navigation.

| Shortcut | Action |
| --- | --- |
| `Alt + Left` / `Alt + Right` | Select the previous / next loaded keyframe |
| `Alt + Shift + Left` / `Alt + Shift + Right` | Seek video playback by the configured step without changing the selected keyframe |

Precise seeking is captured before native video controls consume the shortcut.
It changes playback time only; frame selection and submission fields are left
unchanged. Both navigation modes ignore editable controls such as input,
textarea, and select elements.

## Source files

- `apps/web/src/app/page.tsx` owns session-wide setting state, exposes the
  Setting entry point, and documents the new shortcuts.
- `apps/web/src/components/model-settings-dialog.tsx` renders Setting and the
  global OCR/ASR controls.
- `apps/web/src/components/keyword-search-options.tsx` defines the OCR/ASR
  defaults and renders query-mode/advanced Elasticsearch controls.
- `apps/web/src/components/filter-panel.tsx` passes global configs into each
  search request and implements active-query and autocomplete keyboard flows.
- `apps/web/src/components/query-box.tsx` removes per-box advanced configs and
  supports focused OCR/ASR keyword entry.
- `apps/web/src/components/tag-input.tsx` supports focus ids and deleting the
  final tag with `Backspace`.
- `apps/web/src/hooks/use-temporal-search.ts` maps global OCR/ASR settings to
  backend request fields.
- `apps/web/src/components/frame-detail-dialog.tsx` implements keyframe
  navigation and precise video seeking.

## Verification

Run the production frontend verification from `apps/web`:

```bash
pnpm.cmd build
```
