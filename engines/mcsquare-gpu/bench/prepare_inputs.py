"""Write MCsquare inputs with radiarch's driver: A) single spots in water, B) a heterogeneous phantom with a field.
Nuclear interactions off, full dose (MHD), for the GPU prototype's comparison with the CPU engine."""
import sys
from pathlib import Path
import numpy as np
from radiarch.models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot
from radiarch.services.dose_engines import mcsquare_driver as D

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
drv = D.MCsquareDriver(n_threads=48, seed=0)
over = {"Simulate_Nuclear_Interactions": False, "Dose_MHD_Output": True, "Dose_Sparse_Output": False,
        "Beamlet_Mode": False, "Compute_stat_uncertainty": False}

def plan(layers, gantry=0.0):
    return ProtonPlan(beams=[ProtonBeam(isocenter_mm=(0.0, 0.0, 0.0), gantry_deg=gantry,
                                        layers=[ProtonLayer(energy_mev=e, spots=[ProtonSpot(x_mm=x, y_mm=y, mu=1.0) for x, y in pts])
                                                for e, pts in layers])])

# A: water box 10 x 30 x 10 cm (beam along +y in radiarch's frame), 2 mm voxels; one spot per energy
hu = np.zeros((50, 150, 50), dtype=np.float32)
for e in (100.0, 150.0, 200.0):
    w = out / f"water{int(e)}"
    drv.prepare(w, hu, (2.0, 2.0, 2.0), (-49.0, 1.0, -49.0), plan([(e, [(0.0, 0.0)])]), nb_primaries=1e6,
                calibration=D.CalibrationTables.water(), config_overrides=over)

# B: 20 x 25 x 20 cm, 2 mm: soft tissue (40 HU) with a bone slab (700 HU) and a lung slab (-750 HU) across the field
hu = np.full((100, 125, 100), 40.0, dtype=np.float32)
hu[:, 20:30, :50] = 700.0            # bone over half the field, 4-6 cm deep
hu[:, 45:70, 50:] = -750.0           # lung behind the other half
grid = [(x, y) for x in np.arange(-30.0, 30.1, 5.0) for y in np.arange(-30.0, 30.1, 5.0)]
layers = [(e, grid) for e in (110.0, 120.0, 130.0, 140.0, 150.0)]
w = out / "hetero"
drv.prepare(w, hu, (2.0, 2.0, 2.0), (-99.0, 1.0, -99.0), plan(layers), nb_primaries=1e7, config_overrides=over)
for d in sorted(out.iterdir()):
    print(d.name, sum(1 for _ in d.rglob("*")), "files")

# C) the same phantom and field in beamlet mode (radiarch's influence-matrix settings, nuclear interactions on)
hu = np.full((100, 125, 100), 40.0, dtype=np.float32)
hu[:, 20:30, :50] = 700.0
hu[:, 45:70, 50:] = -750.0
w = out / "hetero_dij"
drv.prepare(w, hu, (2.0, 2.0, 2.0), (-99.0, 1.0, -99.0), plan(layers), nb_primaries=1e4, beamlets=True)
print("hetero_dij written")
