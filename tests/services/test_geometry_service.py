"""Unit tests for radiarch.services.geometry.GeometryService.

We stub out ``_load`` so these tests never touch OpenTPS or real DICOM;
they exercise the processing pipeline (HU conversion → optional resample
→ rasterization → persistence) on synthetic CT + fake contours.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest

from radiarch.models.geometry import (
    GeometryBuildRequest,
    GridSpec,
    HUDensityModel,
    PatientRef,
)
from radiarch.services.geometry import GeometryService, _LoadedCT
from radiarch.services.persistence import _read_nifti


# ---------------------------------------------------------------------------
# Synthetic CT + fake contours
# ---------------------------------------------------------------------------

@dataclass
class _FakePatient:
    name: str = "TEST"
    rtStructs: list = field(default_factory=list)


@dataclass
class _FakeCT:
    imageArray: np.ndarray
    origin: Tuple[float, float, float]
    spacing: Tuple[float, float, float]
    patient: _FakePatient
    seriesInstanceUID: str = "1.2.3.4"
    studyInstanceUID: str = "1.2.3"
    frameOfReferenceUID: str = "1.2.3.9"


@dataclass
class _FakeMask:
    imageArray: np.ndarray


@dataclass
class _FakeContour:
    name: str
    mask: np.ndarray

    def getBinaryMask(self, origin, gridSize, spacing):
        # Ignore geometry args — tests build masks sized to the target grid.
        return _FakeMask(imageArray=self.mask.astype(bool))


def _water_ct(size=(10, 10, 10)) -> np.ndarray:
    """HU=0 everywhere (water) with a HU=50 soft-tissue 'target' blob."""
    arr = np.zeros(size, dtype=np.int16)
    arr[3:7, 3:7, 3:7] = 50
    return arr


def _build_loaded_ct(
    ct_array: np.ndarray,
    origin=(0.0, 0.0, 0.0),
    spacing=(1.0, 1.0, 1.0),
    contours: List[_FakeContour] | None = None,
) -> _LoadedCT:
    ct = _FakeCT(
        imageArray=ct_array,
        origin=origin,
        spacing=spacing,
        patient=_FakePatient(),
    )
    return _LoadedCT(ct=ct, patient=ct.patient, contours=contours or [])


def _simple_request(**overrides) -> GeometryBuildRequest:
    base = dict(
        patient_ref=PatientRef(
            dicom_study_uid="1.2.3",
            ct_series_uid="1.2.3.4",
            rtstruct_uid="1.2.3.5",
        ),
        grid_spec=None,  # inherit from CT
        hu_to_density_model=HUDensityModel.linear,
        structure_name_map=None,
    )
    base.update(overrides)
    return GeometryBuildRequest(**base)


# ---------------------------------------------------------------------------
# Happy path — identity grid, no resample
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_builds_end_to_end_with_identity_grid(self, tmp_path: Path, monkeypatch) -> None:
        ct_array = _water_ct()
        ptv = np.zeros(ct_array.shape, dtype=bool)
        ptv[3:7, 3:7, 3:7] = True
        loaded = _build_loaded_ct(ct_array, contours=[_FakeContour("PTV", ptv)])

        service = GeometryService(base_dir=tmp_path)
        monkeypatch.setattr(service, "_load", lambda _req: loaded)

        result = service.build(_simple_request())

        # Sanity: grid matches the CT, structure_index has PTV=1.
        assert result.grid_spec.size == ct_array.shape
        assert result.grid_spec.spacing_mm == (1.0, 1.0, 1.0)
        assert result.structure_index == {"PTV": 1}
        assert result.frame_of_reference_uid == "1.2.3.9"

        # Files on disk.
        density, spec = _read_nifti(Path(result.density_grid_uri))
        masks, _ = _read_nifti(Path(result.structure_masks_uri))
        assert density.shape == ct_array.shape
        assert masks.shape == ct_array.shape

        # Linear HU model: ρ = 1 + HU/1000 = 1 at HU=0 (clamped to 0 floor).
        np.testing.assert_allclose(density[0, 0, 0], 1.0, atol=1e-5)
        # Inside the blob (HU=50) → ρ = 1.05.
        np.testing.assert_allclose(density[5, 5, 5], 1.05, atol=1e-5)

    def test_ct_metadata_populated(self, tmp_path: Path, monkeypatch) -> None:
        loaded = _build_loaded_ct(_water_ct())
        service = GeometryService(base_dir=tmp_path)
        monkeypatch.setattr(service, "_load", lambda _req: loaded)

        result = service.build(_simple_request())
        assert result.ct_metadata.patient_name == "TEST"
        assert result.ct_metadata.modality == "CT"
        assert result.ct_metadata.num_slices == 10
        assert result.ct_metadata.series_instance_uid == "1.2.3.4"
        assert result.ct_metadata.study_instance_uid == "1.2.3"


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

class TestCaching:
    def test_second_build_hits_cache(self, tmp_path: Path, monkeypatch) -> None:
        loaded = _build_loaded_ct(_water_ct())
        service = GeometryService(base_dir=tmp_path)

        load_calls = {"n": 0}

        def _counting_load(_req):
            load_calls["n"] += 1
            return loaded

        monkeypatch.setattr(service, "_load", _counting_load)

        req = _simple_request()
        r1 = service.build(req)
        r2 = service.build(req)

        assert r1.geometry_id == r2.geometry_id
        assert load_calls["n"] == 1, "cache hit must skip the DICOM load"

    def test_different_hu_model_misses_cache(self, tmp_path: Path, monkeypatch) -> None:
        loaded = _build_loaded_ct(_water_ct())
        service = GeometryService(base_dir=tmp_path)
        monkeypatch.setattr(service, "_load", lambda _req: loaded)

        r1 = service.build(_simple_request(hu_to_density_model=HUDensityModel.linear))
        r2 = service.build(_simple_request(hu_to_density_model=HUDensityModel.schneider))

        assert r1.geometry_id != r2.geometry_id
        assert r1.cache_key != r2.cache_key


# ---------------------------------------------------------------------------
# Grid resampling path
# ---------------------------------------------------------------------------

class TestCustomGrid:
    def test_target_grid_spacing_triggers_resample(self, tmp_path: Path, monkeypatch) -> None:
        ct_array = _water_ct()
        loaded = _build_loaded_ct(ct_array, spacing=(2.0, 2.0, 2.0))
        service = GeometryService(base_dir=tmp_path)
        monkeypatch.setattr(service, "_load", lambda _req: loaded)

        # Request a 1mm grid → density must be resampled (2× upsample per axis).
        target = GridSpec(
            spacing_mm=(1.0, 1.0, 1.0),
            origin_mm=(0.0, 0.0, 0.0),
            size=(19, 19, 19),
        )
        # No contours so the rasterizer doesn't need mask fakes sized to the target.
        req = _simple_request(grid_spec=target)
        result = service.build(req)

        assert result.grid_spec.spacing_mm == (1.0, 1.0, 1.0)
        assert result.grid_spec.size == (19, 19, 19)
        density, _ = _read_nifti(Path(result.density_grid_uri))
        assert density.shape == (19, 19, 19)

    def test_partial_grid_inherits_missing_fields(self, tmp_path: Path, monkeypatch) -> None:
        """User supplies spacing only → origin + size adopted from CT."""
        ct_array = _water_ct()
        loaded = _build_loaded_ct(ct_array, spacing=(2.0, 2.0, 2.0), origin=(5.0, 5.0, 5.0))
        service = GeometryService(base_dir=tmp_path)
        monkeypatch.setattr(service, "_load", lambda _req: loaded)

        partial = GridSpec(spacing_mm=(2.0, 2.0, 2.0))
        result = service.build(_simple_request(grid_spec=partial))

        # Should fall back to CT origin + size → identity path (no resample).
        assert result.grid_spec.origin_mm == (5.0, 5.0, 5.0)
        assert result.grid_spec.size == ct_array.shape


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_rejects_2d_ct(self, tmp_path: Path, monkeypatch) -> None:
        ct_array = np.zeros((4, 4), dtype=np.int16)  # 2D
        loaded = _build_loaded_ct(ct_array)
        service = GeometryService(base_dir=tmp_path)
        monkeypatch.setattr(service, "_load", lambda _req: loaded)

        with pytest.raises(ValueError, match="must be 3D"):
            service.build(_simple_request())


# ---------------------------------------------------------------------------
# Load-path selection
# ---------------------------------------------------------------------------

class _MockAdapter:
    """Adapter stand-in used to probe _load's branching logic."""

    def __init__(self, *, can_retrieve: bool) -> None:
        self._can = can_retrieve

    def can_retrieve_instances(self) -> bool:
        return self._can


class TestLoadPathSelection:
    def test_falls_back_to_disk_when_adapter_cannot_retrieve(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Mock-mode adapter → disk loader, not DicomFetcher."""
        service = GeometryService(base_dir=tmp_path, adapter=_MockAdapter(can_retrieve=False))
        calls = {"disk": 0, "pacs": 0}

        def fake_disk(_root):
            calls["disk"] += 1
            return _build_loaded_ct(_water_ct())

        def fake_pacs(_fetcher, _req):  # pragma: no cover — must not be called
            calls["pacs"] += 1
            raise AssertionError("_load_from_pacs must not be invoked in mock mode")

        monkeypatch.setattr(service, "_load_from_disk", fake_disk)
        monkeypatch.setattr(service, "_load_from_pacs", fake_pacs)

        service.build(_simple_request())
        assert calls == {"disk": 1, "pacs": 0}

    def test_uses_pacs_when_adapter_can_retrieve(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        service = GeometryService(base_dir=tmp_path, adapter=_MockAdapter(can_retrieve=True))
        calls = {"disk": 0, "pacs": 0}

        def fake_disk(_root):  # pragma: no cover — must not be called
            calls["disk"] += 1
            raise AssertionError("_load_from_disk must not be invoked when PACS is available")

        def fake_pacs(_fetcher, _req):
            calls["pacs"] += 1
            return _build_loaded_ct(_water_ct())

        monkeypatch.setattr(service, "_load_from_disk", fake_disk)
        monkeypatch.setattr(service, "_load_from_pacs", fake_pacs)

        service.build(_simple_request())
        assert calls == {"disk": 0, "pacs": 1}

    def test_data_root_override_forces_disk_even_with_pacs(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """data_root_override is a dev/debug escape hatch — it beats PACS."""
        service = GeometryService(base_dir=tmp_path, adapter=_MockAdapter(can_retrieve=True))
        seen_root = {"value": None}

        def fake_disk(root):
            seen_root["value"] = root
            return _build_loaded_ct(_water_ct())

        monkeypatch.setattr(service, "_load_from_disk", fake_disk)
        # _load_from_pacs should never be reached — if it is, the test
        # fails because the returned _LoadedCT won't exist.
        monkeypatch.setattr(
            service,
            "_load_from_pacs",
            lambda *_args, **_kw: (_ for _ in ()).throw(
                AssertionError("PACS path must be skipped when data_root_override is set")
            ),
        )

        service.build(_simple_request(data_root_override="/tmp/fixtures"))
        assert seen_root["value"] == "/tmp/fixtures"
