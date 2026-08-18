"""Unit tests for radiarch.services.beam_persistence.

Uses a small picklable plan stand-in so we don't need OpenTPS to test
the persistence layer's contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from radiarch.models.beam_model import (
    BeamModelResult,
    FluenceElementSet,
    Modality,
    PerBeamElements,
)
from radiarch.services.beam_persistence import (
    META_FILENAME,
    PLAN_FILENAME,
    BeamModelStore,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

@dataclass
class _MockProtonPlan:
    """Minimal picklable stand-in for OpenTPS's ProtonPlan."""

    spots: int
    layers: int
    note: str = "mock proton plan"


def _make_result(plan_uri: str, cache_key: str = "abc") -> BeamModelResult:
    return BeamModelResult(
        beam_model_id="bm-1",
        geometry_id="g-1",
        modality=Modality.proton_pbs,
        fluence_elements=FluenceElementSet(
            total_count=12,
            per_beam=[PerBeamElements(beam_id="B1", element_count=12)],
        ),
        beam_model_ref_uri=plan_uri,
        machine_model_id="default",
        cache_key=cache_key,
    )


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------

class TestPickleRoundtrip:
    def test_save_then_load_plan_roundtrips(self, tmp_path: Path) -> None:
        store = BeamModelStore(tmp_path)
        plan = _MockProtonPlan(spots=42, layers=7)
        result = _make_result(str(tmp_path / "bm-1" / PLAN_FILENAME))

        store.save(beam_model_id="bm-1", cache_key="k1", plan=plan, result=result)

        loaded = store.load_plan("bm-1")
        assert loaded.spots == 42
        assert loaded.layers == 7
        assert loaded.note == "mock proton plan"

    def test_save_writes_expected_files(self, tmp_path: Path) -> None:
        store = BeamModelStore(tmp_path)
        result = _make_result(str(tmp_path / "bm-1" / PLAN_FILENAME))
        store.save(
            beam_model_id="bm-1",
            cache_key="k1",
            plan=_MockProtonPlan(spots=1, layers=1),
            result=result,
        )
        assert (tmp_path / "bm-1" / PLAN_FILENAME).exists()
        assert (tmp_path / "bm-1" / META_FILENAME).exists()


# ---------------------------------------------------------------------------
# Cache index
# ---------------------------------------------------------------------------

class TestCacheIndex:
    def _save(self, store: BeamModelStore, tmp_path: Path, beam_model_id: str, cache_key: str):
        result = _make_result(str(tmp_path / beam_model_id / PLAN_FILENAME), cache_key=cache_key)
        store.save(
            beam_model_id=beam_model_id,
            cache_key=cache_key,
            plan=_MockProtonPlan(spots=1, layers=1),
            result=result,
        )

    def test_lookup_roundtrip(self, tmp_path: Path) -> None:
        store = BeamModelStore(tmp_path)
        self._save(store, tmp_path, "bm-1", "deadbeef")
        hit = store.lookup_by_cache_key("deadbeef")
        assert hit is not None
        assert hit.beam_model_id == "bm-1"

    def test_lookup_miss_returns_none(self, tmp_path: Path) -> None:
        store = BeamModelStore(tmp_path)
        assert store.lookup_by_cache_key("nope") is None
        assert store.get_by_id("nope") is None


# ---------------------------------------------------------------------------
# Atomic retry / delete
# ---------------------------------------------------------------------------

class TestAtomicity:
    def test_save_overwrites_cleanly_on_retry(self, tmp_path: Path) -> None:
        store = BeamModelStore(tmp_path)
        result = _make_result(str(tmp_path / "bm-1" / PLAN_FILENAME))

        # First save with a small plan
        store.save(
            beam_model_id="bm-1", cache_key="k",
            plan=_MockProtonPlan(spots=1, layers=1),
            result=result,
        )
        # Second save with a different plan, same id
        store.save(
            beam_model_id="bm-1", cache_key="k",
            plan=_MockProtonPlan(spots=99, layers=99),
            result=result,
        )

        loaded = store.load_plan("bm-1")
        assert loaded.spots == 99

    def test_delete_scrubs_index_and_files(self, tmp_path: Path) -> None:
        store = BeamModelStore(tmp_path)
        result = _make_result(str(tmp_path / "bm-1" / PLAN_FILENAME), cache_key="k1")
        store.save(
            beam_model_id="bm-1", cache_key="k1",
            plan=_MockProtonPlan(spots=1, layers=1),
            result=result,
        )
        assert store.lookup_by_cache_key("k1") is not None

        deleted = store.delete_by_id("bm-1")
        assert deleted is True
        assert not (tmp_path / "bm-1").exists()
        assert store.lookup_by_cache_key("k1") is None

    def test_delete_unknown_id_returns_false(self, tmp_path: Path) -> None:
        store = BeamModelStore(tmp_path)
        assert store.delete_by_id("nope") is False


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

class TestListing:
    def test_list_ids_excludes_tmp_dirs(self, tmp_path: Path) -> None:
        store = BeamModelStore(tmp_path)
        # Simulate a leftover tmp dir from a crashed write
        (tmp_path / ".bm-2.tmp.xyz").mkdir()
        # And a directory without a meta.json (incomplete write)
        (tmp_path / "bm-3").mkdir()

        result = _make_result(str(tmp_path / "bm-1" / PLAN_FILENAME))
        store.save(
            beam_model_id="bm-1", cache_key="k",
            plan=_MockProtonPlan(spots=1, layers=1),
            result=result,
        )
        assert store.list_ids() == ["bm-1"]
