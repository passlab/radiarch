"""Unit tests for radiarch.services.rasterization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pytest

from radiarch.models.geometry import GridSpec
from radiarch.services.rasterization import (
    TARGET_CANONICAL_NAMES,
    rasterize_contours,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

@dataclass
class _FakeMask:
    imageArray: np.ndarray


@dataclass
class _FakeContour:
    """Duck-types the OpenTPS ROIContour shape we use — just .name and
    getBinaryMask. The mask is prebaked at construction; the grid args
    passed to ``getBinaryMask`` are validated in a couple of tests."""

    name: str
    mask: np.ndarray
    last_origin: Tuple[float, float, float] | None = None
    last_grid_size: Tuple[int, int, int] | None = None
    last_spacing: Tuple[float, float, float] | None = None

    def getBinaryMask(self, origin, gridSize, spacing):
        self.last_origin = origin
        self.last_grid_size = gridSize
        self.last_spacing = spacing
        return _FakeMask(imageArray=self.mask.astype(bool))


def _grid(size=(4, 4, 4)) -> GridSpec:
    return GridSpec(spacing_mm=(1.0, 1.0, 1.0), origin_mm=(0.0, 0.0, 0.0), size=size)


def _disjoint_masks() -> tuple[np.ndarray, np.ndarray]:
    ptv = np.zeros((4, 4, 4), dtype=bool)
    ptv[0:2, 0:2, 0:2] = True
    cord = np.zeros((4, 4, 4), dtype=bool)
    cord[2:4, 2:4, 2:4] = True
    return ptv, cord


# ---------------------------------------------------------------------------
# Basic packing
# ---------------------------------------------------------------------------

class TestBasicRasterization:
    def test_two_disjoint_contours_get_labels_1_and_2(self) -> None:
        ptv, cord = _disjoint_masks()
        contours = [_FakeContour("SpinalCord", cord), _FakeContour("PTV", ptv)]
        mask, index = rasterize_contours(contours, _grid())

        # PTV is a target, so it always sorts first and gets label 1.
        assert index == {"PTV": 1, "SpinalCord": 2}
        assert int(mask[0, 0, 0]) == 1
        assert int(mask[3, 3, 3]) == 2
        # Background is exactly zero everywhere else.
        claimed = np.zeros_like(mask, dtype=bool)
        claimed[0:2, 0:2, 0:2] = True
        claimed[2:4, 2:4, 2:4] = True
        assert np.all(mask[~claimed] == 0)

    def test_returns_uint16(self) -> None:
        ptv, _ = _disjoint_masks()
        mask, _ = rasterize_contours([_FakeContour("PTV", ptv)], _grid())
        assert mask.dtype == np.uint16

    def test_passes_correct_grid_args_to_contour(self) -> None:
        ptv, _ = _disjoint_masks()
        contour = _FakeContour("PTV", ptv)
        grid = GridSpec(spacing_mm=(2.0, 2.0, 3.0), origin_mm=(10.0, 20.0, -5.0), size=(4, 4, 4))
        rasterize_contours([contour], grid)

        assert contour.last_origin == (10.0, 20.0, -5.0)
        assert contour.last_grid_size == (4, 4, 4)
        assert contour.last_spacing == (2.0, 2.0, 3.0)


# ---------------------------------------------------------------------------
# Alias resolution
# ---------------------------------------------------------------------------

class TestAliasResolution:
    def test_alias_collapses_to_canonical(self) -> None:
        ptv, _ = _disjoint_masks()
        contours = [_FakeContour("PTV_60", ptv)]
        name_map = {"PTV": ["PTV_60", "PTV60"]}
        _, index = rasterize_contours(contours, _grid(), structure_name_map=name_map)
        assert index == {"PTV": 1}

    def test_alias_match_is_case_insensitive(self) -> None:
        ptv, _ = _disjoint_masks()
        contours = [_FakeContour("ptv_60", ptv)]
        name_map = {"PTV": ["PTV_60"]}
        _, index = rasterize_contours(contours, _grid(), structure_name_map=name_map)
        assert "PTV" in index

    def test_no_name_map_uses_contour_name(self) -> None:
        ptv, _ = _disjoint_masks()
        contours = [_FakeContour("BrainStem", ptv)]
        _, index = rasterize_contours(contours, _grid())
        assert index == {"BrainStem": 1}

    def test_first_contour_wins_when_aliases_collide(self) -> None:
        m1 = np.zeros((4, 4, 4), dtype=bool)
        m1[0, 0, 0] = True
        m2 = np.zeros((4, 4, 4), dtype=bool)
        m2[3, 3, 3] = True
        contours = [_FakeContour("PTV_60", m1), _FakeContour("PTV60", m2)]
        mask, index = rasterize_contours(
            contours, _grid(), structure_name_map={"PTV": ["PTV_60", "PTV60"]}
        )
        # Both alias to PTV → only the first one is rasterized.
        assert index == {"PTV": 1}
        assert int(mask[0, 0, 0]) == 1
        assert int(mask[3, 3, 3]) == 0


# ---------------------------------------------------------------------------
# Label ordering
# ---------------------------------------------------------------------------

class TestLabelOrdering:
    def test_targets_get_lowest_labels(self) -> None:
        """Given a mixed bag, PTV/GTV/CTV always sort before OARs."""
        masks = {name: np.zeros((4, 4, 4), dtype=bool) for name in ("PTV", "GTV", "CTV", "BrainStem", "Parotid")}
        # Mark distinct voxels so we can tell labels apart.
        masks["PTV"][0, 0, 0] = True
        masks["GTV"][0, 0, 1] = True
        masks["CTV"][0, 0, 2] = True
        masks["BrainStem"][0, 1, 0] = True
        masks["Parotid"][0, 1, 1] = True

        # Deliberately shuffle input order — ordering must still be
        # (PTV, GTV, CTV, BrainStem, Parotid).
        contours = [_FakeContour(n, m) for n, m in masks.items()]
        contours = contours[::-1]
        _, index = rasterize_contours(contours, _grid())

        ordered = [name for name, _ in sorted(index.items(), key=lambda kv: kv[1])]
        assert ordered == ["PTV", "GTV", "CTV", "BrainStem", "Parotid"]

    def test_target_prefix_still_counts_as_target(self) -> None:
        """PTV_Boost (without a name map) still sorts with the targets."""
        ptv_boost = np.zeros((4, 4, 4), dtype=bool); ptv_boost[0, 0, 0] = True
        oar = np.zeros((4, 4, 4), dtype=bool); oar[1, 1, 1] = True
        contours = [_FakeContour("Parotid", oar), _FakeContour("PTV_Boost", ptv_boost)]
        _, index = rasterize_contours(contours, _grid())
        assert index["PTV_Boost"] == 1
        assert index["Parotid"] == 2


# ---------------------------------------------------------------------------
# Overlap policy
# ---------------------------------------------------------------------------

class TestOverlap:
    def test_first_match_wins_at_voxel_level(self) -> None:
        """PTV and Brain overlap on (1,1,1). PTV is the target → it wins."""
        ptv = np.zeros((4, 4, 4), dtype=bool)
        ptv[0:2, 0:2, 0:2] = True
        brain = np.zeros((4, 4, 4), dtype=bool)
        brain[1:3, 1:3, 1:3] = True
        contours = [_FakeContour("Brain", brain), _FakeContour("PTV", ptv)]
        mask, index = rasterize_contours(contours, _grid())

        assert index == {"PTV": 1, "Brain": 2}
        # Overlap voxel (1,1,1): PTV claims it.
        assert int(mask[1, 1, 1]) == 1
        # Brain-only voxel (2,2,2): Brain still wins.
        assert int(mask[2, 2, 2]) == 2


# ---------------------------------------------------------------------------
# Robustness / error surfaces
# ---------------------------------------------------------------------------

class TestRobustness:
    def test_rejects_underspecified_grid(self) -> None:
        partial = GridSpec(spacing_mm=(1, 1, 1))
        with pytest.raises(ValueError, match="fully specified"):
            rasterize_contours([], partial)

    def test_empty_contours_produces_empty_index(self) -> None:
        mask, index = rasterize_contours([], _grid())
        assert index == {}
        assert mask.shape == (4, 4, 4)
        assert np.all(mask == 0)

    def test_shape_mismatch_is_skipped_not_raised(self) -> None:
        wrong_shape = np.zeros((3, 3, 3), dtype=bool)
        contours = [_FakeContour("BadMask", wrong_shape)]
        mask, index = rasterize_contours(contours, _grid())
        # Skipped with a warning; final volume is still empty.
        assert index == {}
        assert np.all(mask == 0)

    def test_target_canonical_names_export(self) -> None:
        """Guard the public constant used by tests and downstream callers."""
        assert TARGET_CANONICAL_NAMES == ("PTV", "GTV", "CTV")
