"""Contour → multi-label voxel mask rasterization.

Given a list of RTSTRUCT contours (anything with a ``.name`` and a
``.getBinaryMask(origin, gridSize, spacing)`` method — the OpenTPS
``ROIContour`` duck-types cleanly), this module produces a single
uint16 multi-label volume on a user-supplied :class:`GridSpec`.

Design
------
* **One label per canonical name.** Aliases are collapsed first, so if
  the user passes ``structure_name_map={"PTV": ["PTV_60", "PTV60"]}``
  and the RTSTRUCT contains both ``PTV_60`` and ``PTV60``, we pick the
  first contour that hits and discard the rest with a logger.debug
  breadcrumb — rather than silently over-painting.
* **Deterministic label ordering.** Targets (PTV/GTV/CTV) always receive
  the lowest label indices. Everything else sorts alphabetically. This
  keeps mask files reproducible across builds and across machines.
* **First-match-wins overlap policy.** When two canonical contours
  overlap in a voxel, the lower-label one (earlier in the ordering)
  keeps the voxel. OAR rules generally want targets to dominate
  overlapping OARs in the mask, and our ordering guarantees that.
* **0 is reserved for background.** Labels start at 1.
"""

from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional, Protocol, Tuple

import numpy as np
from loguru import logger

from ..models.geometry import GridSpec


# ---------------------------------------------------------------------------
# Contour protocol — any object matching this shape works.
# ---------------------------------------------------------------------------

class ContourLike(Protocol):
    """Minimum shape we need from an RT contour.

    OpenTPS's ``ROIContour`` satisfies this; fakes in tests can too.
    """

    name: str

    def getBinaryMask(
        self,
        origin: Tuple[float, float, float],
        gridSize: Tuple[int, int, int],
        spacing: Tuple[float, float, float],
    ):  # -> ROIMask with .imageArray, but we only call .imageArray on it.
        ...


# ---------------------------------------------------------------------------
# Alias resolution
# ---------------------------------------------------------------------------

#: Canonical target-volume names. Case-insensitive; any contour matching
#: one of these (directly or via alias) sorts to the front of the label
#: ordering.
TARGET_CANONICAL_NAMES = ("PTV", "GTV", "CTV")


def _normalize(name: str) -> str:
    """Lowercase + strip — the invariant we compare on."""
    return name.strip().lower()


def _build_alias_lookup(
    name_map: Optional[Mapping[str, Iterable[str]]],
) -> Dict[str, str]:
    """Flatten ``{canonical: [aliases]}`` → ``{lowercase_name: canonical}``.

    Canonical names are returned in their original case so the output
    ``structure_index`` reads naturally. Both the canonical name itself
    and each alias become keys (lowercased).
    """
    lookup: Dict[str, str] = {}
    if not name_map:
        return lookup
    for canonical, aliases in name_map.items():
        lookup[_normalize(canonical)] = canonical
        for alias in aliases:
            lookup[_normalize(alias)] = canonical
    return lookup


def _resolve_canonical(contour_name: str, lookup: Dict[str, str]) -> str:
    """Alias lookup; fall back to the raw name if no mapping applies."""
    return lookup.get(_normalize(contour_name), contour_name)


# ---------------------------------------------------------------------------
# Label ordering
# ---------------------------------------------------------------------------

def _target_priority(name: str) -> int:
    """PTV=0, GTV=1, CTV=2, everything else = 100. Lower sorts first."""
    upper = name.strip().upper()
    for idx, target in enumerate(TARGET_CANONICAL_NAMES):
        # Match either exact target or "TARGET_xxx" prefix so PTV_60 still
        # reads as a target even if the alias map didn't collapse it.
        if upper == target or upper.startswith(f"{target}_") or upper.startswith(f"{target}-"):
            return idx
    return 100


def _order_canonicals(names: Iterable[str]) -> list[str]:
    """Targets first (by canonical order), then alphabetical."""
    return sorted(set(names), key=lambda n: (_target_priority(n), n.lower()))


# ---------------------------------------------------------------------------
# Rasterization
# ---------------------------------------------------------------------------

def rasterize_contours(
    contours: Iterable[ContourLike],
    target: GridSpec,
    *,
    structure_name_map: Optional[Mapping[str, Iterable[str]]] = None,
) -> Tuple[np.ndarray, Dict[str, int]]:
    """Pack ``contours`` into a single uint16 multi-label volume.

    Parameters
    ----------
    contours
        Iterable of RTSTRUCT contours. Each must have ``.name`` and
        ``.getBinaryMask(origin, gridSize, spacing)``.
    target
        Fully-specified :class:`GridSpec` (``origin_mm`` and ``size`` set).
        The mask volume is rendered on this grid directly — we do not
        resample after rasterization, to avoid label corruption.
    structure_name_map
        Optional alias map: ``{canonical: [aliases]}``.

    Returns
    -------
    (mask_volume, structure_index)
        ``mask_volume`` is a uint16 array of shape ``target.size`` with
        0 as background. ``structure_index`` is ``{canonical_name: label}``.
    """
    if not target.is_fully_specified():
        raise ValueError(
            "rasterize_contours requires a fully specified target GridSpec"
        )

    origin = tuple(float(x) for x in target.origin_mm)  # type: ignore[arg-type]
    grid_size = tuple(int(x) for x in target.size)       # type: ignore[arg-type]
    spacing = tuple(float(x) for x in target.spacing_mm)

    alias_lookup = _build_alias_lookup(structure_name_map)

    # First pass: group contours by canonical name (first-match-wins
    # within a canonical group). ``masks_by_canonical`` maps canonical
    # name → the *first* rasterized boolean mask we accept for it.
    masks_by_canonical: Dict[str, np.ndarray] = {}
    for contour in contours:
        canonical = _resolve_canonical(contour.name, alias_lookup)
        if canonical in masks_by_canonical:
            logger.debug(
                "Skipping duplicate contour %r → canonical %r (already rasterized)",
                contour.name,
                canonical,
            )
            continue
        try:
            mask_obj = contour.getBinaryMask(origin, grid_size, spacing)
        except Exception as exc:  # pragma: no cover — logged, not fatal.
            logger.warning(
                "Rasterization failed for contour %r (canonical %r): %s",
                contour.name,
                canonical,
                exc,
            )
            continue
        mask = np.asarray(mask_obj.imageArray, dtype=bool)
        if mask.shape != grid_size:
            logger.warning(
                "Contour %r mask shape %s does not match target %s — skipping",
                contour.name,
                mask.shape,
                grid_size,
            )
            continue
        masks_by_canonical[canonical] = mask

    # Second pass: assign labels deterministically and pack.
    ordered = _order_canonicals(masks_by_canonical)
    mask_volume = np.zeros(grid_size, dtype=np.uint16)
    structure_index: Dict[str, int] = {}

    for label, canonical in enumerate(ordered, start=1):
        m = masks_by_canonical[canonical]
        # First-match-wins at voxel level: only paint where current
        # label is still 0 (unclaimed).
        paint = m & (mask_volume == 0)
        mask_volume[paint] = label
        structure_index[canonical] = label

    return mask_volume, structure_index


__all__ = [
    "ContourLike",
    "TARGET_CANONICAL_NAMES",
    "rasterize_contours",
]
