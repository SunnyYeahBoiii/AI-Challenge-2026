# TypeScript Rules

## Tooling

- **Linter:** ESLint (via Next.js)
- **Formatter:** Prettier (if configured)
- **Type Checker:** TypeScript strict mode
- **Test Framework:** Vitest or Jest (to be added)

## Code Style

- Strict TypeScript (`strict: true` in tsconfig — already configured)
- No `any` unless unavoidable — add comment justifying why
- Explicit return types on public/exported functions
- Type inference OK for internal functions
- Prefer `interface` over `type` for object shapes
- Use `as const` for literal values

## App Router Conventions

- Use App Router (not Pages Router) — already in place
- Server Components by default
- Add `'use client'` only when needed (interactivity, browser APIs, state)
- Use route groups `(groupName)` for logical grouping
- Layouts for shared UI across routes
- Loading/error states via `loading.tsx` and `error.tsx`

## Component Patterns

- Container/Presentational separation when complexity warrants
- Custom hooks for reusable stateful logic
- No prop drilling beyond 2 levels — use context or组合components
- Colocate related files (component + styles + tests)

## Styling

- Tailwind CSS utility-first (already in place)
- No inline styles
- Use `clsx` or `tailwind-merge` for conditional classes
- Component variants via `clsx`/`tailwind-merge`

## UI Components

- **Prefer shadcn/ui components** when available
- Use shadcn/ui as base, customize via Tailwind
- Only build custom components when shadcn/ui doesn't cover the need

## Error Handling

Use Result pattern (type-safe):

```typescript
// Using neverthrow or custom Result type
import { Result, ok, err } from "neverthrow";

type SearchError = { code: string; message: string };

async function searchFrames(query: string): Promise<Result<Frame[], SearchError>> {
  try {
    const response = await fetch("/api/search", { ... });
    if (!response.ok) {
      return err({ code: "SEARCH_FAILED", message: response.statusText });
    }
    const data = await response.json();
    return ok(data.results);
  } catch (e) {
    return err({ code: "NETWORK_ERROR", message: String(e) });
  }
}
```

## Testing (TDD — Strict)

- Write tests before implementation
- Coverage ≥ 80% for critical paths
- Integration tests required for: API client, search flow
- Test file naming: `<module>.test.ts` or `<module>.spec.ts`

## Docstrings

JSDoc for public/exported functions:

```typescript
/**
 * Search for frames matching text query.
 * @param query - Text query to search for
 * @param topK - Maximum number of results
 * @returns Promise resolving to search results
 */
export async function searchFrames(query: string, topK = 20): Promise<SearchResponse> {
  // ...
}
```

Internal functions: inference is sufficient, no JSDoc required.
