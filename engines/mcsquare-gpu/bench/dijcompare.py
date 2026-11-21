"""dijcompare.py REF OTHER [NOISE]: influence matrices from two MCsquare beamlet runs (read with radiarch's own
reader), optionally a noise baseline (another seed of REF's engine)."""
import sys
from pathlib import Path
import numpy as np
from radiarch.services.dose_engines.mcsquare_driver import read_sparse_beamlets

def load(d):
    m, meta = read_sparse_beamlets(Path(d) / "Outputs" / "Sparse_Dose.txt")
    return m.tocsc().astype(np.float64), meta

ref, meta = load(sys.argv[1])
oth, _ = load(sys.argv[2])
others = [("other", oth)]
if len(sys.argv) > 3:
    others.append(("noise", load(sys.argv[3])[0]))
print(f"shape {ref.shape}, spots {meta.get('NbrSpots', '?')}; nnz ref {ref.nnz}, " + ", ".join(f"{n} {m.nnz}" for n, m in others))
cs = np.asarray(ref.sum(axis=0)).ravel()
tot = np.asarray(ref.sum(axis=1)).ravel()
hi = tot > 0.1 * tot.max()
for name, m in others:
    c = np.asarray(m.sum(axis=0)).ravel()
    r = (c - cs) / cs
    t = np.asarray(m.sum(axis=1)).ravel()
    d = (t - tot) / tot.max()
    print(f"{name} - ref: spot integrals: mean {r.mean()*100:+.3f} %, sd {r.std()*100:.3f} %, max |.| {np.abs(r).max()*100:.2f} %;"
          f" summed dose (all spots, 1 each): rms {np.sqrt((d[hi]**2).mean())*100:.3f} %, mean {d[hi].mean()*100:+.4f} % of max"
          f" over {hi.sum()} voxels")
