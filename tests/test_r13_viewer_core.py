"""Roadmap R13.2b: the viewer's RT Dose core (viewer/rt-dose-core, JavaScript) against radiarch's own objects.

This test writes fixtures, then runs the core's Node tests on them:
- the dose, structure set and DVHs of a radiarch export;
- synthetic RT Doses with rotated orientations, absolute and uneven frame offsets, 16- and 32-bit pixels.

The fixtures are naturalized datasets, keyword to value as dcmjs gives them in OHIF, with pixel data beside them.
Expected values are computed here independently:
- the stored doses;
- the voxel indices of patient points;
- trilinear interpolation onto image grids;
- the DVH curves.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue
from pydicom.valuerep import DSfloat, IS

from test_r6_rt_export_service import env  # noqa: F401
from test_r13_viewer import _export

CORE = Path(__file__).resolve().parent.parent / "viewer" / "rt-dose-core"
NODE = shutil.which("node")


# --- naturalized datasets ---------------------------------------------------------------------------------------

def _value(v):
    if isinstance(v, (DSfloat, float)):
        return float(v)
    if isinstance(v, (IS, int)):
        return int(v)
    if isinstance(v, MultiValue):
        return [_value(x) for x in v]
    return str(v)


def naturalize(ds: Dataset, out: Path, prefix: str) -> dict:
    d = {}
    for elem in ds:
        if not elem.keyword:
            continue
        if elem.keyword == "PixelData":
            name = f"{prefix}.pixels.bin"
            (out / name).write_bytes(bytes(elem.value))
            d["PixelData"] = {"$file": name}
        elif elem.VR == "SQ":
            d[elem.keyword] = [naturalize(item, out, f"{prefix}.{elem.keyword}{i}") for i, item in enumerate(elem.value)]
        elif isinstance(elem.value, (bytes, bytearray)):
            continue
        elif elem.value is not None and elem.value != "":
            d[elem.keyword] = _value(elem.value)
    return d


def _write(out: Path, name: str, ds: Dataset) -> str:
    (out / f"{name}.json").write_text(json.dumps(naturalize(ds, out, name)))
    return f"{name}.json"


# --- geometry, independently of the core --------------------------------------------------------------------------

def _geometry(ds: Dataset):
    iop = np.array(ds.ImageOrientationPatient, dtype=float)
    r, c = iop[:3], iop[3:]
    n = np.cross(r, c)
    ipp = np.array(ds.ImagePositionPatient, dtype=float)
    row_sp, col_sp = (float(v) for v in ds.PixelSpacing)
    off = np.array(ds.GridFrameOffsetVector, dtype=float)
    if abs(off[0]) > 1e-6:
        off = off - ipp @ n
    return ipp, r, c, n, col_sp, row_sp, off


def _stored_dose(ds: Dataset) -> np.ndarray:
    return (ds.pixel_array.astype(np.float64) * float(ds.DoseGridScaling)).reshape(int(ds.NumberOfFrames), ds.Rows, ds.Columns)


def _to_index(ds: Dataset, pts: np.ndarray):
    """Fractional (i, j, k) of patient points (N, 3); inside: within the grid's voxel centres."""
    ipp, r, c, n, col_sp, row_sp, off = _geometry(ds)
    d = pts - ipp
    i, j, w = d @ r / col_sp, d @ c / row_sp, d @ n
    k = np.interp(w, off, np.arange(off.size))
    tol = 1e-6
    inside = (i >= -tol) & (i <= ds.Columns - 1 + tol) & (j >= -tol) & (j <= ds.Rows - 1 + tol) & (w >= off[0] - tol) & (w <= off[-1] + tol)
    return np.clip(i, 0, ds.Columns - 1), np.clip(j, 0, ds.Rows - 1), k, inside


def _trilinear(vol: np.ndarray, i, j, k):
    from scipy.ndimage import map_coordinates
    return map_coordinates(vol, np.vstack([k, j, i]), order=1, mode="nearest")


def _target_points(target: dict) -> np.ndarray:
    nx, ny, nz = target["dimensions"]
    sx, sy, sz = target["spacing"]
    d = np.array(target["direction"], dtype=float).reshape(3, 3)
    z, y, x = np.meshgrid(np.arange(nz), np.arange(ny), np.arange(nx), indexing="ij")
    return (np.array(target["origin"]) + x.reshape(-1, 1) * sx * d[0] + y.reshape(-1, 1) * sy * d[1] + z.reshape(-1, 1) * sz * d[2])


def _rot_z(deg: float) -> list:
    a = math.radians(deg)
    return [math.cos(a), math.sin(a), 0.0, -math.sin(a), math.cos(a), 0.0, 0.0, 0.0, 1.0]


# --- synthetic RT Doses -------------------------------------------------------------------------------------------

def _synthetic(name: str, *, iop, ipp, spacing_rc, rel_offsets, shape_yx, bits, signed, absolute) -> Dataset:
    ds = Dataset()
    ds.Modality, ds.SOPClassUID = "RTDOSE", "1.2.840.10008.5.1.4.1.1.481.2"
    ds.ImageOrientationPatient, ds.ImagePositionPatient = list(iop), list(ipp)
    ds.PixelSpacing = list(spacing_rc)
    ds.Rows, ds.Columns, ds.NumberOfFrames = shape_yx[0], shape_yx[1], len(rel_offsets)
    n = np.cross(np.array(iop[:3]), np.array(iop[3:]))
    ds.GridFrameOffsetVector = [float(o + (np.dot(ipp, n) if absolute else 0.0)) for o in rel_offsets]
    ds.BitsAllocated = ds.BitsStored = bits
    ds.HighBit, ds.PixelRepresentation, ds.SamplesPerPixel = bits - 1, 1 if signed else 0, 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.DoseUnits, ds.DoseType, ds.DoseSummationType = "GY", "PHYSICAL", "PLAN"
    ds.DoseGridScaling = 1e-3
    # a dose linear in patient coordinates, so trilinear interpolation reproduces it up to the stored resolution
    ipp_a, r, c = np.array(ipp, float), np.array(iop[:3], float), np.array(iop[3:], float)
    k, j, i = np.meshgrid(np.array(rel_offsets, float), np.arange(shape_yx[0]), np.arange(shape_yx[1]), indexing="ij")
    p = ipp_a + i[..., None] * spacing_rc[1] * r + j[..., None] * spacing_rc[0] * c + k[..., None] * n
    gy = 20.0 + 0.05 * p[..., 0] - 0.03 * p[..., 1] + 0.04 * p[..., 2]
    stored = np.rint(gy / 1e-3)
    dtype = {(16, False): "<u2", (16, True): "<i2", (32, False): "<u4", (32, True): "<i4"}[(bits, signed)]
    ds.PixelData = stored.astype(dtype).tobytes()
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    return ds


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_viewer_core_reads_radiarch_doses(env, tmp_path):
    out = tmp_path / "fixtures"
    out.mkdir()
    svc, res = _export()
    rd = pydicom.dcmread(svc.file_path(res.export_id, "RD.dcm"))
    rs = pydicom.dcmread(svc.file_path(res.export_id, "RS.dcm"))

    doses = {
        "radiarch": rd,
        "oblique-absolute-uneven-16bit": _synthetic("oblique", iop=_rot_z(30.0)[:6], ipp=[-40.0, -25.0, -12.0], spacing_rc=(2.5, 3.0),
                                                   rel_offsets=[0.0, 2.0, 4.0, 7.0, 10.0, 15.0], shape_yx=(18, 21), bits=16, signed=False,
                                                   absolute=True),
        "prone-32bit-signed": _synthetic("prone", iop=[-1.0, 0.0, 0.0, 0.0, -1.0, 0.0], ipp=[30.0, 20.0, -10.0], spacing_rc=(2.0, 2.0),
                                         rel_offsets=[0.0, 3.0, 6.0, 9.0], shape_yx=(16, 16), bits=32, signed=True, absolute=False),
    }
    index = {"doses": [], "resamples": [], "dvhs": []}
    for name, ds in doses.items():
        rtdose = _write(out, f"rd-{name}", ds)
        vol = _stored_dose(ds)
        (out / f"rd-{name}.values.bin").write_bytes(vol.astype("<f4").tobytes())
        ipp, r, c, n, col_sp, row_sp, off = _geometry(ds)
        probes = []
        for (i, j, k) in [(0, 0, 0), (ds.Columns - 1, ds.Rows - 1, len(off) - 1), (ds.Columns // 2, 1, len(off) // 2)]:
            probes.append({"world": list(ipp + i * col_sp * r + j * row_sp * c + off[k] * n), "index": [i, j, k]})
        probes.append({"world": list(ipp - 50.0 * r), "index": None})
        probes.append({"world": list(ipp + (off[-1] + 5.0) * n), "index": None})
        index["doses"].append({"name": name, "rtdose": rtdose, "values": f"rd-{name}.values.bin", "max_gy": float(vol.max()),
                               "shape_xyz": [ds.Columns, ds.Rows, int(ds.NumberOfFrames)], "frame_offsets": [float(o) for o in off],
                               "uniform_frames": bool(np.allclose(np.diff(off), np.diff(off)[0], atol=1e-3)) if off.size > 1 else True,
                               "probes": probes})

        # onto image grids: an axial grid of other spacings and a grid rotated about z, each partly outside the dose
        centre = ipp + (ds.Columns - 1) / 2 * col_sp * r + (ds.Rows - 1) / 2 * row_sp * c + off[off.size // 2] * n
        for tname, direction, spacing in [("axial", [1, 0, 0, 0, 1, 0, 0, 0, 1], [3.3, 3.7, 4.1]), ("rotated", _rot_z(-15.0), [2.9, 3.1, 2.3])]:
            dims = [24, 22, 9]
            d = np.array(direction, dtype=float).reshape(3, 3)
            origin = centre - (dims[0] / 2) * spacing[0] * d[0] - (dims[1] / 2) * spacing[1] * d[1] - (dims[2] / 2) * spacing[2] * d[2]
            target = {"dimensions": dims, "spacing": spacing, "origin": [float(v) for v in origin], "direction": [float(v) for v in direction]}
            i, j, k, inside = _to_index(ds, _target_points(target))
            expected = np.where(inside, _trilinear(vol, i, j, k), 0.0).astype("<f4")
            assert 0 < inside.sum() < inside.size            # partly outside, so both branches are exercised
            fname = f"rs-{name}-{tname}.bin"
            (out / fname).write_bytes(expected.tobytes())
            index["resamples"].append({"name": f"{name} onto {tname}", "rtdose": rtdose, "target": target, "expected": fname,
                                       "tolerance_gy": float(vol.max()) * 2e-6 + 1e-6, "min_nonzero": int((expected > 0).sum())})

    # the DVHs of radiarch's dose, named by its structure set
    names = {int(x.ROINumber): str(x.ROIName) for x in rs.StructureSetROISequence}
    colors = {int(x.ReferencedROINumber): [int(v) for v in x.ROIDisplayColor] for x in rs.ROIContourSequence}
    expected = []
    for item in rd.DVHSequence:
        number = int(item.DVHReferencedROISequence[0].ReferencedROINumber)
        data = np.array(item.DVHData, dtype=float).reshape(-1, 2)
        expected.append({"roi_number": number, "name": names[number], "color": colors[number],
                         "dose_gy": list(np.concatenate([[0.0], np.cumsum(data[:-1, 0])])), "volume": list(data[:, 1]),
                         "max_gy": float(item.DVHMaximumDose), "mean_gy": float(item.DVHMeanDose)})
    index["dvhs"].append({"rtdose": "rd-radiarch.json", "rtstruct": _write(out, "rs-radiarch", rs), "expected": expected})
    (out / "index.json").write_text(json.dumps(index))

    proc = subprocess.run([NODE, "--test", "--test-reporter=tap", str(CORE / "test" / "core.test.js")], cwd=CORE, capture_output=True, text=True, timeout=300,
                          env={**os.environ, "RT_DOSE_FIXTURES": str(out)})
    report = proc.stdout + proc.stderr
    assert proc.returncode == 0, report
    assert "# skipped 0" in report and "# fail 0" in report, report
