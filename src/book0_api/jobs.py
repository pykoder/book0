"""Exécuteur BackgroundTasks des jobs (convert-markdown, sync-library).

run_job est passé à background_tasks.add_task par la route POST
/libraries/jobs : TestClient l'exécute de façon synchrone, uvicorn dans un
worker. Il prend possession du gateway que la route lui transmet (la route ne
le ferme pas — l'exécution ayant lieu après la réponse, c'est run_job qui le
ferme, dans tous les cas). Toutes les transitions de statut passent par le
gateway (tout le SQL PG vit dans book0_core/pg_gateway.py) ; le module
n'ouvre jamais de connexion lui-même. CalibreSyncer est référencé par le nom
du module pour que les tests puissent le remplacer
(monkeypatch.setattr(book0_api.jobs, ...)).
"""

from collections.abc import Mapping
from pathlib import Path

from book0_core.models import (
    JobAction,
    JobFailure,
    JobOutcome,
    JobStatus,
)
from book0_core.pg_gateway import PgLibraryGateway
from calibre_pg_sync.syncer import CalibreSyncer

# Niveau de titres par défaut de la conversion markdown (spec §7.2).
_DEFAULT_LEVEL = 7


def run_job(
    gateway: PgLibraryGateway,
    job_id: str,
    action: JobAction,
    book_ids: tuple[str, ...],
    params: Mapping[str, object] | None = None,
) -> None:
    """pending → running → done|failed (+ outcome).

    Prend possession de gateway : l'exécution ayant lieu après la réponse de
    la route (qui ne ferme donc pas la connexion), run_job le ferme dans tous
    les cas. convert-markdown : chaque livre est traité indépendamment, une
    exception par livre devient un JobFailure reason=<nom de classe
    d'exception> sans interrompre les suivants. sync-library : un seul appel
    CalibreSyncer, une exception globale fait passer tout le job en failed.
    """
    try:
        gateway.update_job_status(job_id, JobStatus.RUNNING)
        try:
            if action is JobAction.CONVERT_MARKDOWN:
                outcome = _run_convert_markdown(gateway, book_ids, params)
            else:  # JobAction.SYNC_LIBRARY (énumération fermée côté modèle)
                outcome = _run_sync_library(gateway, book_ids)
        except Exception as error:  # noqa: BLE001 — tout échec atterrit dans le job
            gateway.update_job_status(
                job_id,
                JobStatus.FAILED,
                JobOutcome((), (JobFailure(id=job_id, reason=str(error)),)),
            )
        else:
            gateway.update_job_status(job_id, JobStatus.DONE, outcome)
    finally:
        gateway.close()


def _run_convert_markdown(
    gateway: PgLibraryGateway,
    book_ids: tuple[str, ...],
    params: Mapping[str, object] | None,
) -> JobOutcome:
    level = _level_from_params(params)
    succeeded: list[str] = []
    failed: list[JobFailure] = []
    for book_id in book_ids:
        try:
            gateway.get_book_content(book_id, level, None)
        except Exception as error:  # noqa: BLE001 — raison = classe d'exception
            failed.append(JobFailure(id=book_id, reason=type(error).__name__))
        else:
            succeeded.append(book_id)
    return JobOutcome(tuple(succeeded), tuple(failed))


def _level_from_params(params: Mapping[str, object] | None) -> int:
    if not params or "level" not in params:
        return _DEFAULT_LEVEL
    value = params["level"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"paramètre 'level' : entier attendu, obtenu : {value!r}")
    return value


def _run_sync_library(
    gateway: PgLibraryGateway, book_ids: tuple[str, ...]
) -> JobOutcome:
    syncer = CalibreSyncer(str(Path(gateway.base_path) / "metadata.db"), gateway.pg_dsn)
    syncer.run()
    return JobOutcome(tuple(book_ids), ())
