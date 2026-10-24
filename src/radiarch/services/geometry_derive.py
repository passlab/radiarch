"""Derived geometries (roadmap R4): a geometry plus structure operations.

A derived geometry keeps the parent's grid and CT, adds the structures the
operations create (expansions, erosions, rings, booleans, a couch), applies
density overrides to the density and CT grids, and records its parent and the
operations. It is cached by the parent's cache key and the operations, like a
built geometry.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple

import numpy as np
import SimpleITK as sitk
from loguru import logger

from ..models.geometry import GeometryDeriveRequest, GeometryResult, HUDensityModel, StructureOperation
from .hu_density import get_model
from .masks import BITMASK, MAX_BITMASK_STRUCTURES, set_structure, structure_mask, to_bitmask
from .persistence import GeometryPaths, GeometryStore
from .rasterization import _target_priority
from . import structure_ops as ops


class DeriveError(ValueError):
    pass


def _read(path: str) -> np.ndarray:
    return sitk.GetArrayFromImage(sitk.ReadImage(str(path)))


# v2 (R9): derived volumes were written with x and z swapped before; the version keeps those out of every cache
DERIVE_VERSION = "2"


def derive_cache_key(parent: GeometryResult, request: GeometryDeriveRequest) -> str:
    import hashlib
    return hashlib.sha256(f"{parent.cache_key}|derive-v{DERIVE_VERSION}|{request.operations_hash()}".encode("utf-8")).hexdigest()


class GeometryDeriver:
    """Apply :class:`StructureOperation` steps to a persisted geometry."""

    def __init__(self, store: GeometryStore) -> None:
        self.store = store

    def derive(self, parent: GeometryResult, request: GeometryDeriveRequest) -> GeometryResult:
        cache_key = derive_cache_key(parent, request)
        cached = self.store.lookup_by_cache_key(cache_key)
        if cached is not None:
            logger.info("Derived geometry cache hit %s → %s", cache_key[:10], cached.geometry_id)
            return cached

        density = _read(parent.density_grid_uri).astype(np.float32)
        masks_raw = _read(parent.structure_masks_uri)
        encoding = getattr(parent, "mask_encoding", "labels") or "labels"
        index: Dict[str, int] = {str(k): int(v) for k, v in parent.structure_index.items()}
        masks = to_bitmask(masks_raw, index.values(), encoding)
        ct = _read(parent.ct_grid_uri).astype(np.int16) if parent.ct_grid_uri else None
        spacing = tuple(float(v) for v in parent.grid_spec.spacing_mm)
        origin = tuple(float(v) for v in (parent.grid_spec.origin_mm or (0.0, 0.0, 0.0)))
        hu_model = get_model(parent.hu_to_density_model or HUDensityModel.stoichiometric.value)
        lower = {k.lower(): k for k in index}

        def mask_of(name: Optional[str]) -> np.ndarray:
            if name is None or name.lower() not in lower:
                raise DeriveError(f"structure {name!r} not in the geometry ({sorted(index)})")
            return structure_mask(masks, index[lower[name.lower()]], BITMASK)

        def add(name: str, mask: np.ndarray) -> None:
            nonlocal masks
            if not name:
                raise DeriveError("an operation that creates a structure needs a name")
            if name.lower() in lower:
                label = index[lower[name.lower()]]
            else:
                if len(index) >= MAX_BITMASK_STRUCTURES:
                    raise DeriveError(f"a geometry holds at most {MAX_BITMASK_STRUCTURES} structures")
                label = max(index.values(), default=0) + 1
                index[name] = label
                lower[name.lower()] = name
            masks = set_structure(masks, label, mask, BITMASK)

        applied: List[dict] = []
        for op in request.operations:
            applied.append(op.payload())
            if op.op == "expand":
                add(op.name, ops.expand(mask_of(op.source), spacing, op.margin_mm))
            elif op.op == "erode":
                add(op.name, ops.erode(mask_of(op.source), spacing, op.margin_mm))
            elif op.op == "ring":
                add(op.name, ops.ring(mask_of(op.source), spacing, op.inner_mm, op.outer_mm))
            elif op.op == "union":
                add(op.name, ops.union(*[mask_of(s) for s in op.sources]))
            elif op.op == "intersection":
                add(op.name, ops.intersection(*[mask_of(s) for s in op.sources]))
            elif op.op == "subtract":
                add(op.name, ops.subtract(mask_of(op.source), *[mask_of(s) for s in op.sources]))
            elif op.op == "couch":
                name = op.name or "Couch"
                slab = ops.couch_slab(density.shape, origin, spacing, float(op.y_top_mm), float(op.thickness_mm))
                add(name, slab)
                hu = -700.0 if op.hu is None else float(op.hu)
                density[slab] = hu_model.convert(np.full(int(slab.sum()), hu, dtype=np.float32))
                if ct is not None:
                    ct[slab] = np.int16(round(hu))
            elif op.op == "density_override":
                region = mask_of(op.source)
                if op.hu is not None:
                    hu = float(op.hu)
                    density[region] = hu_model.convert(np.full(int(region.sum()), hu, dtype=np.float32))
                    if ct is not None:
                        ct[region] = np.int16(round(hu))
                else:
                    density[region] = np.float32(op.density_g_cm3)
            else:  # pragma: no cover — validated by the model
                raise DeriveError(f"unknown op {op.op!r}")

        geometry_id = str(uuid.uuid4())
        paths = GeometryPaths.for_id(self.store.base_dir, geometry_id)
        result = GeometryResult(
            geometry_id=geometry_id,
            density_grid_uri=str(paths.density),
            structure_masks_uri=str(paths.masks),
            ct_grid_uri=str(paths.ct) if ct is not None else None,
            structure_index=index,
            mask_encoding=BITMASK,
            grid_spec=parent.grid_spec,
            frame_of_reference_uid=parent.frame_of_reference_uid,
            ct_metadata=parent.ct_metadata,
            cache_key=cache_key,
            parent_geometry_id=parent.geometry_id,
            derived_operations=list(parent.derived_operations) + applied,
            hu_to_density_model=parent.hu_to_density_model,
        )
        # the arrays here are (z, y, x), as SimpleITK reads them; the store takes (x, y, z)
        self.store.save(geometry_id=geometry_id, cache_key=cache_key, density=density.transpose(2, 1, 0), masks=masks.transpose(2, 1, 0),
                        ct=ct.transpose(2, 1, 0) if ct is not None else None, result=result)
        logger.info("Derived geometry %s from %s: %d operation(s), structures %s", geometry_id, parent.geometry_id,
                    len(applied), sorted(index))
        return result


__all__ = ["DeriveError", "GeometryDeriver", "derive_cache_key"]
