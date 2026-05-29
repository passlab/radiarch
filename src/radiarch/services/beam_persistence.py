"""On-disk persistence for Beam Model Service outputs.

Layout under ``{artifact_dir}/beam_models/``::

    beam_models/
      _index.json                    # cache_key → beam_model_id
      {beam_model_id}/
        plan.pkl                     # pickled OpenTPS plan (proton or photon)
        meta.json                    # full BeamModelResult

The plan file is whatever ``ProtonPlan`` or ``PhotonPlan`` instance the
modality builder produced; it's pickled rather than serialized to DICOM
RT to keep round-trip fidelity for the in-process dose engine. Future
work could add an alternate DICOM RT export for clinical interop.

Atomicity follows the same belt-and-suspenders pattern as
``GeometryStore``:

* writes go to a sibling ``.tmp.*`` directory and are renamed
  atomically into ``{beam_model_id}/`` on success;
* the cache index entry is written *after* the directory is in place
  (so a crash mid-write leaves orphan dirs, not dangling cache entries);
* deletes scrub the index entry first, then ``rmtree`` the directory.
"""

from __future__ import annotations

import json
import os
import pickle
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..models.beam_model import BeamModelResult


PLAN_FILENAME = "plan.pkl"
META_FILENAME = "meta.json"
INDEX_FILENAME = "_index.json"


@dataclass
class BeamModelPaths:
    """Convenience bundle of the on-disk paths for one beam model."""

    root: Path
    plan: Path
    meta: Path

    @classmethod
    def for_id(cls, base_dir: Path, beam_model_id: str) -> "BeamModelPaths":
        root = base_dir / beam_model_id
        return cls(
            root=root,
            plan=root / PLAN_FILENAME,
            meta=root / META_FILENAME,
        )


class BeamModelStore:
    """File-backed beam-model persistence with a JSON cache index.

    Concurrency story is identical to :class:`GeometryStore`: not
    process-safe across the cache index file, fine for synchronous + a
    single Celery worker. Production multi-worker deployments will want
    a DB row with a unique index on cache_key.
    """

    def __init__(self, base_dir: str | os.PathLike[str]) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ---- cache index --------------------------------------------------

    @property
    def _index_path(self) -> Path:
        return self.base_dir / INDEX_FILENAME

    def _load_index(self) -> Dict[str, str]:
        if not self._index_path.exists():
            return {}
        try:
            return json.loads(self._index_path.read_text())
        except (OSError, json.JSONDecodeError):
            # Treat a corrupt index as empty; the next successful save
            # overwrites it cleanly.
            return {}

    def _save_index(self, index: Dict[str, str]) -> None:
        tmp = self._index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(index, indent=2, sort_keys=True))
        os.replace(tmp, self._index_path)

    def lookup_by_cache_key(self, cache_key: str) -> Optional[BeamModelResult]:
        index = self._load_index()
        beam_model_id = index.get(cache_key)
        if not beam_model_id:
            return None
        return self.get_by_id(beam_model_id)

    def get_by_id(self, beam_model_id: str) -> Optional[BeamModelResult]:
        paths = BeamModelPaths.for_id(self.base_dir, beam_model_id)
        if not paths.meta.exists():
            return None
        try:
            data = json.loads(paths.meta.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return BeamModelResult.model_validate(data)

    def load_plan(self, beam_model_id: str) -> Any:
        """Read and unpickle the saved OpenTPS plan object."""
        paths = BeamModelPaths.for_id(self.base_dir, beam_model_id)
        if not paths.plan.exists():
            raise FileNotFoundError(f"plan artifact missing for {beam_model_id}")
        with paths.plan.open("rb") as fh:
            return pickle.load(fh)

    # ---- writes -------------------------------------------------------

    def save(
        self,
        *,
        beam_model_id: str,
        cache_key: str,
        plan: Any,
        result: BeamModelResult,
    ) -> BeamModelPaths:
        """Pickle plan + write meta + update cache index, all atomically."""
        paths = BeamModelPaths.for_id(self.base_dir, beam_model_id)
        with tempfile.TemporaryDirectory(
            dir=self.base_dir,
            prefix=f".{beam_model_id}.tmp.",
        ) as tmp:
            tmp_path = Path(tmp)
            tmp_plan = tmp_path / PLAN_FILENAME
            tmp_meta = tmp_path / META_FILENAME

            with tmp_plan.open("wb") as fh:
                pickle.dump(plan, fh, protocol=pickle.HIGHEST_PROTOCOL)
            tmp_meta.write_text(result.model_dump_json(indent=2))

            # Atomic replace: nuke any existing dir first (retry-safe).
            if paths.root.exists():
                shutil.rmtree(paths.root)
            os.replace(tmp_path, paths.root)
            # Recreate the tempdir reference so the context manager's
            # cleanup is a no-op (the original tmp_path has moved).
            os.makedirs(tmp_path, exist_ok=True)

        # Update the index *after* files are in place — order matters.
        index = self._load_index()
        index[cache_key] = beam_model_id
        self._save_index(index)
        return paths

    # ---- deletes ------------------------------------------------------

    def delete_by_id(self, beam_model_id: str) -> bool:
        """Remove a beam model dir and scrub its cache_key entry.

        Returns True if a model was actually deleted, False if the id
        was unknown. Safe against partial state — each step is defensive.
        """
        root = self.base_dir / beam_model_id
        if not root.exists():
            return False

        cache_key = self._read_cache_key(root)
        if cache_key is not None:
            index = self._load_index()
            if index.get(cache_key) == beam_model_id:
                index.pop(cache_key)
                self._save_index(index)

        shutil.rmtree(root, ignore_errors=True)
        return True

    def _read_cache_key(self, root: Path) -> Optional[str]:
        meta = root / META_FILENAME
        if not meta.exists():
            return None
        try:
            return json.loads(meta.read_text()).get("cache_key")
        except (OSError, json.JSONDecodeError):
            return None

    # ---- debugging helpers -------------------------------------------

    def list_ids(self) -> list[str]:
        if not self.base_dir.exists():
            return []
        return sorted(
            p.name
            for p in self.base_dir.iterdir()
            if p.is_dir() and not p.name.startswith(".") and (p / META_FILENAME).exists()
        )


__all__ = [
    "PLAN_FILENAME",
    "META_FILENAME",
    "INDEX_FILENAME",
    "BeamModelPaths",
    "BeamModelStore",
]
