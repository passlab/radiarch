"""Halo study inputs: the proton_bragg_peak phantom (water, +-40 mm, 350 mm deep, 1 mm) and an idealised beam
(one Gaussian, sigma 3 mm, divergence 0.1 mrad - zero makes the sampling degenerate -, no energy spread) at 200 and 225 MeV, nuclear interactions on and off."""
import sys
from pathlib import Path
import numpy as np
from radiarch.models.proton_plan import ProtonBeam, ProtonLayer, ProtonPlan, ProtonSpot
from radiarch.services.dose_engines import mcsquare_driver as D
from radiarch.validation import phantoms as ph

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
drv = D.MCsquareDriver(n_threads=48, seed=0)
phantom = ph.water_box(40.0, 350.0, 1.0)
hu = np.zeros(phantom.shape, dtype=np.float32)
for e in (200.0, 225.0):
    plan = ProtonPlan(beams=[ProtonBeam(isocenter_mm=(0.0, 0.0, 0.0), gantry_deg=0.0,
                                        layers=[ProtonLayer(energy_mev=e, spots=[ProtonSpot(x_mm=0.0, y_mm=0.0, mu=1.0)])])])
    for nuc in (True, False):
        w = out / f"w{int(e)}{'n' if nuc else 'e'}"
        drv.prepare(w, hu, phantom.spacing_mm, phantom.origin_mm, plan, nb_primaries=1e7, calibration=D.CalibrationTables.water(),
                    config_overrides={"Simulate_Nuclear_Interactions": nuc, "Compute_stat_uncertainty": False})
        lines = (w / "bdl.txt").read_text().splitlines()
        for i, l in enumerate(lines):
            c = l.split()
            if len(c) >= 18 and c[0].replace(".", "").isdigit():
                # NominalEnergy MeanEnergy EnergySpread ProtonsMU Weight1 SpotSize1x Divergence1x Correlation1x
                # SpotSize1y Divergence1y Correlation1y Weight2 SpotSize2x Divergence2x Correlation2x SpotSize2y ...
                c[2] = "0.0"; c[4] = "1.0"; c[5] = "3.0"; c[6] = "0.0001"; c[7] = "0.001"; c[8] = "3.0"; c[9] = "0.0001"; c[10] = "0.001"
                c[11] = "0.0"
                lines[i] = " \t ".join(c)
        (w / "bdl.txt").write_text("\n".join(lines) + "\n")
        print(w.name, "mean energy", [l.split()[1] for l in lines if l.split()[:1] == [f"{e:.3f}"]])
