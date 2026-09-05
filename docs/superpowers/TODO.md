# TODO

Work deliberately deferred during brainstorming, code review, or implementation - not
forgotten, just not actioned yet. See `CLAUDE.md`'s "Deferred work" section for the convention:
brainstorming appends here when a design doc's "Out of scope" section defers something
concrete; the commit or plan that resolves an item removes its line.

- [ ] **Comma-splitting bug in `GROUP_CONCAT`-based aggregation.** `list_books` and
  `get_book_details` (`src/book0_core/sqlite_gateway.py`) both aggregate many-to-many fields
  via `GROUP_CONCAT(name, ', ')` + Python `.split(", ")`. A name containing the literal
  substring `", "` (e.g. Calibre's own `"Lastname, Firstname"` convention) gets silently split
  into two. Confirmed empirically during the book-details feature's final review
  (2026-08-13). Fix both queries together in one pass (fixing only one would create a second
  inconsistency) — likely `json_group_array(name)` + `json.loads()`, or an unambiguous
  delimiter instead of `", "`. See
  `docs/superpowers/specs/2026-08-12-book-details-design.md`.

- [ ] **Normalize/dedupe book ids before they reach the Gateway.** Fixes two Minor findings
  from the same final review: SQLite's numeric affinity aliases several string forms to the
  same row (`"01"`, `" 1"`, `"1.0"`, `"+1"`, `"1e0"` all match id `"1"`), and duplicate
  requested ids produce duplicate rendered rows (a CLI-level artifact, not a SQL one — `IN (1,
  1)` doesn't itself duplicate rows). Design agreed (2026-08-13): a single function in
  `book0_core`, called once in each CLI immediately after parsing `--ids`, splitting the raw
  list into valid ids (regex `[1-9]\d*`, deduped, first-seen order preserved) passed to the
  Gateway, and invalid ids that never reach the DB at all but still land in `missing_ids` —
  same user-visible treatment an unknown id already gets today. Not implemented; explicitly
  scoped for later.

- [ ] **(far future, undesigned) Multi-library support.** Identify a book by `(tag, id)`
  rather than a bare id, to support: a tag meaning a virtual library (a saved
  search/collection) rather than a physical one; a non-Calibre backend with its own native id
  scheme; a single tag spanning several physical libraries, with consequences for what the "id
  space" means for that tag. Raised as motivating context for the item above, not as a request
  to design the multi-library architecture itself — no design exists yet. Revisit via
  brainstorming when picked up.

- [ ] **(undesigned) `books-detail`'s own field projection.** The narrower remainder of the
  old "`books-detail` response projection + pagination" item, after the
  2026-08-20 list-pagination design absorbed and resolved the pagination half (paginate a
  books/authors/publishers listing, then feed that page's ids into the existing
  `get_book_details`/`--ids` flow). Still undesigned: an `--ids-only` mode, a future
  file-path/download field, description/abstract text — how a caller specifies "which
  fields"/mode (fixed enum vs. open field-selection list), and whether real query-level
  savings (skipping SQL joins per requested scope) requires forking `BookDetailsResult`'s
  shape or the `LibraryGateway` Protocol itself. No design exists yet; revisit via
  brainstorming when picked up.

- [ ] **Scalar config keys (`default-library`, `default-page-size`, etc.) should live in a
  `[general]` TOML section instead of floating at top level.** Right now they only parse
  correctly if placed before any `[table]` header, since TOML folds anything written after one
  into that table — hit exactly this way (2026-08-28) via `book0-api.toml`. Revisit via
  brainstorming; affects `book0_config/config.py` and `book0_cli_remote/config.py`.

- [ ] **epub2md's `parse_extract_spec` should raise a domain error instead of
  `argparse.ArgumentTypeError` for syntax errors.** Its semantic failures are plain
  `ValueError` (via `apply_extract`) but its syntax failures are `argparse.ArgumentTypeError`,
  forcing `book0_core/pg_gateway.py` to proxy exception types through an import-time probe
  (`_extract_syntax_error_type`) to avoid the argparse dependency forbidden for `book0_core`.
  Deferred (2026-09-03): epub2md's API is frozen by the P1 plan — revisit when an epub2md
  breaking change becomes acceptable.

- **Jobs : `book_ids` non persistés en base** — `JobRequest.book_ids` n'a pas de colonne
  `jobs` (le schéma P1 n'en prévoit pas) ; Task 6 les passe en mémoire à `run_job`, donc
  après un redémarrage on ne sait plus quels livres un job `convert-markdown` visait
  (auditabilité). Option : injecter `book_ids` dans `params` jsonb à la création.
  Deferred (2026-09-03) : aucun mécanisme de reprise des jobs pending n'existe — les jobs
  sont des enregistrements d'issues, pas du travail reprisable.

- **Jobs : hypothèse mono-serveur** — le recovery `interrupted` au démarrage marque les jobs
  `running` de TOUTES les bibliothèques du PG (gateway non scopé) ; deux instances API sur le
  même PG s'interrompraient mutuellement leurs jobs en cours. Option : marquer par instance
  (colonne owner/hostname) si le multi-serveur devient un objectif.
  Deferred (2026-09-03) : déploiement mono-serveur assumé.

- **`apply_author_name` ne met pas à jour `books.author_sort`** — après un renommage/fusion,
  la colonne de tri conserve l'ancienne graphie ; `BookSort.AUTHOR` (PG, P2 T9) lira donc
  l'ancien nom jusqu'à une resync externe. Options : recalcul de `author_sort` dans la même
  transaction, ou documenter que la fraîcheur dépend du sync Calibre.
  Deferred (2026-09-03) : le plan P3 ne demandait pas la maintenance d'author_sort.

- **Filtres structurés et facettes jamais câblés côté `book0-remote`** —
  `HttpLibraryGateway` (`src/book0_cli_remote/http_gateway.py`) lève `NotImplementedError`
  pour les 4 `query_*_page` (books/authors/publishers/series) et pour `list_field_values` :
  les filtres structurés et la route `GET /libraries/values/{field}` ne sont donc
  consommables qu'en HTTP direct (jaquette, curl), pas depuis le CLI `book0-remote`.
  Deferred (2026-09-05) : le P2 n'exigeait la parité que sur les lectures de base du CLI ;
  côté serveur, les filtres fonctionnent en mode SQLite comme en mode PG.

- **Requêtes filtrées non paginées plafonnées en silence à 100 000 lignes** — sans
  `page_size` explicite (ni `default-page-size` serveur), les routes filtrées/triées
  (`query_*_page`, y compris jobs) de `book0_api/main.py` interrogent avec
  `_QUERY_ALL_PAGE_SIZE = 100_000` : au-delà, le surplus disparaît de la réponse sans
  erreur ni avertissement. Deferred (2026-09-05) : le plafond protège le serveur d'une
  requête non bornée ; dépasser 100k lignes filtrées n'est pas un cas d'usage actuel.
