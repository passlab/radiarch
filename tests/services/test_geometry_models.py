"""Unit tests for the Pydantic schemas in radiarch.models.geometry."""

from __future__ import annotations

import numpy as np
import pytest

from radiarch.models.geometry import (
    CTMetadata,
    GeometryBuildRequest,
    GeometryResult,
    GridSpec,
    HUDensityModel,
    PatientRef,
)


class TestGridSpec:
    def test_rejects_non_positive_spacing(self) -> None:
        with pytest.raises(ValueError, match="strictly positive"):
            GridSpec(spacing_mm=(1.0, 0.0, 1.0))

    def test_rejects_non_positive_size(self) -> None:
        with pytest.raises(ValueError, match="size entries"):
            GridSpec(spacing_mm=(1, 1, 1), origin_mm=(0, 0, 0), size=(0, 1, 1))

    def test_compute_affine(self) -> None:
        spec = GridSpec(
            spacing_mm=(2.0, 2.0, 3.0),
            origin_mm=(10.0, -5.0, 0.0),
            size=(4, 4, 4),
        )
        expected = np.array(
            [
                [2.0, 0.0, 0.0, 10.0],
                [0.0, 2.0, 0.0, -5.0],
                [0.0, 0.0, 3.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        np.testing.assert_allclose(spec.to_numpy_affine(), expected)

    def test_affine_requires_origin(self) -> None:
        spec = GridSpec(spacing_mm=(1, 1, 1))
        with pytest.raises(ValueError, match="origin_mm"):
            spec.compute_affine()


class TestGeometryBuildRequest:
    def _req(self, **overrides) -> GeometryBuildRequest:
        base = dict(
            patient_ref=PatientRef(
                dicom_study_uid="1.2.3",
                ct_series_uid="1.2.3.4",
                rtstruct_uid="1.2.3.5",
            ),
            grid_spec=GridSpec(
                spacing_mm=(1, 1, 1), origin_mm=(0, 0, 0), size=(64, 64, 64)
            ),
            hu_to_density_model=HUDensityModel.schneider,
            structure_name_map={"PTV": ["PTV_60", "PTV60"]},
        )
        base.update(overrides)
        return GeometryBuildRequest(**base)

    def test_cache_key_is_deterministic(self) -> None:
        k1 = self._req().compute_cache_key()
        k2 = self._req().compute_cache_key()
        assert k1 == k2

    def test_cache_key_changes_with_hu_model(self) -> None:
        a = self._req(hu_to_density_model=HUDensityModel.schneider).compute_cache_key()
        b = self._req(hu_to_density_model=HUDensityModel.linear).compute_cache_key()
        assert a != b

    def test_cache_key_invariant_to_alias_case_and_order(self) -> None:
        a = self._req(structure_name_map={"PTV": ["PTV_60", "PTV60"]}).compute_cache_key()
        b = self._req(structure_name_map={"ptv": ["ptv60", "ptv_60"]}).compute_cache_key()
        assert a == b

    def test_cache_key_ignores_data_root_override(self) -> None:
        a = self._req(data_root_override="/tmp/a").compute_cache_key()
        b = self._req(data_root_override="/tmp/b").compute_cache_key()
        assert a == b


class TestGeometryResult:
    def _spec(self) -> GridSpec:
        return GridSpec(
            spacing_mm=(1, 1, 1), origin_mm=(0, 0, 0), size=(10, 10, 10)
        )

    def _ct_meta(self) -> CTMetadata:
        return CTMetadata(patient_name="TEST", modality="CT", num_slices=10)

    def test_rejects_label_zero(self) -> None:
        with pytest.raises(ValueError, match=">= 1"):
            GeometryResult(
                geometry_id="g1",
                density_grid_uri="/tmp/d.nii.gz",
                structure_masks_uri="/tmp/m.nii.gz",
                structure_index={"PTV": 0, "Cord": 1},
                grid_spec=self._spec(),
                frame_of_reference_uid="1.2.3.9",
                ct_metadata=self._ct_meta(),
                cache_key="abc",
            )

    def test_rejects_duplicate_labels(self) -> None:
        with pytest.raises(ValueError, match="unique"):
            GeometryResult(
                geometry_id="g1",
                density_grid_uri="/tmp/d.nii.gz",
                structure_masks_uri="/tmp/m.nii.gz",
                structure_index={"PTV": 1, "Cord": 1},
                grid_spec=self._spec(),
                frame_of_reference_uid="1.2.3.9",
                ct_metadata=self._ct_meta(),
                cache_key="abc",
            )

    def test_happy_path(self) -> None:
        r = GeometryResult(
            geometry_id="g1",
            density_grid_uri="/tmp/d.nii.gz",
            structure_masks_uri="/tmp/m.nii.gz",
            structure_index={"PTV": 1, "Cord": 2},
            grid_spec=self._spec(),
            frame_of_reference_uid="1.2.3.9",
            ct_metadata=self._ct_meta(),
            cache_key="abc",
        )
        assert r.structure_index == {"PTV": 1, "Cord": 2}
