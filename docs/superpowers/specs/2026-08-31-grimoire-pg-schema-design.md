# Design — Schéma PostgreSQL cible pour Grimoire

Date : 2026-08-31
Statut : spécification, aucune implémentation.
Document associé : `2026-08-31-grimoire-api-librarygateway-design.md` (API REST +
Protocols). Ce document est extrait de sa section 8.3 : le schéma PG est un sujet
distinct de l'API gateway.

Périmètre : cible de données côté `calibre_pg_sync` consommée par
`PgLibraryGateway`. Aucune écriture vers `metadata.db` Calibre.

## 1. Tables miroir du schéma Calibre

`calibre_pg_sync` transpose déjà le schéma Calibre (import + sync incrémentale) :
books, authors, publishers, series, tags, languages, data/formats, ratings,
comments — avec `library_uuid` + `local_id` (composite unique) pour fusionner
plusieurs bibliothèques, et `books.base_path` par bibliothèque pour localiser les
fichiers sur disque (EPUB, couvertures).

Cible : conserver cette structure telle quelle. `PgLibraryGateway` la consomme en
lecture pour les routes de lecture et en écriture (books et tables de jointure
books_* uniquement) pour le PATCH d'édition en masse.

## 2. Table `jobs` (nouvelle)

| Colonne | Type | Notes |
|---|---|---|
| `id` | uuid PK | généré à la création du job |
| `library_uuid` | uuid, NOT NULL | bibliothèque cible (résolue depuis le tag) |
| `action` | text, NOT NULL | `convert-markdown` \| `sync-library` (énumération serveur) |
| `status` | text, NOT NULL | `pending` \| `running` \| `done` \| `failed` \| `interrupted` |
| `params` | jsonb | paramètres du job (ex. `{"level": 7}`) |
| `outcome` | jsonb, NULL | `{"succeeded": [...], "failed": [{"id", "reason"}]}` |
| `created_at` | timestamptz, NOT NULL | |
| `started_at` | timestamptz, NULL | |
| `finished_at` | timestamptz, NULL | |

Contraintes : `outcome` non null ssi `status ∈ {done, failed}` ; index sur
(`library_uuid`, `status`, `created_at`) pour `GET /libraries/jobs`.

## 3. Règles

- `PgLibraryGateway` ne lit/écrit que ce schéma ; il ne touche jamais `metadata.db`.
- Les écritures de métadonnées (PATCH) vivent dans la même transaction que la
  lecture d'état : tout réussit ou rien.
- Un job `running` introuvable vivant au redémarrage du serveur passe en
  `interrupted` (marquage au démarrage, pas de mécanisme de reprise).
- La re-sync Calibre (source de vérité des fichiers) peut écraser des métadonnées
  modifiées via l'API : stratégie de conflit hors périmètre de ce document (voir
  points ouverts de la spec API).

## 4. Out of scope

- Migration/versionnage du schéma (aucun outil de migration dans book0 ;
  calibre_pg_sync crée le schéma à l'import — le choix d'un outil type Alembic
  reste ouvert).
- Tables de cache markdown (le cache est disque côté serveur API, pas en PG).
