"""Halo metrics for the MCsquare runs (RUNS/<case>-<tag>/Outputs/Dose.mhd) and the Geant4 runs (G4/<E>-<phys>/halo*edep*.mhd)."""
import sys, glob, re
from pathlib import Path
import numpy as np
import itk

def metrics(dose_xd):                      # dose_xd: (x lateral 81, depth), summed over the other lateral axis, 1 mm
    x = (np.arange(dose_xd.shape[0]) - 40) * 1.0
    y = 0.5 + np.arange(dose_xd.shape[1])
    idd = dose_xd.sum(axis=0); k = int(np.argmax(idd))
    beyond = np.where(idd[k:] <= 0.8 * idd[k])[0]; j = k + beyond[0]
    r80 = float(np.interp(0.8 * idd[k], [idd[j], idd[j - 1]], [y[j], y[j - 1]]))
    pe = float(idd[k] / idd[5])
    out = {"R80": r80, "peak/entrance": pe}
    for frac in (0.5, 0.8):
        prof = np.clip(dose_xd[:, int(np.argmin(np.abs(y - frac * r80)))], 0, None)
        m = (prof * x).sum() / prof.sum()
        out[f"rms sigma @{frac}R80"] = float(np.sqrt((prof * (x - m) ** 2).sum() / prof.sum()))
        out[f"halo >10mm @{frac}R80 %"] = float(100 * prof[np.abs(x) > 10].sum() / prof.sum())
    return out

rows = {}
for f in sorted(glob.glob(f"{sys.argv[1]}/*/Outputs/Dose.mhd")):
    tag = Path(f).parts[-3]
    a = itk.array_from_image(itk.imread(f))             # MCsquare's frame as (z, y, x); y = depth, reversed
    rows[tag] = metrics(a.sum(axis=0)[::-1, :].T)        # (x, depth from the surface)
for f in sorted(glob.glob(f"{sys.argv[2]}/*/halo*edep*.mhd")):
    tag = "g4-" + Path(f).parts[-2]
    a = itk.array_from_image(itk.imread(f))             # (z depth, y 1, x 81), z ascending = deeper first
    rows[tag] = metrics(a[::-1, 0, :].T)
keys = list(next(iter(rows.values())).keys())
print(f"{'run':26}" + "".join(f"{k:>22}" for k in keys))
for t, r in rows.items():
    print(f"{t:26}" + "".join(f"{r[k]:22.4f}" for k in keys))
