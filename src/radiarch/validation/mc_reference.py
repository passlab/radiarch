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
    field_mm = FIELDS[case]

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
    versa.set_rectangular_field(mlc, jaws, field_mm * mm, field_mm * mm, SAD_MM * mm)
    sim.volume_manager.get_volume("linac_box_mlc").material = "G4_Galactic"

    if source == "spectrum":
        edges, weights = read_egsnrc_spectrum(SPECTRUM)
        src = sim.add_source("GenericSource", "photons")
        src.particle = "gamma"
        src.attached_to = linac.name
        z_linac = linac.size[2]
        src.position.type = "point"
        src.position.translation = [0, 0, z_linac / 2 - 5.6 * mm]          # the target position of the Versa model
        theta_max = float(np.degrees(np.arctan(0.75 * field_mm / SAD_MM))) + 0.5
        src.direction.type = "iso"
        src.direction.theta = [0, theta_max * deg]
        src.direction.phi = [0, 360 * deg]
        src.energy.type = "spectrum_histogram"
        src.energy.spectrum_energy_bin_edges = [float(e) * MeV for e in edges]
        src.energy.spectrum_weights = [float(w) for w in weights]
        src.n = int(primaries)
        spectrum_note = f"Mohan 6 MV (EGSnrc {SPECTRUM.name}), point source, flat fluence within {theta_max:.2f} deg"
    elif source == "versa":
        # the full head from its electron source, as in opengate's test019: slow, for the record
        full = versa.add_linac(sim, "versa", SAD_MM * mm)
        src = versa.add_electron_source(sim, full.name, 6.49 * MeV, 1 * mm, 0.5 * mm)
        versa.enable_brem_splitting(sim, full.name, splitting_factor=10)
        src.n = int(primaries)
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

    n = int(round(PHANTOM_MM / spacing_mm))
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
    return sim, dose, stats, dict(case=case, field_mm=field_mm, construction="stacked sibling boxes, one dose actor each", primaries=int(primaries), threads=int(threads), seed=int(seed),
                                  spacing_mm=float(spacing_mm), source=source, spectrum=spectrum_note, slabs=SLABS[case],
                                  physics=f"G4EmStandardPhysics_option3; cuts 1 mm world, {CUT_MM:g} mm phantom; e-/e+ max step {MAX_STEP_MM:g} mm in the phantom",
                                  collimation="Elekta Versa HD jaws + Agility MLC (opengate.contrib.linacs.elektaversa), rectangular field at isocenter")


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
    src.n = int(primaries)
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
    args = ap.parse_args(argv)
    if args.compact is not None:
        for f in args.compact:
            compact(f); print("compacted", f)
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
    dose_r = dose_r / float(args.primaries)                    # Gy per primary
    s = float(args.spacing_mm)
    n = dose_r.shape[0]
    half = (n - 1) / 2.0 * s
    origin = (-half, s / 2.0, -half)                           # (x, y, z): lateral centred, surface at y = 0
    out = args.out / f"{args.case}.npz"
    save_reference(out, dose_r, unc_r, s, origin, int(args.primaries))
    prov.update(elapsed_s=round(elapsed, 1), opengate_version=getattr(opengate, "__version__", "10.1.1"), python=sys.version.split()[0],
                cpu=cpu_model(), date=_dt.datetime.now().isoformat(timespec="seconds"), geant4_data="downloaded by opengate_core",
                file=out.name, shape_zyx=list(dose_r.shape), origin_mm=list(origin), units="Gy per primary; uncertainty relative")
    (args.out / f"{args.case}.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    cax = dose_r[n // 2, :, n // 2]
    k = int(np.argmax(cax))
    print(f"wrote {out}: max {dose_r.max():.3e} Gy/primary, d_max {origin[1] + k * s:.1f} mm, "
          f"PDD10 {np.interp(100.0, origin[1] + np.arange(n) * s, cax) / cax[k] * 100:.1f} %, elapsed {elapsed:.0f} s")
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
    out = {}
    for name, (n, sp) in (("fine", PENCIL_FINE), ("coarse", PENCIL_COARSE)):
        a = actors[name]
        d = to_radiarch(itk.array_from_image(itk.imread(str(a.get_output_path("dose")))).astype(np.float64)) / float(args.primaries)
        u = to_radiarch(itk.array_from_image(itk.imread(str(a.get_output_path("dose_uncertainty")))).astype(np.float64))
        r_max = (n - 1) / 2.0 * sp
        centres, prof, err = radial_profiles(d, np.nan_to_num(u, nan=1.0), sp, 0.5 if name == "fine" else 5.0, r_max)
        out[f"{name}_r_mm"], out[f"{name}_dose"], out[f"{name}_err"] = centres, prof, err
        out[f"{name}_cax"] = d[(n - 1) // 2, :, (n - 1) // 2]
    depth = PENCIL_DEPTH_SPACING / 2 + np.arange(out["fine_dose"].shape[0]) * PENCIL_DEPTH_SPACING
    path = args.out / "pencil_6mv.npz"
    np.savez_compressed(path, depth_mm=depth, primaries=int(args.primaries), area_mm2=prov["area_mm2"], sad_mm=SAD_MM, **out)
    prov.update(elapsed_s=round(elapsed, 1), opengate_version=getattr(opengate, "__version__", "10.1.1"), python=sys.version.split()[0],
                cpu=cpu_model(), date=_dt.datetime.now().isoformat(timespec="seconds"), file=path.name,
                units="dose per primary (Gy), geometric radius at depth, inverse square included")
    (args.out / "pencil_6mv.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    k = int(np.argmax(out["fine_dose"][:, 0]))
    print(f"wrote {path}: axis maximum at {depth[k]:.0f} mm, elapsed {elapsed:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
