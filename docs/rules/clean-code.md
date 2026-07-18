# Clean Code Rules

## SOLID Principles

- **Single Responsibility:** Each class/function does one thing well
- **Open/Closed:** Extend behavior via composition, not modification
- **Liskov Substitution:** Subtypes must be substitutable for base types
- **Interface Segregation:** Many specific interfaces over one general-purpose
- **Dependency Inversion:** Depend on abstractions, not concretions

## DRY (Don't Repeat Yourself)

- Extract repeated logic into shared functions/modules
- Reuse existing utilities before writing new ones
- If you copy-paste more than once, refactor

## YAGNI (You Aren't Gonna Need It)

- Don't build for hypothetical future requirements
- Ship the minimum that works now
- Future you can add complexity when it's actually needed

## Boy Scout Rule

- Leave code cleaner than you found it
- Small improvements during other work: rename unclear variables, extract tiny functions, remove dead code
- No large refactors in feature PRs — separate PR for that

## Anti-Patterns (Avoid)

### Magic Numbers
```python
# Bad
if retries > 3:
    timeout = 30

# Good
MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 30

if retries > MAX_RETRIES:
    timeout = DEFAULT_TIMEOUT_SECONDS
```

### Deep Nesting
```python
# Bad
if user:
    if user.is_active:
        if user.has_permission("search"):
            if query.is_valid():
                return search(query)

# Good
if not user or not user.is_active:
    return error("Inactive user")
if not user.has_permission("search"):
    return error("Permission denied")
if not query.is_valid():
    return error("Invalid query")
return search(query)
```

### God Classes
- If a class/files exceeds ~300 lines, split it
- Extract cohesive groups of methods into separate modules

### Premature Abstraction
- Don't create abstractions until you see 3+ concrete use cases
- Concrete first, abstract when pattern is clear

## Error Handling Patterns

### Python
- Use custom exceptions for business logic errors
- Catch specific exceptions, not bare `except:`
- Log errors with context before re-raising or returning

### TypeScript
- Use Result pattern for type-safe error handling
- No裸 `throw` in async code — wrap in Result
- Error types should be descriptive and actionable

## Naming

- Variables/functions: `camelCase` (TS), `snake_case` (Python)
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Names should reveal intent — `frame_results` not `results`
- Booleans: `is_active`, `has_permission`, `should_retry`

## Functions

- Do one thing, do it well
- Maximum ~30 lines (guideline, not hard rule)
- Fewer parameters is better (3 max, use objects/dicts for more)
- Extract logic that has its own name into its own function

## Code Organization

- Related code lives together (component + styles + tests)
- Dependencies flow inward: routes → services → database
- No circular dependencies between modules
