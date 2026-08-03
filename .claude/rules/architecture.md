---
paths:
  - "app/**"
  - "tests/**"
---

# Architecture and real source layout

Before touching a file, identify which zone it belongs to. Conventions differ by zone.

## Default layered layout

> This map is a **starting point**, not a fixed spec - run `ls app/` and `ls tests/` for the
> complete list of directories before assuming one does not exist, and update this file once
> the real layout diverges.

```
app/
├── api/
│   ├── deps.py                  # shared FastAPI Depends() providers (DB session, current user...)
│   └── <version>/<resource>/    # routers grouped by API version then resource, e.g. v1/patients/
│       └── router.py            #   only orchestrates: parses request, calls a service, returns
│                                 #   a schema. No business logic, no direct ORM/session use.
├── schemas/<resource>.py         # Pydantic models: Request/Response DTOs. Never reused as ORM models.
├── services/<resource>.py        # business logic, orchestrates repositories, raises domain
│                                 #   exceptions. Framework-agnostic - no `Request`, no HTTP codes.
├── repositories/<resource>.py     # data access only: queries, persistence. No business rules.
├── models/<resource>.py           # SQLAlchemy ORM entities.
├── core/                          # config (Settings via pydantic-settings), security, logging,
│                                  #   startup/shutdown events, exception handlers
├── db/                            # engine/session factory, Alembic env, base declarative class
└── worker/                        # background tasks / Celery-RQ jobs, if the project has any

tests/
├── unit/                          # services + pure logic, all I/O mocked/faked
├── integration/                   # repositories + DB, real test database (containerized/SQLite)
└── e2e/                           # full app via httpx.AsyncClient / TestClient, real routes
```

## If the project adopts a DDD-style split instead

Some services outgrow the flat layered layout above and move to bounded contexts:

```
app/
├── domain/<context>/             # entities, value objects, domain events, <Context>RepositoryInterface
├── infrastructure/<context>/      # SQLAlchemy<Context>Repository implementing the interface, adapters
└── application/<context>/         # use cases / command-query handlers, calls domain + infra ports
```

If this project uses that split, replace the "Default layered layout" section above with the
real tree and record the dependency rule below (Domain depends on nothing, Application and
Infrastructure depend on Domain only - mirror it in an import-linter/deptrac-style config if
one exists).

## Zone rule

Identify the zone first:

- Clean zone (recently written, matches the layout above): align strictly on the existing
  pattern.
- Legacy/inherited zone (inconsistent, pre-dates this convention): do not copy bad practices.
  Propose a compliant version within the requested scope; do not launch an unrequested
  big-bang refactor.

## Dependency direction

- `api/` may depend on `services/` and `schemas/`. Never on `repositories/` or `models/`
  directly.
- `services/` may depend on `repositories/` (via interface/abstraction when one exists) and
  `schemas/`. Never on `api/`.
- `repositories/` may depend on `models/` and `db/`. Never on `services/` or `api/`.
- If an import-linter / deptrac-equivalent config exists in the project, it is authoritative -
  check it rather than guessing.
