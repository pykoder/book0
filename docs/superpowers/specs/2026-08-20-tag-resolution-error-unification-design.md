# Tag resolution error unification — design

## Purpose

`book0_api` (and by extension `book0-remote`) has treated a **given-but-unconfigured** tag as
a deliberate anti-enumeration case since `2026-08-04-book0-api-and-remote-cli-design.md`: `200`
+ an empty/degenerate result, so a client probing tag values can't distinguish "wrong guess"
from "right guess, empty library." `book0`'s own `--tag` never had this property — an unknown
tag has always been a hard error there. This design drops the anti-enumeration behavior as not
worth its cost (discussed and agreed: the protection is weak in practice — a client that can
reach the server at all typically already knows the valid tag set from its own config — and it
buys inconsistency between the three consumers for no real benefit) and unifies all three
(`book0`, `book0_api`, `book0-remote`) on the same error for both "no tag resolvable" and
"tag resolved but not configured."

## Error semantics

No new domain error type. `TagRequiredError` (`book0_core/errors.py`, existing since
`2026-08-13-default-tag-resolution-design.md`) is treated as covering two causes rather than
one — "unconfigured tag" is a variant of "no usable tag," not a distinct condition:

1. No tag given/resolvable at all (omitted `--tag`/`?tag=`, no `default-library` configured) —
   existing behavior, unchanged.
2. A tag was given or resolved via `default-library`, but it isn't a key in the server's/config
   file's `[libraries]` table — **new**: previously `200 []` (or the route-specific
   equivalent) on `book0_api`; now `TagRequiredError` same as case 1.

Both causes get the same message shape used today: `f"Unknown library tag: {tag!r}"` for case
2 (matching `book0_cli`'s existing wording exactly), and the existing "No tag given and no
default-library configured..." message for case 1. Same HTTP status (400), same exception
type, no new client-visible discrimination between the two causes — a caller doesn't need to
tell them apart, both mean "you didn't give me a usable tag."

One accepted edge case: a server-side `default-library` that itself isn't a key in
`[libraries]` (a config typo) now also raises `TagRequiredError` (400) via this same path, even
though it's really a server misconfiguration rather than a bad client request. No config-load-time
validation is added for this — out of scope, see below.

## `book0_api` changes

`create_app`'s inner `_resolve_db_path(tag: str | None) -> Path` (was `Path | None`) now either
returns a usable path or raises `TagRequiredError` — it never returns `None`:

```python
def _resolve_db_path(tag: str | None) -> Path:
    resolved_tag = tag if tag is not None else default_tag
    if resolved_tag is None:
        raise TagRequiredError(
            "No tag given and no default-library configured for this server"
        )
    db_path = libraries.get(resolved_tag)
    if db_path is None:
        raise TagRequiredError(f"Unknown library tag: {resolved_tag!r}")
    return db_path
```

Every route's `if db_path is None: return <empty-shaped-thing>` branch is deleted as dead code
now that `_resolve_db_path` never returns `None`:

- `list_books` / `list_authors` / `list_publishers` drop `return []`.
- `get_book_details` drops `return BookDetailsResultOut(books=[], missing_ids=body.ids)`.
- `get_book_cover` drops `return _cover_not_found(id)` for the unconfigured-tag case — an
  unconfigured tag on the cover route now also raises `TagRequiredError` (400) rather than the
  previous `CoverNotFoundError` (404). The existing `CoverNotFoundError` branches for a
  genuinely missing cover, missing file on disk, and unknown book id are untouched.

Each route's existing `except TagRequiredError` → `400` mapping (already present for case 1)
now also catches case 2, since both raise the same type from the same call site.

## `book0` (local CLI) changes

`run()`'s local unconfigured-tag handling switches from an early print-and-return to raising
the same domain error, for consistency with `book0_api` and `book0-remote`:

```python
library_path = config.libraries.get(tag)
if library_path is None:
    raise TagRequiredError(f"Unknown library tag: {tag!r}")
```

Caught by the existing `except (LibraryNotFoundError, NotACalibreLibraryError,
TagRequiredError)` block — same stderr text, same exit code as before, just going through the
shared error path instead of a local branch.

## `book0-remote` / `HttpLibraryGateway` changes

None needed. `HttpLibraryGateway` already reconstructs `TagRequiredError` generically from any
`400` response body via its `_ERROR_TYPES` dict, and `book0_cli_remote/main.py::run()` already
catches it alongside the other two domain errors.

## Superseded documentation

The following specs stated or relied on the old "unconfigured tag → empty/degenerate response"
behavior as a deliberate design choice; they are left as historical record (not edited) and are
superseded by this design on that specific point:

- `2026-08-04-book0-api-and-remote-cli-design.md`
- `2026-08-11-authors-list-design.md`
- `2026-08-12-publishers-list-design.md`
- `2026-08-12-book-details-design.md`
- `2026-08-13-default-tag-resolution-design.md`
- `2026-08-17-remote-cover-cache-design.md`

`.claude/rules/testing.md`'s boundary-case and response-branch wording is updated in place
(it's a living operational rule, not a historical record) to describe the unified behavior.
`docs/superpowers/TODO.md`'s *"book0_api's unknown-tag books-detail path echoes raw, un-deduped
ids"* item is resolved and removed by this change: the unknown-tag `books-detail` path no
longer returns a degenerate response at all, so there's nothing left to normalize.

## Testing

- `tests/e2e/test_book0_api_main.py`: the four `*_returns_empty_list_for_an_unknown_tag`-style
  tests (books/authors/publishers/details) and `get_book_cover`'s unconfigured-tag test are
  rewritten to assert `400` + `{"error": "TagRequiredError"}` instead of their previous
  `200`/`404` expectations.
- `tests/integration/test_http_gateway.py`: the matching `HttpLibraryGateway` tests are
  rewritten from asserting an empty return value to `pytest.raises(TagRequiredError)`.
- `tests/integration/test_cli_remote_main.py`: the matching `book0-remote` CLI tests are
  rewritten from asserting a "No X found" stdout message + exit 0 to asserting a non-empty
  stderr message + exit 1 (same shape as the existing `LibraryNotFoundError`/
  `TagRequiredError`(no-default) CLI tests).
- `tests/integration/test_cli_main.py`'s existing
  `test_run_reports_unknown_tag_on_stderr_and_exits_with_status_1` needs no change — it only
  asserts exit code 1 and non-empty stderr, which is unchanged.

## Out of scope

- Config-load-time validation that a server's `default-library` value is itself a key in
  `[libraries]` (would turn the misconfigured-default edge case into a startup-time fail-fast
  error instead of a per-request 400) — a real improvement, but a separate concern from
  unifying the two request-time error causes; not requested.
- Any change to the `CoverNotFoundError` branches for a genuinely missing cover, a cover file
  missing on disk, or an unknown book id — those are unrelated to tag resolution.
