"""compare.py REF OTHER [NOISE]: dose comparison of two MCsquare Dose.mhd (CT frame), optionally a noise baseline
(another seed of REF's engine). Prints integral, peak position, R80, distal fall-off, lateral sigma and the voxel
differences above 10 % of the maximum."""
import sys
from pathlib import Path
import numpy as np

def read(d):
    h = dict(l.split(" = ", 1) for l in (Path(d) / "Outputs" / "Dose.mhd").read_text().splitlines() if " = " in l)
    dims = [int(v) for v in h["DimSize"].split()]
    sp = [float(v) for v in h["ElementSpacing"].split()]
    a = np.fromfile(Path(d) / "Outputs" / h["ElementDataFile"], dtype=np.float32).reshape(dims[::-1])  # (z, y, x)
    return a.astype(np.float64), sp

def metrics(a, sp):
    idd = a.sum(axis=(0, 2))                   # along y (beam direction in these phantoms)
    k = int(np.argmax(idd)); pk = idd[k]
    tail = np.where(idd[k:] <= 0.8 * pk)[0]; j = k + int(tail[0]) if len(tail) else len(idd) - 1
    r80 = np.interp(0.8 * pk, [idd[j], idd[j - 1]], [j, j - 1]) * sp[1]
    t2 = np.where(idd[k:] <= 0.2 * pk)[0]; j2 = k + int(t2[0]) if len(t2) else len(idd) - 1
    r20 = np.interp(0.2 * pk, [idd[j2], idd[j2 - 1]], [j2, j2 - 1]) * sp[1]
    mid = a[:, max(k // 2, 1), :]
    px = mid.sum(axis=0); xs = np.arange(len(px)) * sp[0]
    sig = np.sqrt(np.sum(px * (xs - np.sum(px * xs) / px.sum()) ** 2) / px.sum()) if px.sum() > 0 else 0
    return dict(total=a.sum(), peak_depth=k * sp[1], peak_to_entrance=pk / max(idd[1], 1e-30), R80=r80, falloff=r20 - r80,
                sigma_mid=sig, dmax=a.max())

ref, sp = read(sys.argv[1]); oth, _ = read(sys.argv[2])
rows = [("ref", metrics(ref, sp)), ("other", metrics(oth, sp))]
if len(sys.argv) > 3:
    noi, _ = read(sys.argv[3]); rows.append(("noise", metrics(noi, sp)))
keys = list(rows[0][1])
print(f"{'':6}" + "".join(f"{k:>16}" for k in keys))
for name, m in rows:
    print(f"{name:6}" + "".join(f"{m[k]:16.5g}" for k in keys))
hi = ref > 0.1 * ref.max()
def diff(o):
    d = (o - ref) / ref.max()
    return f"max |d| {np.abs(d[hi]).max()*100:.2f} %, mean d {d[hi].mean()*100:+.3f} %, rms {np.sqrt((d[hi]**2).mean())*100:.2f} % of Dmax over {hi.sum()} voxels"
print("other - ref:", diff(oth))
if len(sys.argv) > 3:
    print("noise - ref:", diff(noi))
