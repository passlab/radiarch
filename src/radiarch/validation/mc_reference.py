"""Monte Carlo photon references with OpenGATE (roadmap R7).

A standalone script: it imports no radiarch code because it runs in its own
Python 3.12 environment (OpenGATE 10 does not build on 3.14)::

    uv run --no-project --python 3.12 --with opengate==10.1.1 --with itk \\
        python -m radiarch.validation.mc_reference --case water_10x10 --primaries 2e7 --out validation/references/mc

Each case is one of the harness phantoms (``validation/phantoms.py``: a
30 cm water box at SSD 100 cm; the lung and bone slabs; the thorax-like
body) irradiated by a 6 MV beam and scored on the harness grid. The beam is
what the CCC engine assumes: a point source of the Mohan 6 MV spectrum
(EGSnrc distribution, ``references/spectra/mohan6.spectrum``) with a flat
angular fluence over the field, collimated by the Elekta Versa HD jaws and
Agility MLC of ``opengate.contrib.linacs.elektaversa`` — no flattening
filter, no head scatter, no contamination electrons — so the comparison
tests phantom transport, not the linac. ``--source versa`` instead runs the
full Versa head from its electron source (hours; for the record, not the
nightly). Slab materials are water at the slab density, as the engine sees
them.

The output is one ``.npz`` per case in radiarch's grid convention: dose per
primary as a ``(z, y, x)`` float32 array with the beam along ``+y`` and the
surface at ``y = 0``, the relative statistical uncertainty, spacing, origin,
and the provenance (primaries, seed, OpenGATE version, elapsed time) in a
JSON sidecar. ``validation/run.py`` reads them in the ``photon_vs_mc`` case.

``--primaries`` is the total: OpenGATE 10 runs a source's ``n`` on every
thread, so each thread runs its share (:func:`per_thread`), and the dose is per
simulated primary as the statistics actor counts them. The R7 and R8
references were made before this and ran 18 times the primaries they state.

One process stops gaining speed beyond about a dozen threads (on a 48-core
server, 81 000 primaries per second on 4 threads, 149 000 on 12, 132 000 on
80), so a long reference runs as several processes with different seeds and
``--merge`` joins them.

The leaf model's check (R4, ``docs/reports/mlc-leaf-model.md``) adds 1 x 1 and
2 x 2 cm open fields, scored at 1.25 mm over the central 100 mm, and four fields
set leaf by leaf (``MLC_BANDS``): open, every pair closed, a 10 mm gap on every
pair, and an irregular field. The Versa HD has no X jaws, so two tungsten blocks
stand in for them; the provenance gives each leaf pair's row at isocenter, from
which the harness plans the same field.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SPECTRUM = HERE / "references" / "spectra" / "mohan6.spectrum"

PHANTOM_MM = 300.0           # cube side; the harness water box is ±150 mm wide and 300 mm deep
SAD_MM = 1000.0
CUT_MM = 0.1            # production cut in the phantom
MAX_STEP_MM = 0.5       # electron and positron step limit in the phantom (step convergence, R7)

# (depth_from_mm, depth_to_mm, density_g_cm3): water elsewhere
SLABS = {
    "water_10x10": [],
    "water_4x4": [],
    "water_20x20": [],
    "lung_slab": [(30.0, 110.0, 0.26)],
    "lung_slab_2x2": [(30.0, 110.0, 0.26)],      # a narrow field in lung: lateral electronic disequilibrium (R8)
    "bone_slab": [(30.0, 60.0, 1.85)],
}
FIELDS = {"water_10x10": 100.0, "water_4x4": 40.0, "water_20x20": 200.0, "lung_slab": 100.0, "lung_slab_2x2": 20.0, "bone_slab": 100.0}

# Small fields and fields shaped leaf by leaf, for the pencil beam's leaf model (docs/reports/mlc-leaf-model.md).
# The small fields are open fields like the others; they are scored over the central 100 mm only, at 1.25 mm.
SLABS.update(water_2x2=[], water_1x1=[])
FIELDS.update(water_2x2=20.0, water_1x1=10.0)
# The MLC fields: Y jaws at +-50 mm, and two tungsten blocks standing in for X jaws at +-100 mm (the Versa HD has
# none). Each band (y0, y1, x_left, x_right), at isocenter, opens the leaf pairs whose centre lies in [y0, y1) to the
# nominal tips x_left, x_right; a band with x_left == x_right closes its pairs there, the leaves touching. Pairs in no
# band close on the axis, as the Versa model leaves them. Nominal tips are the Versa's: its leaf calibration ("from
# thales") puts the 50 % edge of a rounded leaf end on them, as an Elekta planning system states leaf positions.
MLC_JAW_Y_MM = 50.0
MLC_BLOCK_X_MM = 100.0
MLC_BANDS = {
    "mlc_open": [(-50.0, 50.0, -110.0, 110.0)],          # the leaves behind the blocks: a 20 x 10 cm open field
    "mlc_closed": [],                                    # every pair closed on the axis: transmission and the tips' leak
    "mlc_gap10": [(-50.0, 50.0, -5.0, 5.0)],             # a 10 mm gap on every pair: the effective leaf gap
    "mlc_shape": [(-50.0, -30.0, -40.0, 40.0),           # an irregular field for the check; adjacent openings overlap,
                  (-30.0, -20.0, 20.0, 20.0),            # since the model's opposite banks overlap when they interdigitate.
                  (-20.0, -10.0, 15.0, 25.0),            # Closed off the axis at 20 mm, a 10 mm gap at 20 mm,
                  (-10.0, 5.0, -30.0, 22.0),
                  (5.0, 15.0, -32.5, -27.5),             # a 5 mm gap at -30 mm
                  (15.0, 30.0, -60.0, -10.0),
                  (30.0, 50.0, -20.0, 60.0)],
}
for _c in MLC_BANDS:
    SLABS[_c] = []
LATERAL_MM = {"water_2x2": 100.0, "water_1x1": 100.0, **{c: 240.0 for c in MLC_BANDS}}   # scored width; default the phantom's
X_BLOCK_FROM_MM, X_BLOCK_TO_MM = 180.0, 280.0     # the blocks' extent along the beam, from the source (between the target and the MLC)


def read_egsnrc_spectrum(path: Path):
    """EGSnrc spectrum file: title; ``nbins, e_low, mode``; then ``e_upper, value`` per bin.
    Mode 1 values are per MeV, mode 0 per bin. Returns ``(bin_edges_mev, weights_per_bin)``."""
    lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    nbins, e_low, mode = [float(v) for v in lines[1].split(",")[:3]]
    edges = [e_low]
    weights = []
    for l in lines[2:2 + int(nbins)]:
        e_up, val = [float(v) for v in l.split(",")[:2]]
        width = e_up - edges[-1]
        weights.append(val * width if int(mode) == 1 else val)
        edges.append(e_up)
    w = np.asarray(weights, dtype=float)
    return np.asarray(edges, dtype=float), (w / w.sum()).tolist()


def build(case: str, primaries: int, threads: int, spacing_mm: float, seed: int, source: str, out_dir: Path, visu: bool = False):
    import opengate as gate
    import opengate.contrib.linacs.elektaversa as versa

    mm, m, MeV, deg = gate.g4_units.mm, gate.g4_units.m, gate.g4_units.MeV, gate.g4_units.deg
    gcm3 = gate.g4_units.g_cm3
    field_mm = FIELDS.get(case, 2.0 * MLC_BLOCK_X_MM)

    sim = gate.Simulation()
    sim.g4_verbose = False
    sim.visu = visu
    sim.number_of_threads = int(threads)
    sim.random_seed = int(seed)
    sim.output_dir = str(out_dir)
    sim.progress_bar = False
    sim.check_volumes_overlap = False

    world = sim.world
    world.size = [2 * m, 2 * m, 2.6 * m]
    world.material = "G4_AIR"

    # materials: water at the slab densities
    db = sim.volume_manager.material_database
    for _, _, rho in SLABS[case]:
        if _slab_material(rho) != "G4_WATER":
            db.add_material_weights(_slab_material(rho), ["H", "O"], [0.111894, 0.888106], float(rho) * gcm3)

    # phantom: sibling boxes stacked along the beam (water, slab, water), each scored by its own dose actor;
    # the upper face at the isocenter plane (SSD = SAD), beam along -z. Not nested volumes and not a voxelised
    # image: R7 found that OpenGATE 10's dose actor reads 3.5-4.5 % low upstream (and shows a spike at the
    # boundary) when the scored volume holds a daughter or voxels, even of water, whatever the physics list.
    layers = phantom_layers(case)
    phantoms = []
    for i, (d0, d1, material) in enumerate(layers):
        box = sim.add_volume("Box", f"layer{i}")
        box.size = [PHANTOM_MM * mm, PHANTOM_MM * mm, (d1 - d0) * mm]
        box.material = material
        box.translation = [0, 0, -(d0 + d1) / 2.0 * mm]
        phantoms.append(box)
    # collimation: Versa HD jaws and Agility MLC in an empty head, field at isocenter
    versa.add_linac_materials(sim)
    linac = versa.add_empty_linac_box(sim, "linac_box", SAD_MM * mm)
    linac.material = "G4_Galactic"
    jaws = versa.add_jaws(sim, linac.name, linac.name)
    mlc = versa.add_mlc(sim, linac.name, linac.name)
    mlc_note = None
    if case in MLC_BANDS:
        mlc_note = set_mlc_field(sim, versa, linac, mlc, jaws, MLC_BANDS[case], mm)
        # the source cone covers the rectangle the jaws and blocks leave open, as the open fields' cones cover theirs
        theta_max = float(np.degrees(np.arctan(np.hypot(MLC_BLOCK_X_MM, MLC_JAW_Y_MM) / SAD_MM))) + 0.5
    else:
        versa.set_rectangular_field(mlc, jaws, field_mm * mm, field_mm * mm, SAD_MM * mm)
        theta_max = float(np.degrees(np.arctan(0.75 * field_mm / SAD_MM))) + 0.5
    sim.volume_manager.get_volume("linac_box_mlc").material = "G4_Galactic"

    if source == "spectrum":
        edges, weights = read_egsnrc_spectrum(SPECTRUM)
        src = sim.add_source("GenericSource", "photons")
        src.particle = "gamma"
        src.attached_to = linac.name
        z_linac = linac.size[2]
        src.position.type = "point"
        src.position.translation = [0, 0, z_linac / 2 - 5.6 * mm]          # the target position of the Versa model
        src.direction.type = "iso"
        src.direction.theta = [0, theta_max * deg]
        src.direction.phi = [0, 360 * deg]
        src.energy.type = "spectrum_histogram"
        src.energy.spectrum_energy_bin_edges = [float(e) * MeV for e in edges]
        src.energy.spectrum_weights = [float(w) for w in weights]
        src.n = per_thread(primaries, threads)
        spectrum_note = f"Mohan 6 MV (EGSnrc {SPECTRUM.name}), point source, flat fluence within {theta_max:.2f} deg"
    elif source == "versa":
        # the full head from its electron source, as in opengate's test019: slow, for the record
        full = versa.add_linac(sim, "versa", SAD_MM * mm)
        src = versa.add_electron_source(sim, full.name, 6.49 * MeV, 1 * mm, 0.5 * mm)
        versa.enable_brem_splitting(sim, full.name, splitting_factor=10)
        src.n = per_thread(primaries, threads)
        spectrum_note = "Elekta Versa HD head model from a 6.49 MeV electron source (opengate.contrib.linacs.elektaversa)"
    else:
        raise SystemExit(f"unknown source {source}")

    # Step convergence (R7): without a step limit the dose depends on the production cut (0.5 vs 1 mm moved the
    # upstream dose 4.6 %) and on any geometric boundary in the beam (-4.5 % upstream, a spike past it); with
    # electron and positron steps limited to 0.5 mm and a 0.1 mm cut, a single box and a split box agree within
    # 0.5 %. These are the reference settings.
    pm = sim.physics_manager
    pm.physics_list_name = "G4EmStandardPhysics_option3"
    pm.set_production_cut("world", "all", 1 * mm)
    pm.user_limits_particles = ["e-", "e+"]
    for box in phantoms:
        pm.set_production_cut(box.name, "all", CUT_MM * mm)
        pm.set_max_step_size(box.name, MAX_STEP_MM * mm)

    n = int(round(LATERAL_MM.get(case, PHANTOM_MM) / spacing_mm))     # the image is centred on the box
    dose = []
    for i, ((d0, d1, _), box) in enumerate(zip(layers, phantoms)):
        actor = sim.add_actor("DoseActor", f"dose{i}")
        actor.attached_to = box.name
        actor.size = [n, n, int(round((d1 - d0) / spacing_mm))]
        actor.spacing = [spacing_mm * mm] * 3
        actor.output_filename = f"{case}_layer{i}.mhd"
        actor.dose.active = True
        actor.dose_uncertainty.active = True
        actor.edep.active = False
        dose.append(actor)
    stats = sim.add_actor("SimulationStatisticsActor", "stats")
    stats.track_types_flag = True
    prov = dict(case=case, field_mm=field_mm, construction="stacked sibling boxes, one dose actor each", primaries=int(primaries), threads=int(threads), seed=int(seed),
                spacing_mm=float(spacing_mm), source=source, spectrum=spectrum_note, slabs=SLABS[case],
                physics=f"G4EmStandardPhysics_option3; cuts 1 mm world, {CUT_MM:g} mm phantom; e-/e+ max step {MAX_STEP_MM:g} mm in the phantom",
                collimation="Elekta Versa HD jaws + Agility MLC (opengate.contrib.linacs.elektaversa), rectangular field at isocenter")
    if mlc_note is not None:
        prov.update(collimation="Elekta Versa HD jaws + Agility MLC (opengate.contrib.linacs.elektaversa), leaf by leaf; tungsten blocks for X jaws",
                    mlc=mlc_note)
    return sim, dose, stats, prov


def per_thread(primaries: float, threads: int) -> int:
    """The source's ``n`` for a total of ``primaries``: OpenGATE 10 runs ``n`` on every thread. The references made
    before 2026-11-06 (R7, R8) passed the total as ``n`` with 18 threads, so they ran 18 times the primaries their
    provenance states and their dose is per primary per thread; ``cases_r7._mc_reference`` scales them."""
    return max(1, int(np.ceil(float(primaries) / max(1, int(threads)))))


def mlc_leaf_positions(centres_mm, bands, f, c: float, jaw_y_mm: float = MLC_JAW_Y_MM):
    """Each leaf's offset from closed and each pair's row at isocenter, for the leaf pairs centred at ``centres_mm``
    (isocenter, ascending). Returns ``(left, right, rows)``: the left and right leaves' offsets at the MLC (mm, in the
    order of ``centres_mm``) and, for the pairs the jaws leave open, ``[y_min, y_max, x_left, x_right]`` with the nominal
    tips at isocenter.

    A tip at nominal x sits where the Versa's own rectangular fields put it: a right leaf at ``c (x - f(x))`` and a left
    leaf at ``c (x + f(-x))`` from closed, ``c`` the MLC's projection and ``f`` its calibration offset. A closed pair
    touches mechanically at ``c x``; its nominal tips are then ``x - f(-x)`` and ``x + f(x)``: touching rounded ends pass
    what a gap of ``f(x) + f(-x)`` (about 0.5 mm on the axis) passes. Adjacent pairs may not interdigitate: the model's
    opposite banks overlap when they do."""
    centres = np.asarray(centres_mm, dtype=float)
    bounds = np.concatenate([[1.5 * centres[0] - 0.5 * centres[1]], 0.5 * (centres[1:] + centres[:-1]),
                             [1.5 * centres[-1] - 0.5 * centres[-2]]])
    left, right = np.zeros(len(centres)), np.zeros(len(centres))
    rows = []
    for k, y in enumerate(centres):
        band = next((b for b in bands if b[0] <= y < b[1]), None)
        if band is not None and band[3] > band[2]:
            xl, xr = float(band[2]), float(band[3])
            left[k], right[k] = c * (xl + float(f(-xl))), c * (xr - float(f(xr)))
            if left[k] >= right[k]:
                raise ValueError(f"a gap of {xr - xl:g} mm at y = {y:.1f} mm closes the leaves past touching")
        else:
            xc = float(band[2]) if band is not None else 0.0
            left[k] = right[k] = c * xc
            xl, xr = xc - float(f(-xc)), xc + float(f(xc))
        if bounds[k + 1] > -jaw_y_mm and bounds[k] < jaw_y_mm:
            rows.append([round(float(bounds[k]), 3), round(float(bounds[k + 1]), 3), round(xl, 3), round(xr, 3)])
    if np.any(right[:-1] < left[1:]) or np.any(right[1:] < left[:-1]):
        raise ValueError("adjacent leaf pairs interdigitate: the Versa model's opposite banks then overlap")
    return left, right, rows


def set_mlc_field(sim, versa, linac, mlc, jaws, bands, mm) -> dict:
    """Set the Y jaws, each leaf (:func:`mlc_leaf_positions`) and the X blocks of an MLC case; return what the harness
    needs to plan the same field: the jaws, the blocks and each leaf pair's row at isocenter."""
    import scipy.interpolate

    center_mlc, center_curve_mlc = 349.3, 349.3 - 7.5        # the Versa model's planes, from the source (mm)
    center_curve_jaws = 470.5 - (77.0 / 2 - 35.0)
    mpos, moff = versa.retrieve_offset_data_to_apply("from thales", "mlc")
    jpos, joff = versa.retrieve_offset_data_to_apply("from thales", "jaw")
    f = scipy.interpolate.interp1d(mpos, moff, kind="cubic")
    fj = scipy.interpolate.interp1d(jpos, joff, kind="cubic")
    y_mlc = np.asarray(mlc.translation)[:, 1]
    nb = len(y_mlc) // 2
    if not np.allclose(y_mlc[:nb], y_mlc[nb:]):
        raise SystemExit("the Versa MLC's two banks are not paired by index")
    order = np.argsort(y_mlc[:nb])
    centres = y_mlc[:nb][order] * SAD_MM / center_mlc                 # leaf-pair centres at isocenter
    try:
        left, right, rows = mlc_leaf_positions(centres, bands, f, center_curve_mlc / SAD_MM)
    except ValueError as e:
        raise SystemExit(str(e))
    pos = np.zeros(2 * nb)
    pos[order], pos[order + nb] = left, right
    jaw = (center_curve_jaws / SAD_MM) * (MLC_JAW_Y_MM - float(fj(MLC_JAW_Y_MM)))
    versa.field(mlc, jaws, pos * mm, np.array([-jaw, jaw]) * mm)
    # the X blocks: tungsten, their inner bottom corners on the rays to +-MLC_BLOCK_X_MM at isocenter
    z_src = linac.size[2] / 2 - 5.6 * mm                     # the target, in the head's frame (as the source)
    d_iso = (linac.translation[2] + z_src) / mm               # source to isocenter
    edge = MLC_BLOCK_X_MM * X_BLOCK_TO_MM / d_iso
    for side, name in ((-1, "xblock_left"), (1, "xblock_right")):
        b = sim.add_volume("Box", name)
        b.mother = linac.name
        b.material = "G4_W"
        b.size = [120 * mm, 200 * mm, (X_BLOCK_TO_MM - X_BLOCK_FROM_MM) * mm]
        b.translation = [side * (edge + 60.0) * mm, 0, z_src - 0.5 * (X_BLOCK_FROM_MM + X_BLOCK_TO_MM) * mm]
    return dict(jaw_y_mm=[-MLC_JAW_Y_MM, MLC_JAW_Y_MM], block_x_mm=[-MLC_BLOCK_X_MM, MLC_BLOCK_X_MM],
                blocks=f"G4_W, {X_BLOCK_TO_MM - X_BLOCK_FROM_MM:g} mm thick, {X_BLOCK_FROM_MM:g}-{X_BLOCK_TO_MM:g} mm from the source",
                bands=[list(b) for b in bands], rows=rows, leaf_pitch_mm=round(float(np.mean(np.diff(centres))), 4),
                tips="nominal: the Versa model's leaf calibration (from thales) puts the 50 % edge on them; closed pairs touch")


def save_reference(path: Path, dose: np.ndarray, uncertainty: np.ndarray, spacing_mm: float, origin_mm, primaries: int) -> None:
    """Compact storage: the dose relative to its maximum as float16 (3 significant digits, far below the
    statistical noise) and the relative uncertainty in per mille as uint16; about a quarter of float32."""
    dose = np.asarray(dose, dtype=np.float64)
    top = float(dose.max()) if dose.size else 0.0
    rel = (dose / top) if top > 0 else dose
    unc = np.clip(np.nan_to_num(np.asarray(uncertainty, dtype=np.float64), nan=1.0) * 1000.0, 0, 65535)
    np.savez_compressed(path, dose_rel=rel.astype(np.float16), dose_max=np.float64(top), uncertainty_permille=np.rint(unc).astype(np.uint16),
                        spacing_mm=np.array([spacing_mm] * 3, dtype=float), origin_mm=np.asarray(origin_mm, dtype=float), primaries=int(primaries))


def load_reference_arrays(path: Path):
    """``(dose Gy per primary, relative uncertainty, spacing, origin, primaries)`` from either storage format."""
    d = np.load(path)
    if "dose_rel" in d.files:
        dose = d["dose_rel"].astype(np.float32) * np.float32(d["dose_max"])
        unc = d["uncertainty_permille"].astype(np.float32) / 1000.0
    else:
        dose, unc = d["dose"].astype(np.float32), d["uncertainty"].astype(np.float32)
    return dose, unc, tuple(float(v) for v in d["spacing_mm"]), tuple(float(v) for v in d["origin_mm"]), int(d["primaries"])


def compact(path: Path) -> None:
    """Rewrite a reference written in the float32 format in the compact one."""
    dose, unc, spacing, origin, primaries = load_reference_arrays(path)
    save_reference(path, dose, unc, spacing[0], origin, primaries)


def merge_runs(case: str, run_dirs, out_dir: Path) -> dict:
    """One reference from runs of a case with different seeds, each in its own directory: the dose weighted by each
    run's primaries, the absolute uncertainties added in quadrature. One OpenGATE process stops gaining speed beyond
    about a dozen threads, so a long reference runs as several processes and is merged."""
    runs = [Path(d) for d in run_dirs]
    provs = [json.loads((d / f"{case}.json").read_text(encoding="utf-8")) for d in runs]
    seeds = [int(p["seed"]) for p in provs]
    if len(set(seeds)) != len(seeds):
        raise ValueError(f"{case}: runs share a seed: {seeds}")
    if any(p.get("dose_per") != "event" for p in provs):
        raise ValueError(f"{case}: every run must store the dose per simulated primary")
    total, acc, var, grid = 0, None, None, None
    for d in runs:
        dose, unc, spacing, origin, n = load_reference_arrays(d / f"{case}.npz")
        dose = dose.astype(np.float64)
        if grid is None:
            grid, acc, var = (dose.shape, spacing, origin), np.zeros_like(dose), np.zeros_like(dose)
        elif (dose.shape, spacing, origin) != grid:
            raise ValueError(f"{d}: grid differs from {runs[0]}")
        acc += n * dose
        var += (n * unc.astype(np.float64) * dose) ** 2
        total += n
    dose = acc / total
    with np.errstate(divide="ignore", invalid="ignore"):
        unc = np.where(dose > 0, np.sqrt(var) / total / dose, 1.0)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{case}.npz"
    save_reference(out, dose, unc, grid[1][0], grid[2], total)
    prov = dict(provs[0])
    prov.update(primaries=total, seed=seeds, runs=len(runs), run_primaries=[int(p["primaries"]) for p in provs],
                elapsed_s=round(sum(float(p["elapsed_s"]) for p in provs), 1), date=max(p["date"] for p in provs), file=out.name)
    (out_dir / f"{case}.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    return prov


def phantom_layers(case: str):
    """``(depth_from_mm, depth_to_mm, material)`` of the stacked boxes, from the surface down."""
    layers, depth = [], 0.0
    for d0, d1, rho in sorted(SLABS[case], key=lambda t: t[0]):
        if d0 > depth:
            layers.append((depth, d0, "G4_WATER"))
        layers.append((d0, d1, _slab_material(rho)))
        depth = d1
    if depth < PHANTOM_MM:
        layers.append((depth, PHANTOM_MM, "G4_WATER"))
    return layers


def read_layers(actors):
    """The layers' dose and uncertainty images joined along the depth axis in radiarch's convention."""
    import itk
    doses, uncs = [], []
    for actor in actors:
        arr = itk.array_from_image(itk.imread(str(actor.get_output_path("dose")))).astype(np.float32)
        up = actor.get_output_path("dose_uncertainty")
        unc = itk.array_from_image(itk.imread(str(up))).astype(np.float32) if Path(up).is_file() else np.zeros_like(arr)
        doses.append(to_radiarch(arr)); uncs.append(to_radiarch(unc))
    return np.concatenate(doses, axis=1), np.concatenate(uncs, axis=1)


def _slab_material(rho) -> str:
    return "G4_WATER" if isinstance(rho, str) or abs(float(rho) - 1.0) < 1e-9 else f"WATER_{float(rho):g}"


def to_radiarch(arr_mc: np.ndarray) -> np.ndarray:
    """The actor image ``(z_mc, y_mc, x_mc)`` with the beam along -z and the surface at the top
    becomes radiarch's ``(z, y, x)`` with depth along +y: ``dose[z, y, x] = mc[nz-1-y, z, x]``."""
    return np.ascontiguousarray(np.transpose(arr_mc[::-1], (1, 0, 2)), dtype=np.float32)


# ---------------------------------------------------------------------------
# Pencil-beam kernel for the native photon engine (R8)
# ---------------------------------------------------------------------------

PENCIL_LATERAL_MM = 400.0
PENCIL_DEPTH_MM = 300.0
PENCIL_FINE = (81, 1.0)          # voxels across, lateral spacing (mm): +-40 mm at 1 mm
PENCIL_COARSE = (81, 5.0)        # +-200 mm at 5 mm
PENCIL_DEPTH_SPACING = 2.0


def build_pencil(primaries: int, threads: int, seed: int, out_dir: Path, radius_mm: float = 0.5):
    """A narrow pencil of the Mohan 6 MV spectrum (radius ``radius_mm`` at the surface, which is the
    isocenter plane, 1000 mm from a point source) into a 400 x 400 x 300 mm water box, scored by two dose
    actors on the same volume (no internal boundary): 1 mm laterally to +-40 mm for the core, 5 mm to
    +-200 mm for the scatter tail, 2 mm in depth. Step-converged settings as the references."""
    import opengate as gate

    mm, m, MeV, deg = gate.g4_units.mm, gate.g4_units.m, gate.g4_units.MeV, gate.g4_units.deg
    sim = gate.Simulation()
    sim.g4_verbose = False
    sim.number_of_threads = int(threads)
    sim.random_seed = int(seed)
    sim.output_dir = str(out_dir)
    sim.progress_bar = False
    sim.check_volumes_overlap = False
    world = sim.world
    world.size = [2 * m, 2 * m, 2.6 * m]
    world.material = "G4_Galactic"           # the pencil reaches the surface unscattered, as the kernel assumes
    box = sim.add_volume("Box", "phantom")
    box.size = [PENCIL_LATERAL_MM * mm, PENCIL_LATERAL_MM * mm, PENCIL_DEPTH_MM * mm]
    box.material = "G4_WATER"
    box.translation = [0, 0, -PENCIL_DEPTH_MM / 2 * mm]
    edges, weights = read_egsnrc_spectrum(SPECTRUM)
    src = sim.add_source("GenericSource", "pencil")
    src.particle = "gamma"
    src.position.type = "point"
    src.position.translation = [0, 0, SAD_MM * mm]
    src.direction.type = "iso"
    theta = float(np.degrees(np.arctan(radius_mm / SAD_MM)))
    src.direction.theta = [0, theta * deg]
    src.direction.phi = [0, 360 * deg]
    src.energy.type = "spectrum_histogram"
    src.energy.spectrum_energy_bin_edges = [float(e) * MeV for e in edges]
    src.energy.spectrum_weights = [float(w) for w in weights]
    src.n = per_thread(primaries, threads)
    pm = sim.physics_manager
    pm.physics_list_name = "G4EmStandardPhysics_option3"
    pm.set_production_cut("world", "all", 1 * mm)
    pm.user_limits_particles = ["e-", "e+"]
    pm.set_production_cut(box.name, "all", CUT_MM * mm)
    pm.set_max_step_size(box.name, MAX_STEP_MM * mm)
    actors = {}
    nz = int(round(PENCIL_DEPTH_MM / PENCIL_DEPTH_SPACING))
    for name, (n, sp) in (("fine", PENCIL_FINE), ("coarse", PENCIL_COARSE)):
        a = sim.add_actor("DoseActor", f"dose_{name}")
        a.attached_to = box.name
        a.size = [n, n, nz]
        a.spacing = [sp * mm, sp * mm, PENCIL_DEPTH_SPACING * mm]
        a.output_filename = f"pencil_{name}.mhd"
        a.dose.active = True
        a.dose_uncertainty.active = True
        a.edep.active = False
        actors[name] = a
    stats = sim.add_actor("SimulationStatisticsActor", "stats")
    prov = dict(case="pencil_6mv", radius_mm=radius_mm, area_mm2=float(np.pi * radius_mm ** 2), primaries=int(primaries), threads=int(threads),
                seed=int(seed), sad_mm=SAD_MM, ssd_mm=SAD_MM, spectrum=f"Mohan 6 MV (EGSnrc {SPECTRUM.name}), point source",
                physics=f"G4EmStandardPhysics_option3; cut {CUT_MM:g} mm and e-/e+ max step {MAX_STEP_MM:g} mm in the phantom; vacuum outside",
                phantom_mm=[PENCIL_LATERAL_MM, PENCIL_LATERAL_MM, PENCIL_DEPTH_MM],
                grids={"fine": {"n": PENCIL_FINE[0], "spacing_mm": PENCIL_FINE[1]}, "coarse": {"n": PENCIL_COARSE[0], "spacing_mm": PENCIL_COARSE[1]},
                       "depth_spacing_mm": PENCIL_DEPTH_SPACING})
    return sim, actors, stats, prov


def cpu_model() -> str:
    """The processor, for the provenance record (the repository is public: no host names)."""
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return f"{line.split(':', 1)[1].strip()}, {os.cpu_count()} logical CPUs"
    except OSError:
        pass
    return platform.processor() or "unknown CPU"


def radial_profiles(dose_zyx: np.ndarray, unc_zyx: np.ndarray, spacing_mm: float, bin_mm: float, r_max_mm: float):
    """Mean dose and its uncertainty in annuli around the axis, per depth slice. ``dose_zyx`` is in radiarch
    order (depth along axis 1, lateral axes 0 and 2, axis at the centre voxel)."""
    nl = dose_zyx.shape[0]
    c = (nl - 1) / 2.0
    x = (np.arange(nl) - c) * spacing_mm
    rr = np.sqrt(x[:, None] ** 2 + x[None, :] ** 2)                 # (z_lateral, x_lateral)
    edges = np.arange(0.0, r_max_mm + bin_mm, bin_mm)
    idx = np.digitize(rr, edges) - 1
    nb = len(edges) - 1
    prof = np.zeros((dose_zyx.shape[1], nb)); err = np.zeros_like(prof); count = np.zeros(nb)
    for b in range(nb):
        m = idx == b
        count[b] = m.sum()
        if not count[b]:
            continue
        sub = dose_zyx[:, :, :].transpose(1, 0, 2)[:, m]            # (depth, voxels in the annulus)
        prof[:, b] = sub.mean(axis=1)
        u = (unc_zyx.transpose(1, 0, 2)[:, m] * sub)
        err[:, b] = np.sqrt((u ** 2).sum(axis=1)) / max(count[b], 1)
    centres = np.array([rr[idx == b].mean() if count[b] else (edges[b] + edges[b + 1]) / 2 for b in range(nb)])
    return centres, prof, err


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="OpenGATE photon references for the radiarch validation harness")
    ap.add_argument("--case", choices=sorted(SLABS))
    ap.add_argument("--pencil", action="store_true", help="the pencil-beam kernel of the native photon engine (R8) instead of a phantom case")
    ap.add_argument("--compact", type=Path, nargs="*", default=None, help="rewrite existing references in the compact format and exit")
    ap.add_argument("--primaries", type=float, default=2e7)
    ap.add_argument("--threads", type=int, default=16)
    ap.add_argument("--spacing-mm", type=float, default=2.5)
    ap.add_argument("--seed", type=int, default=20261021)
    ap.add_argument("--source", default="spectrum", choices=["spectrum", "versa"])
    ap.add_argument("--out", type=Path, default=HERE / "references" / "mc")
    ap.add_argument("--work", type=Path, default=None, help="directory for OpenGATE's intermediate images; default validation/mc/work")
    ap.add_argument("--visu", action="store_true")
    ap.add_argument("--merge", type=Path, nargs="+", default=None, help="merge the --case runs in these directories into --out and exit")
    args = ap.parse_args(argv)
    if args.compact is not None:
        for f in args.compact:
            compact(f); print("compacted", f)
        return 0
    if args.merge:
        if not args.case:
            ap.error("--merge needs --case")
        prov = merge_runs(args.case, args.merge, args.out)
        print(f"merged {prov['runs']} runs of {args.case}: {prov['primaries']:.3g} primaries into {args.out / prov['file']}")
        return 0
    if args.pencil:
        return run_pencil(args)
    if not args.case:
        ap.error("--case is required")
    args.out.mkdir(parents=True, exist_ok=True)
    # intermediate images (hundreds of MB) stay out of the package: validation/mc/work (gitignored)
    work = args.work or (HERE.parents[2] / "validation" / "mc" / "work")
    work.mkdir(parents=True, exist_ok=True)

    import opengate

    sim, dose, stats, prov = build(args.case, int(args.primaries), args.threads, args.spacing_mm, args.seed, args.source, work, args.visu)
    t0 = time.time()
    sim.run()
    elapsed = time.time() - t0
    print(stats)

    dose_r, unc_r = read_layers(dose)
    events = int(stats.counts.events)                          # every thread runs the source's n
    dose_r = dose_r / float(events)                            # Gy per primary
    s = float(args.spacing_mm)
    n = dose_r.shape[0]
    half = (n - 1) / 2.0 * s
    origin = (-half, s / 2.0, -half)                           # (x, y, z): lateral centred, surface at y = 0
    out = args.out / f"{args.case}.npz"
    save_reference(out, dose_r, unc_r, s, origin, events)
    prov.update(primaries=events, dose_per="event", elapsed_s=round(elapsed, 1), opengate_version=getattr(opengate, "__version__", "10.1.1"),
                python=sys.version.split()[0], cpu=cpu_model(), date=_dt.datetime.now().isoformat(timespec="seconds"),
                geant4_data="downloaded by opengate_core", file=out.name, shape_zyx=list(dose_r.shape), origin_mm=list(origin),
                units="Gy per primary (simulated events); uncertainty relative")
    (args.out / f"{args.case}.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    cax = dose_r[n // 2, :, n // 2]
    k = int(np.argmax(cax))
    print(f"wrote {out}: max {dose_r.max():.3e} Gy/primary, d_max {origin[1] + k * s:.1f} mm, "
          f"PDD10 {np.interp(100.0, origin[1] + np.arange(len(cax)) * s, cax) / cax[k] * 100:.1f} %, elapsed {elapsed:.0f} s")
    return 0




def run_pencil(args) -> int:
    """Run the pencil case and write ``pencil_6mv.npz``: radial depth-dose tables (geometric radius at depth,
    inverse square included, dose per primary) from the fine core grid and the coarse tail grid."""
    import itk
    import opengate

    work = args.work or (HERE.parents[2] / "validation" / "mc" / "work")
    work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    sim, actors, stats, prov = build_pencil(int(args.primaries), args.threads, args.seed, work)
    t0 = time.time(); sim.run(); elapsed = time.time() - t0
    print(stats)
    events = int(stats.counts.events)
    out = {}
    for name, (n, sp) in (("fine", PENCIL_FINE), ("coarse", PENCIL_COARSE)):
        a = actors[name]
        d = to_radiarch(itk.array_from_image(itk.imread(str(a.get_output_path("dose")))).astype(np.float64)) / float(events)
        u = to_radiarch(itk.array_from_image(itk.imread(str(a.get_output_path("dose_uncertainty")))).astype(np.float64))
        r_max = (n - 1) / 2.0 * sp
        centres, prof, err = radial_profiles(d, np.nan_to_num(u, nan=1.0), sp, 0.5 if name == "fine" else 5.0, r_max)
        out[f"{name}_r_mm"], out[f"{name}_dose"], out[f"{name}_err"] = centres, prof, err
        out[f"{name}_cax"] = d[(n - 1) // 2, :, (n - 1) // 2]
    depth = PENCIL_DEPTH_SPACING / 2 + np.arange(out["fine_dose"].shape[0]) * PENCIL_DEPTH_SPACING
    path = args.out / "pencil_6mv.npz"
    np.savez_compressed(path, depth_mm=depth, primaries=events, area_mm2=prov["area_mm2"], sad_mm=SAD_MM, **out)
    prov.update(primaries=events, dose_per="event", elapsed_s=round(elapsed, 1), opengate_version=getattr(opengate, "__version__", "10.1.1"), python=sys.version.split()[0],
                cpu=cpu_model(), date=_dt.datetime.now().isoformat(timespec="seconds"), file=path.name,
                units="dose per primary (Gy), geometric radius at depth, inverse square included")
    (args.out / "pencil_6mv.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    k = int(np.argmax(out["fine_dose"][:, 0]))
    print(f"wrote {path}: axis maximum at {depth[k]:.0f} mm, elapsed {elapsed:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
