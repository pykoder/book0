---
paths:
  - "app/**/*.py"
  - "tests/**/*.py"
---

# Python / FastAPI design rules

## SOLID

- Give each class/module one responsibility. Split a service that validates AND persists AND
  notifies.
- Extend stable, tested code (interfaces via `Protocol`/ABC, FastAPI dependencies). Do not
  modify it in place to special-case a new caller.
- Keep every interface implementation substitutable: no exception outside the contract, no
  weakened behavior.
- Prefer several small, targeted `Protocol`s/ABCs over one catch-all interface.
- Depend on abstractions (repository protocols/ports) in the service layer. Never depend on
  concrete implementations (a specific ORM session, an HTTP client) there - inject them.

## KISS / DRY / YAGNI

- Ship the simplest solution that meets the real need. Do not ship an "elegant" but complex one.
- Factor out duplication only when it is proven and stable. Do not factor two occurrences that
  may diverge.
- Do not add flexibility, configuration, or abstraction "just in case". Add an abstraction layer
  only for a concrete need in the current task.

## Design patterns

- Use a pattern only when it solves a real problem present in the code. No Factory for a simple
  object; no Strategy for two fixed cases.
- Patterns common in a FastAPI codebase: Repository, Unit of Work, CQRS (Command/Query +
  handler), Dependency Injection via `Depends`, Value Object (frozen Pydantic/dataclass),
  Adapter (external API clients), Event/Listener (domain events, background tasks).
- Comment the *why* of a non-obvious pattern briefly. Do not comment the *what* - the code must
  be self-explanatory.

## Typing and Pydantic

- Type-hint every function signature (params + return). No bare `Any` unless genuinely
  polymorphic.
- Pydantic models are the boundary contract: one `schemas/` model per request/response shape.
  Never return an ORM model directly from a router.
- Use `model_config = ConfigDict(...)` (Pydantic v2) rather than the old `class Config`.
- Prefer `Annotated[Type, Field(...)]` for field metadata over bare `Field(...)` defaults when
  the project's Pydantic version supports it consistently - check existing schemas first.

## Async correctness

- Never perform blocking I/O inside `async def` - no synchronous DB drivers, no `requests`,
  no `time.sleep`. Use the async equivalents (`asyncpg`/async SQLAlchemy, `httpx.AsyncClient`,
  `asyncio.sleep`) or offload via `run_in_executor` if a sync-only library is unavoidable.
- Do not mix sync and async database sessions in the same code path.

## Coding standards

- The authoritative style/lint ruleset is **Ruff** (`pyproject.toml` / `ruff.toml`) plus
  **mypy** for type checking, and **Black**-compatible formatting (Ruff format or Black,
  whichever the project has configured). Read the config before writing; conform to it.
- Use `logging` (or the project's configured structured logger) for logging. Never leave
  `print()` debugging behind.
- This project is managed with **uv** - every command below goes through `uv run`, never a
  bare binary (see the tooling table in the root `CLAUDE.md`). After changes, run:
  - `uv run ruff check .` and `uv run ruff format .`
  - `uv run mypy app`
  and fix every new report before considering the task done.
- Adding or removing a dependency goes through `uv add <package>` / `uv add --dev <package>` /
  `uv remove <package>` - never hand-edit `pyproject.toml`'s dependency list and never `pip
  install` directly, or the lockfile (`uv.lock`) drifts from what is actually installed.
