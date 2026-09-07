# TODO

Work deliberately deferred during brainstorming, code review, or implementation - not
forgotten, just not actioned yet. See `CLAUDE.md`'s "Deferred work" section for the convention:
brainstorming appends here when a design doc's "Out of scope" section defers something
concrete; the commit or plan that resolves an item removes its line.

Note (2026-09-07) : les items référençant `book0_core`/`book0_config` (bug GROUP_CONCAT,
normalisation des ids, multi-bibliothèques, projection books-detail, clés scalaires
`[general]`, `parse_extract_spec` epub2md, `apply_author_name`/`author_sort`) ont déménagé
avec leur code vers `../book0-core/docs/superpowers/TODO.md`.

- [ ] **Jobs : `book_ids` non persistés en base** — `JobRequest.book_ids` n'a pas de colonne
  `jobs` (le schéma P1 n'en prévoit pas) ; Task 6 les passe en mémoire à `run_job`, donc
  après un redémarrage on ne sait plus quels livres un job `convert-markdown` visait
  (auditabilité). Option : injecter `book_ids` dans `params` jsonb à la création.
  Deferred (2026-09-03) : aucun mécanisme de reprise des jobs pending n'existe — les jobs
  sont des enregistrements d'issues, pas du travail reprisable.

- [ ] **Jobs : hypothèse mono-serveur** — le recovery `interrupted` au démarrage marque les jobs
  `running` de TOUTES les bibliothèques du PG (gateway non scopé) ; deux instances API sur le
  même PG s'interrompraient mutuellement leurs jobs en cours. Option : marquer par instance
  (colonne owner/hostname) si le multi-serveur devient un objectif.
  Deferred (2026-09-03) : déploiement mono-serveur assumé.

- [ ] **Filtres structurés et facettes jamais câblés côté `book0-remote`** —
  `HttpLibraryGateway` (`src/book0_cli_remote/http_gateway.py`) lève `NotImplementedError`
  pour les 4 `query_*_page` (books/authors/publishers/series) et pour `list_field_values` :
  les filtres structurés et la route `GET /libraries/values/{field}` ne sont donc
  consommables qu'en HTTP direct (jaquette, curl), pas depuis le CLI `book0-remote`.
  Deferred (2026-09-05) : le P2 n'exigeait la parité que sur les lectures de base du CLI ;
  côté serveur, les filtres fonctionnent en mode SQLite comme en mode PG.

- [ ] **Requêtes filtrées non paginées plafonnées en silence à 100 000 lignes** — sans
  `page_size` explicite (ni `default-page-size` serveur), les routes filtrées/triées
  (`query_*_page`, y compris jobs) de `book0_api/main.py` interrogent avec
  `_QUERY_ALL_PAGE_SIZE = 100_000` : au-delà, le surplus disparaît de la réponse sans
  erreur ni avertissement. Deferred (2026-09-05) : le plafond protège le serveur d'une
  requête non bornée ; dépasser 100k lignes filtrées n'est pas un cas d'usage actuel.

- [ ] **book0-django : backend Django alternatif de l'API book0.** Après le split
  book0-core / book0-cli / book0-fastapi (spec
  `2026-09-07-book0-repo-split-design.md`) : nouveau dépôt dépendant de `book0-core`,
  servant le même contrat REST que `book0_api` (lectures + lectures PG d'abord ; routes
  d'écriture différées ; schéma compatible OpenAPI pour la génération de types de
  jaquette ; lanceur `jaquette-django.sh`). Deferred (2026-09-07) : cycle propre
  brainstorming/spec/plan, à lancer une fois le split réalisé.
