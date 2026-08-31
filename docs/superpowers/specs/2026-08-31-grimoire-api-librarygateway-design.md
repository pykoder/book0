# Design — API REST complète Grimoire et spécification LibraryGateway

Date : 2026-08-31
Statut : spécification validée, aucune implémentation.
Périmètre : définition seule — routes REST de `book0_api` et Protocols Python de
`book0_core`. Aucune modification de code dans ce livrable.

## 1. Contexte et objectifs

Grimoire regroupe : `book0` (backend FastAPI lisant `metadata.db` Calibre en lecture
seule), `jaquette` (frontend React consommant `book0_api`), `epub2md` (conversion
EPUB → Markdown numéroté avec syntaxe d'extraction) et `calibre_pg_sync`
(transposition des bibliothèques Calibre vers PostgreSQL).

Objectif : reproduire les fonctionnalités principales de Calibre plus quelques
extensions, via une interface web à trois zones (navigation à liste à gauche,
grille/liste de livres au centre, détails du livre courant à droite), en étendant
`book0_api` et l'architecture existante de `book0`.

Fonctionnalités visées (source : `specs-api.md` à la racine de Grimoire) :

1. Listes de navigation : livres, publishers, authors, series (extensible ensuite :
   tags, commentaires, formats, langues, ISBN).
2. Affichage des livres en mode liste détaillée (id, titre, publisher, série, tome,
   date de publication) ou en grille de couvertures (titre et/ou auteur), avec
   pagination dans les deux modes.
3. Tri selon les champs, filtrage par combinaison de critères.
4. Sélection multiple (mode liste : cases à cocher ; mode grille : surlignage),
   édition en masse des propriétés des livres sélectionnés.
5. Actions en tâche de fond sur la sélection, comptes rendus consultables ensuite.
6. Valeurs possibles d'une propriété (facettes).
7. Zone de détails : méta-données ou contenu Markdown (conversion façon epub2md)
   avec filtrage du contenu par la syntaxe d'extraction d'epub2md.

## 2. Décisions structurantes

| Décision | Choix |
|---|---|
| Support des écritures | PostgreSQL via `calibre_pg_sync` — PG devient le catalogue principal de l'API |
| Sync retour vers Calibre | Non. Calibre reste une source d'import/sync à sens unique dans cette version |
| Service | `book0_api` évolue : mêmes principes, routes existantes conservées et étendues |
| Protocols | Deux Protocols (`ReadLibraryGateway`, `MutableCatalogGateway`), une seule implémentation PG qui les réalise tous les deux. Lecture et écriture visent la même base PG |
| `metadata.db` | Reste strictement read-only ; `SqliteLibraryGateway` n'implémente que la partie lecture, pour les CLIs existants |
| Fichiers (EPUB, couvertures) | Restent sur disque (répertoires Calibre), localisés via `base_path` enregistré en PG à l'import |
| Markdown | Conversion serveur (epub2md intégré à `book0_api`, avec cache disque) + extraction serveur |
| Filtrage | Paramètres structurés (pas la syntaxe de recherche Calibre), convention compacte « `,` liste / `-` intervalle » (§5) |
| Édition en masse | Synchrone (`PATCH`), transactionnelle |
| Tâches de fond | Jobs asynchrones persistés en PG, exécutés via `BackgroundTasks`, comptes rendus consultables |
| Authentification | Aucune (cohérent avec l'existant) |

## 3. Architecture

```
jaquette (React) ──HTTP──> book0_api (FastAPI) ──> Protocols book0_core
                                                     ├── ReadLibraryGateway
                                                     │     ├── SqliteLibraryGateway (CLIs)
                                                     │     └── PgLibraryGateway
                                                     └── MutableCatalogGateway
                                                           └── PgLibraryGateway (seule impl.)

calibre_pg_sync ──import/sync──> PostgreSQL   <── jobs, rapports, cache markdown
Répertoires Calibre (EPUB, images) : lus sur disque via base_path stocké en PG
```

- Les routes de `book0_api` restent en `def` (pas `async def`) : I/O bloquantes
  (`psycopg`, `sqlite3`, disque) exécutées par les workers threadpool de FastAPI.
- Direction des dépendances inchangée : `book0_core` ne dépend d'aucun framework ;
  `book0_api` dépend de `book0_core` (+ `book0_config`) ; tout le SQL PG vit dans un
  unique module `book0_core/pg_gateway.py` (aucun autre module n'ouvre de connexion PG).
- `jaquette` régénère ses types via `pnpm gen:api-types` (openapi-typescript) après
  évolution du schéma OpenAPI.

## 4. Modèle de domaine (`book0_core/models.py`)

`Book` est enrichi pour servir le mode liste ET le mode grille avec un seul endpoint :

```python
@dataclass(frozen=True)
class Book:
    id: str                      # id Calibre (opaque, numérique positif)
    title: str
    authors: tuple[str, ...]
    pubdate: str | None
    publisher: Publisher | None  # nouveaux champs (tous optionnels pour rétrocompat)
    series: Series | None
    series_index: str | None     # « tome » dans la série
    rating: int | None           # 1..5
    has_cover: bool

@dataclass(frozen=True)
class Series:                    # existait déjà ; devient ressource listable
    id: str
    name: str

@dataclass(frozen=True)
class FieldValue:
    value: str
    count: int

@dataclass(frozen=True)
class BookQuery:
    author_ids: tuple[str, ...] = ()
    publisher_ids: tuple[str, ...] = ()
    series_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    ratings: tuple[int, ...] = ()          # "1,3-5" → (1, 3, 4, 5)
    pubdate_years: tuple[int, ...] = ()    # idem sur l'année de publication
    sort: BookSort = BookSort.TITLE
    order: SortOrder = SortOrder.ASC

class BookSort(Enum):    # TITLE, PUBDATE, PUBLISHER, SERIES, SERIES_INDEX, RATING, AUTHOR
class SortOrder(Enum):   # ASC, DESC
```

Le parsing de la convention « `,` / `-` » (§5) se fait à la frontière API
(`book0_api`), jamais dans `book0_core` : le domaine reçoit des tuples développés.

Nouveaux résultats paginés : `PagedSeriesResult` (même forme que
`PagedAuthorsResult`), `PagedJobsResult` (§8).

## 5. Convention de filtrage compacte

Tous les paramètres de filtre acceptent une valeur compacte :

- `v` : valeur exacte — `?rating=4`, `?author_id=12`
- `v1,v2,...` : liste, OU logique intra-clé — `?tag=classique,science-fiction`
- `a-b` : intervalle inclusif (champs comparables uniquement : `rating`,
  `author_id`, `publisher_id`, `series_id`, `pubdate` sur l'année) — `?rating=3-5`,
  `?pubdate=2000-2005`
- Combinaison libre : `?rating=1,3-5`
- ET logique **entre** clés : `?author_id=3&tag=classique&language=fr`

Règles de validation (sinon 422 `InvalidFilterError`) :
- un intervalle n'est permis que sur un champ comparable ;
- `a` ≤ `b` dans un intervalle ;
- les valeurs texte ne contiennent ni `,` ni `-` initial (ambiguïté) — rejetées ;
- les ids sont numériques positifs (regex `[0-9]+`, cohérent avec la normalisation
  d'ids déjà spécifiée dans le TODO de book0).

## 6. Routes de lecture

Toutes acceptent `?tag=...` (résolu côté serveur vers une bibliothèque PG ;
`TagRequiredError` → 400 si ni tag ni `default-library`) et la pagination existante
`?page=`, `?page_size=` (réponse paginée avec `total_pages`/`has_more_than_shown`/
handle, comme aujourd'hui).

### 6.1 Listes de navigation (colonne gauche)

| Route | Réponse (non paginée) |
|---|---|
| `GET /libraries/books` | `BookOut[]` (enrichi) |
| `GET /libraries/authors` | `AuthorOut[]` |
| `GET /libraries/publishers` | `PublisherOut[]` |
| `GET /libraries/series` | `SeriesOut[]` (nouveau) |

`BookOut` :

```json
{ "id": "42", "title": "Dune", "authors": ["Frank Herbert"],
  "pubdate": "2001-08-02", "publisher": {"id": "3", "name": "Presses de la Cité"},
  "series": {"id": "7", "name": "Dune"}, "series_index": "1.0",
  "rating": 4, "has_cover": true }
```

- Mode liste détaillée : colonnes id, titre, publisher, série, tome, date.
- Mode grille : couverture via `GET /libraries/books/{id}/cover` (route existante,
  servie depuis le disque via `base_path`) + titre/auteur.
- Anciens champs conservés : rétrocompatibilité jaquette et CLIs distants.

Tri sur les quatre listes : `?sort=...&order=asc|desc` (whitelist serveur, défaut
`title,asc` ; pour books : `title, pubdate, publisher, series, series_index, rating,
author` ; pour authors/publishers/series : `name`).

### 6.2 Filtres

Applicables à `GET /libraries/books` (et, pour la navigation en cascade gauche →
centre, aux autres listes : `GET /libraries/authors?series_id=7` = auteurs de la
série 7, etc.). Voir §5 pour la syntaxe.

Exemple : `GET /libraries/books?tag=classique&rating=4-5&sort=pubdate&order=desc&page=2&page_size=50`

### 6.3 Valeurs possibles d'une propriété (facettes)

```
GET /libraries/values/{field}?tag=...
field ∈ tags | languages | formats | ratings
→ [ { "value": "fantasy", "count": 142 }, ... ]   (trié par count décroissant)
```

Sert à alimenter les filtres sans connaître les valeurs à l'avance. Les filtres de
liste (§6.2) peuvent s'appliquer pour obtenir les facettes d'un sous-ensemble.

### 6.4 Détails d'un livre

`POST /libraries/books/detail` — inchangée (corps `{"ids": [...]}`), réponse
`BookDetailsResultOut` enrichie des nouveaux champs.

### 6.5 Contenu Markdown (zone droite, onglet contenu)

```
GET /libraries/books/{id}/content?level=7&extract=1.2...1.4-
→ 200 { "book_id": "42", "level": 7, "extract": "1.2...1.4-", "markdown": "..." }
```

- Conversion par `epub2md` (dépendance de paquet, pas un sous-processus),
  appelée par l'implémentation PG de `MutableCatalogGateway.get_book_content`
  (§8.2) — aucune autre partie du code n'importe epub2md. L'EPUB est localisé
  sur disque via `base_path` + conventions Calibre
  (`author/series/book (id)/book.epub`).
- `level` : 1–7 (défaut 7, même sémantique qu'epub2md) ; `extract` : syntaxe
  `START...END` d'epub2md, appliquée côté serveur.
- Cache disque de la conversion par `(book_id, level, mtime EPUB)` — le cache est
  invalidé automatiquement si l'EPUB change (re-sync Calibre).
- Erreurs : 404 `BookNotFoundError` (id inconnu), 404 `NoEpubError` (pas de fichier
  EPUB), 400 `InvalidExtractError` (syntaxe d'extraction invalide).

## 7. Routes d'écriture

### 7.1 Édition en masse (synchrone)

```
PATCH /libraries/books?tag=...
Body : { "ids": ["42", "17"],
         "patch": { "publisher_id": "3",
                    "tags": ["fantasy", "classique"],
                    "series_id": "7", "series_index": "1.0",
                    "rating": 4, "pubdate": "2001-08-02",
                    "language": "fr", "comments": "..." } }
→ 200 { "updated": ["42", "17"], "missing_ids": [] }
```

- Sémantique PATCH : seuls les champs présents et non `null` dans `patch` sont
  appliqués ; les absents restent inchangés.
- Transactionnelle : tout réussit ou rien (les ids inconnus ne font pas échouer,
  ils remontent dans `missing_ids`).
- `ids` vide ou `patch` vide → 422 `InvalidPatchError`.
- Pas de PATCH unitaire distinct : un seul id couvre le livre courant.
- Champs modifiables : `publisher_id`, `series_id`, `series_index`, `tags`
  (remplace la liste), `rating`, `pubdate`, `language`, `comments`. (Titre et
  auteurs hors périmètre initial — voir « Out of scope ».)

### 7.2 Tâches de fond et comptes rendus

```
POST /libraries/jobs?tag=...
Body : { "action": "convert-markdown", "book_ids": ["42", "17"], "params": { "level": 7 } }
→ 202 { "id": "8f3a9c...", "status": "pending" }
```

- Actions initiales (énumération serveur, extensible) :
  - `convert-markdown` : pré-génère le contenu Markdown des EPUB sélectionnés
    (param `level`), pour précharger le cache de §6.5 ;
  - `sync-library` : relance l'import/sync `calibre_pg_sync` pour la bibliothèque
    du tag.
- Exécution via `BackgroundTasks` de FastAPI ; l'état du job est persisté en PG
  dès la création, donc les comptes rendus survivent aux redémarrages (un job
  `running` introuvable au redémarrage passe en `interrupted`).

```
GET /libraries/jobs?status=&action=&page=&page_size=   → PagedJobsOut (liste paginée)
GET /libraries/jobs/{id}                               → détail + compte rendu
```

```json
{ "id": "8f3a9c...", "action": "convert-markdown", "status": "done",
  "created_at": "2026-08-31T12:00:00Z", "started_at": "2026-08-31T12:00:01Z",
  "finished_at": "2026-08-31T12:00:40Z",
  "outcome": { "succeeded": ["42"],
               "failed": [ { "id": "17", "reason": "NoEpubError" } ] } }
```

- `status` ∈ `pending | running | done | failed | interrupted`.
- Pas de suppression ni de relance de job dans cette version (consultation seule).
- Erreurs : 404 `UnknownJobError`, 422 `UnknownJobActionError`.

## 8. Spécification des Protocols (`book0_core`)

### 8.1 `ReadLibraryGateway`

Étend l'esprit de l'actuel `LibraryGateway` (qui devient ce Protocol, renommé) —
implémenté par `SqliteLibraryGateway` (CLIs) **et** `PgLibraryGateway` (API) :

```python
class ReadLibraryGateway(Protocol):
    # --- méthodes existantes, conservées telles quelles ---
    def list_books(self) -> list[Book]: ...
    def list_authors(self) -> list[Author]: ...
    def list_publishers(self) -> list[Publisher]: ...
    def get_book_details(self, ids: list[str]) -> BookDetailsResult: ...
    def list_books_page(self, page: int, page_size: int,
                        handle: str | None = None) -> PagedBooksResult: ...
    def list_authors_page(self, page: int, page_size: int,
                          handle: str | None = None) -> PagedAuthorsResult: ...
    def list_publishers_page(self, page: int, page_size: int,
                             handle: str | None = None) -> PagedPublishersResult: ...
    def close_pagination(self, handle: str) -> None: ...

    # --- nouvelles méthodes ---
    def list_series(self) -> list[Series]: ...
    def list_series_page(self, page: int, page_size: int,
                         handle: str | None = None) -> PagedSeriesResult: ...
    def query_books_page(self, query: BookQuery, page: int, page_size: int,
                         handle: str | None = None) -> PagedBooksResult: ...
    def query_authors_page(self, query: BookQuery, page: int, page_size: int,
                           handle: str | None = None) -> PagedAuthorsResult: ...
    # (idem query_publishers_page, query_series_page)
    def list_field_values(self, field: Literal["tags", "languages", "formats",
                            "ratings"]) -> list[FieldValue]: ...
```

- `query_books_page` généralise `list_books_page` (une `BookQuery` vide ≡ liste
  complète triée par titre). `list_*_page` reste pour compat CLIs ; à terme les
  CLIs peuvent migrer vers `query_*_page` (hors périmètre).
- Les variantes `query_{authors,publishers,series}_page` renvoient les entités
  participant aux livres filtrés (navigation en cascade).

### 8.2 `MutableCatalogGateway`

Implémenté uniquement par `PgLibraryGateway` :

```python
class MutableCatalogGateway(Protocol):
    def edit_books(self, ids: list[str], patch: BookPatch) -> EditBooksResult: ...
    def get_book_content(self, book_id: str, level: int,
                         extract: str | None) -> BookContent: ...
    def create_job(self, request: JobRequest) -> Job: ...
    def get_job(self, job_id: str) -> Job | None: ...
    def list_jobs_page(self, status: JobStatus | None, action: JobAction | None,
                       page: int, page_size: int) -> PagedJobsResult: ...
```

```python
@dataclass(frozen=True)
class BookPatch:               # champ None = non modifié
    publisher_id: str | None = None
    series_id: str | None = None
    series_index: str | None = None
    tags: tuple[str, ...] | None = None
    rating: int | None = None
    pubdate: str | None = None
    language: str | None = None
    comments: str | None = None

@dataclass(frozen=True)
class EditBooksResult:
    updated: tuple[str, ...]
    missing_ids: tuple[str, ...]

@dataclass(frozen=True)
class BookContent:
    book_id: str
    level: int
    extract: str | None
    markdown: str

class JobAction(Enum):      # CONVERT_MARKDOWN, SYNC_LIBRARY
class JobStatus(Enum):      # PENDING, RUNNING, DONE, FAILED, INTERRUPTED

@dataclass(frozen=True)
class JobRequest:
    action: JobAction
    book_ids: tuple[str, ...] = ()
    params: Mapping[str, object] | None = None

@dataclass(frozen=True)
class Job:
    id: str
    action: JobAction
    status: JobStatus
    created_at: str
    started_at: str | None
    finished_at: str | None
    outcome: JobOutcome | None     # {succeeded: tuple[str,...],
                                   #  failed: tuple[JobFailure, ...]}
```

### 8.3 Schéma PG cible (spécification, côté calibre_pg_sync)

- Tables miroir du schéma Calibre transposé existant (books, authors, publishers,
  series, tags, languages, data/formats, ratings, comments) avec `library_uuid` +
  `local_id` (déjà en place dans calibre_pg_sync) + `base_path` par bibliothèque.
- Nouvelle table `jobs` : `id (uuid)`, `library_uuid`, `action`, `status`,
  `params (jsonb)`, `outcome (jsonb)`, `created_at`, `started_at`, `finished_at`.
- `PgLibraryGateway` ne lit/écrit que ce schéma ; il ne touche jamais `metadata.db`.

## 9. Erreurs et mapping HTTP

| Erreur domaine (`book0_core.errors`) | HTTP | Cas |
|---|---|---|
| `TagRequiredError` | 400 | ni tag ni default-library ; tag inconnu |
| `LibraryNotFoundError` | 404 | bibliothèque introuvable |
| `NotACalibreLibraryError` | 500 | fichier non conforme (lecture SQLite) |
| `BookNotFoundError` | 404 | id de livre inconnu (routes unitaires) |
| `NoEpubError` | 404 | pas de fichier EPUB (contenu markdown) |
| `InvalidExtractError` | 400 | syntaxe d'extraction invalide |
| `InvalidFilterError` | 422 | violation de la convention §5 |
| `InvalidPatchError` | 422 | corps PATCH invalide/vides |
| `UnknownJobError` | 404 | id de job inconnu |
| `UnknownJobActionError` | 422 | action de job hors énumération |

Corps d'erreur identique à l'existant : `{"error": "<ClassName>", "detail": "..."}`.
`HttpLibraryGateway` (et son homologue PG éventuel) reconstruit la même exception
côté client — la substituabilité des gateways reste la règle.

## 10. Tests (exigences, sans implémentation ici)

- Unitaires : parsing de la convention `,`/`-` (§5), validation de `BookPatch`,
  expansion des filtres, enums.
- Intégration : `PgLibraryGateway` contre une PG temporaire (fixtures
  calibre_pg_sync) — requêtes/tri/filtres/pagination, transaction PATCH, cycle de
  vie des jobs ; `SqliteLibraryGateway` mis à jour pour les nouvelles méthodes de
  lecture (fixtures SQLite existantes).
- E2E : chaque nouvelle route via `TestClient` — nominal, bornes (liste vide,
  page hors limite), erreurs (tag manquant/inconnu, filtre invalide, job inconnu,
  EPUB absent, extract invalide).
- jaquette : MSW mocks des nouvelles routes ; régénération des types OpenAPI.

## 11. Impact jaquette

- `api/` : nouveaux appels (series, values, content, PATCH, jobs) + types
  régénérés.
- Écrans : navigation série dans la colonne gauche ; bascule liste/grille au
  centre (même endpoint) ; onglet méta-données/contenu à droite avec la ligne de
  filtrage markdown (`extract`) ; panneau d'édition en masse sur la sélection ;
  vue des jobs/comptes rendus.
- La sélection, la pagination et le livre courant restent de l'état client
  (aucune route de « sélection persistée »).

## 12. Out of scope (cette version)

- Sync bidirectionnelle retour vers Calibre ; résolution des conflits de re-sync.
- Syntaxe de recherche Calibre (`search=...`) — un paramètre pourra s'ajouter
  sans casser les filtres structurés.
- Édition du titre et des auteurs en masse.
- Authentification, quotas, multi-utilisateurs.
- Suppression/relance de jobs, notifications temps réel (polling suffira).
- Extension des facettes aux commentaires et ISBN.
- Migration des CLIs vers `query_*_page`.

## 13. Points ouverts reportés au TODO

- Comportement d'un `PATCH` sur un livre modifié entre-temps par une re-sync
  (mtime/version ?) — à traiter avec la stratégie de re-sync `calibre_pg_sync`.
- Représentation d'intervalles sur des ids devenus non denses après suppression
  (l'expansion `12,17` couvre le besoin ; l'intervalle sur ids est un sucre).
