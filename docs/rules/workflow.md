# Workflow Rules

## Git Strategy

Trunk-based development with main branch.

## Branch Naming

```
feat/<short-description>     # New features
fix/<short-description>      # Bug fixes
refactor/<short-description> # Code refactoring
docs/<short-description>     # Documentation changes
test/<short-description>     # Test additions/fixes
```

Examples:
- `feat/dres-kis-submission`
- `fix/milvus-timeout-handling`
- `refactor/search-service-extraction`

## Commit Messages

Conventional commits format:

```
<type>(<scope>): <description>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring (no feature change)
- `docs`: Documentation only
- `test`: Adding/fixing tests
- `chore`: Maintenance tasks
- `style`: Code style changes (formatting, no logic change)

Examples:
- `feat(search): add text-based vector search endpoint`
- `fix(embed): handle invalid image format gracefully`
- `refactor(routes): extract search logic to service layer`

## Pull Requests

### Requirements
- Descriptive title and description
- At least 1 human review required before merge
- All CI checks must pass (when CI is configured)
- Squash merge into main

### PR Description Template

```markdown
## What
Brief description of changes.

## Why
Context for why this change is needed.

## How
Key implementation decisions (if non-obvious).

## Testing
How this was tested.
```

## Code Review Checklist

Before submitting PR:
- [ ] Code follows style rules (Ruff for Python, ESLint for TypeScript)
- [ ] Tests written/updated (TDD)
- [ ] No hardcoded secrets
- [ ] Error handling covers edge cases
- [ ] Docstrings/JSDoc added for public APIs
- [ ] `.env.example` updated if new env vars added
