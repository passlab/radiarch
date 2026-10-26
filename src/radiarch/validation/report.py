"""The validation document (roadmap R7): one signed record per engine version.

``python -m radiarch.validation.report [--results validation/results/<run>] [--out validation/reports]``

Compiles the newest harness run (or the one named) into one document per
engine — CCC photons, MCsquare protons, and the engine-independent services
(geometry, evaluation, writers) — with the engine's identity (binary and
kernel digests, version, build notes), the radiarch commit, the processor,
every case with its checks and their sources, the known limitations, and a
signature block for the physicist and the project lead. The document is
evidence: it records what was tested against which reference and what the
numbers were; it never grants an acceptance level, and it says so on its
first line.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..models.common import RESEARCH_USE_ONLY

RADIARCH_ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = RADIARCH_ROOT / "validation" / "results"
REPORTS_DIR = RADIARCH_ROOT / "validation" / "reports"

# Which cases speak for which engine. Cases not listed go to the services document.
ENGINE_CASES: Dict[str, Dict[str, Any]] = {
    "ccc": {
        "title": "CCC photon engine (WiscPlan collapsed cone, radiarch build)",
        "kinds": ("photon_pdd", "photon_profile", "photon_slab", "photon_output_vs_field", "photon_vs_mc", "photon_vs_pyradplan", "dij_consistency",
                  "tg119_planning", "lung_e2e"),
        "limitations": [
            "Generic 6 MV kernels and no linac head model: output factors, head scatter and off-axis softening are not modelled; "
            "the engine transports photons only, so the build-up is longer than a measured 6 MV beam.",
            "The shipped engine constants truncate scatter (dose cutoff 0.5 % of a beamlet's peak, 2 cm safety radius); radiarch's "
            "build takes both at run time (CCC_DOSE_CUTOFF, CCC_RSAFE_CM) and the 'full' setting removes the truncation at ~45x the "
            "cost. The comparison with the Monte Carlo reference (the kernels' own spectrum) is in the photon_vs_mc checks above; the full setting overshoots at depth, so the shipped setting stays the default for influence matrices and final doses.",
            "The Monte Carlo references share the engine's assumptions where the engine has them (water composition at the slab "
            "densities, a flat primary fluence collimated by jaws and MLC, no flattening filter), so they test transport, not the linac. "
            "They are step-converged (0.5 mm electron steps, 0.1 mm cut; a single and a split water box agree within 0.5 %).",
            "R8 findings against the pencil-beam engine: the shipped scatter truncation makes the central-axis dose almost "
            "independent of field size (4 x 4 and 6 x 6 cm give the 10 x 10 cm dose at 10 cm depth; output factors 1.000) and makes "
            "the depth dose depend on the beamlet size (PDD10 about 2.5 points lower with 5 mm beamlets than with the 10 mm "
            "beamlets this record validated). Small fields are overdosed at depth by up to ~10 %.",
            "Before engine version 1.1.0 (R8) the gantry turned the opposite way to IEC 61217: lateral and oblique beams entered "
            "from the mirrored side. Plans optimized within radiarch were self-consistent; DICOM imports and exports were not.",
        ],
    },
    "pb": {
        "title": "Native photon pencil-beam engine (radiarch, roadmap R8)",
        "kinds": ("photon_pdd", "photon_profile", "photon_output_vs_field", "pb_vs_mc", "pb_vs_ccc", "dij_consistency", "lung_sbrt_vmat",
                  "lung_vmat", "hn_sib_vmat", "lung_4d", "protocol_reproduces", "protocol_batch"),
        "limitations": [
            "The kernel is a Monte Carlo pencil kernel of the Mohan 6 MV spectrum in water (the CCC kernels' spectrum), decomposed "
            "into a few depth-weighted components; there is no linac head model (no head scatter or off-axis softening), and the "
            "field edge is an ideal edge blurred by a Gaussian fluence penumbra fitted to the Monte Carlo reference.",
            "Heterogeneities change the radiological depth and the lateral spread: the kernel's part within 30 mm is stretched "
            "by the local density to the power -0.9. The two parameters were fitted to the Monte Carlo lung slabs (2 x 2 and "
            "10 x 10 cm), so the lung checks are consistency checks; the photon scatter beyond 30 mm is not scaled and the "
            "build-down and re-build-up at interfaces are not modelled.",
            "The influence matrix stops 80 mm from each beamlet and thins its small entries by an unbiased roulette; final and "
            "segment doses use the full 200 mm kernel. Optimization doses therefore differ slightly from the final dose.",
        ],
    },
    "mcsquare": {
        "title": "MCsquare proton engine (radiarch driver)",
        "kinds": ("proton_range", "proton_bragg_peak", "dij_consistency"),
        "limitations": [
            "Water phantom tests use a water-only calibration; clinical cases keep the Schneider tables, under which HU 0 is a "
            "soft-tissue blend about 1-3 % denser than water.",
            "The beam data library is the generic IBA library shipped with the engine, not a commissioned machine.",
        ],
    },
    "services": {
        "title": "Engine-independent services (geometry, registration, evaluation, DICOM RT)",
        "kinds": ("geometry_volumes", "dvh_crosscheck", "gamma_crosscheck", "rt_roundtrip", "registration_4d", "replan_cbct"),
        "limitations": [
            "Gamma and DVH are checked against independent implementations (pymedphys, dicompyler-core), not against measurement.",
            "Registration is checked against a clinician's contours and contoured fiducials on another breathing phase, whose own "
            "phase-to-phase variability bounds the agreement; there is no ground-truth deformation.",
        ],
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=RADIARCH_ROOT, capture_output=True, text=True).stdout.strip()
    except Exception:  # pragma: no cover
        return ""


def _mcsquare_binary(root: Path) -> Optional[Path]:
    """The build the MCsquare launcher runs on this host (its own rule: AMD → generic; else the widest of
    AVX-512, AVX2, AVX, SSE4 the CPU reports)."""
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text()
    except OSError:
        return None
    if "AuthenticAMD" in cpuinfo:
        name = "MCsquare_linux"
    else:
        name = next((f"MCsquare_linux_{f}" for f in ("avx512", "avx2", "avx", "sse4") if f in cpuinfo), "MCsquare_linux")
    p = Path(root) / name
    return p if p.is_file() else None


def engine_identity(engine: str) -> Dict[str, Any]:
    """What exactly was tested: versions, digests, build notes."""
    out: Dict[str, Any] = {"engine": engine, "radiarch_commit": _git("rev-parse", "--short", "HEAD"), "radiarch_describe": _git("describe", "--always", "--dirty")}
    try:
        from importlib.metadata import version
        out["radiarch_version"] = version("radiarch")
    except Exception:
        out["radiarch_version"] = "0.1.0"
    if engine == "ccc":
        from ..services.dose_engines.ccc import CCCEngine
        from ..services.dose_engines.ccc_driver import CCCDriver

        drv = CCCDriver()
        out["engine_version"] = CCCEngine().version
        out["binary"] = str(drv.binary)
        out["binary_sha256"] = _sha256(drv.binary) if drv.binary.is_file() else "missing"
        out["kernel_fingerprint"] = drv.kernel_fingerprint() if drv.kernel_dir.is_dir() else "missing"
        out["build"] = ("rebuilt from the WiscPlan GPLv2 source with the dose cutoff and safety radius as run-time parameters "
                        "(engines/ccc/CCC_DoseEngine, g++ -O2); the defaults reproduce the shipped binary bit for bit (tests/test_goldens.py)")
        out["scatter_settings"] = {"shipped": {"dose_cutoff": drv.SHIPPED_DOSE_CUTOFF, "rsafe_cm": drv.SHIPPED_RSAFE_CM},
                                   "full": {"dose_cutoff": drv.FULL_SCATTER_DOSE_CUTOFF, "rsafe_cm": drv.FULL_SCATTER_RSAFE_CM}}
    elif engine == "mcsquare":
        from ..services.dose_engines.mcsquare import MCsquareEngine
        from ..services.dose_engines.mcsquare_driver import MCsquareDriver

        drv = MCsquareDriver()
        out["engine_version"] = MCsquareEngine().version
        binary = _mcsquare_binary(drv.assets.root)
        out["launcher"] = str(drv.assets.launcher)
        out["binary"] = str(binary) if binary else "n/a"
        out["binary_sha256"] = _sha256(binary) if binary and binary.is_file() else "missing"
        try:
            out["bdl_path"] = str(drv.assets.bdl_path(drv.bdl_name))
            out["bdl_sha256"] = _sha256(Path(out["bdl_path"])) if Path(out["bdl_path"]).is_file() else "missing"
            out["scanner"] = str(getattr(drv, "scanner_name", getattr(drv, "scanner", "n/a")))
        except Exception as exc:  # pragma: no cover
            out["bdl_path"] = f"unavailable ({exc})"
        out["build"] = "MCsquare binaries as shipped with OpenTPS 3.0.1 (engines/mcsquare; LICENSE-OpenTPS); driver: radiarch"
    elif engine == "pb":
        from ..services.dose_engines import pb as pbm
        eng = pbm.PencilBeamEngine()
        k = eng.kernel()
        cal = eng.calibration()
        out["engine_version"] = eng.version
        from ..services.dose_engines.pb_kernel import default_kernel_path
        out["kernel_table"] = _rel(default_kernel_path())
        out["kernel_fingerprint"] = k.fingerprint
        out["kernel_source"] = {kk: k.meta.get("source", {}).get(kk) for kk in ("file", "sha256", "primaries", "spectrum", "physics")}
        out["model"] = {"components": cal["n_components"], "penumbra_fwhm_mm": cal["penumbra_fwhm_mm"], "dmax_mm": cal["dmax_mm"],
                        "dij_cutoff_mm": pbm.DEFAULT_CUTOFF_MM, "dij_sampling_threshold": pbm.DEFAULT_SAMPLING,
                        "lateral_scaling": {"near_mm": pbm.DEFAULT_LATERAL_NEAR_MM, "exponent": pbm.DEFAULT_LATERAL_EXPONENT,
                                            "density_sigma_mm": pbm.DEFAULT_LATERAL_SIGMA_MM, "max_scale": pbm.DEFAULT_LATERAL_MAX_SCALE,
                                            "scales": pbm.DEFAULT_LATERAL_SCALES}}
        out["build"] = "radiarch's own NumPy engine (src/radiarch/services/dose_engines/pb.py); optional CuPy path"
    else:
        out["engine_version"] = out["radiarch_version"]
    return out


def _belongs(engine: str, result: Dict[str, Any]) -> bool:
    """Whether a case speaks for an engine's document: by kind, with the pencil-beam variants of the shared photon
    kinds (names ending ``_pb``) in the pb document only, and the cross-engine case in both photon documents."""
    kind, name = result.get("kind"), str(result.get("name", ""))
    if kind not in ENGINE_CASES[engine]["kinds"] and not (engine == "ccc" and kind == "pb_vs_ccc"):
        return False
    if name.endswith("_pb"):
        return engine == "pb"
    if engine == "pb" and kind in ("photon_pdd", "photon_profile", "photon_output_vs_field"):
        return False
    return True


def _rel(path: Any) -> str:
    """A path inside the repository as a repository-relative path (documents are shared, often publicly)."""
    try:
        return str(Path(str(path)).resolve().relative_to(RADIARCH_ROOT))
    except (ValueError, OSError):
        return str(path)


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return f"{line.split(':', 1)[1].strip()}, {os.cpu_count()} logical CPUs"
    except OSError:
        pass
    return platform.processor() or "unknown CPU"


def latest_run(results_dir: Path = RESULTS_DIR) -> Optional[Path]:
    runs = sorted(p for p in results_dir.glob("*") if (p / "results.json").is_file())
    return runs[-1] if runs else None


def load_run(run_dir: Path) -> Dict[str, Any]:
    return json.loads((run_dir / "results.json").read_text(encoding="utf-8"))


def _case_section(r: Dict[str, Any]) -> List[str]:
    checks = r.get("checks", [])
    n_pass = sum(1 for c in checks if c.get("passed") is True)
    n_fail = sum(1 for c in checks if c.get("passed") is False)
    n_info = sum(1 for c in checks if c.get("passed") is None)
    lines = [f"### {r['name']} — {r['status']} ({n_pass} pass, {n_fail} fail, {n_info} informative; {r.get('seconds', 0)} s)", ""]
    if r.get("error"):
        lines += ["```", str(r["error"]).strip()[-1200:], "```", ""]
    for n in r.get("notes", []):
        lines.append(f"- {n}")
    if checks:
        lines += ["", "| Check | Value | Target | Result | Source |", "|---|---|---|---|---|"]
        for c in checks:
            flag = "informative" if c.get("passed") is None else ("pass" if c.get("passed") else "**FAIL**")
            val = c.get("value")
            val = f"{val:.4g}" if isinstance(val, float) else val
            note = str(c.get("note", "")).replace("|", "/")
            lines.append(f"| {c['name']} | {val} | {c['target']} | {flag} | {note[:160]} |")
    lines.append("")
    return lines


def render(engine: str, run: Dict[str, Any], run_dir: Path) -> str:
    spec = ENGINE_CASES[engine]
    ident = engine_identity(engine)
    cases = [r for r in run["results"] if _belongs(engine, r)]
    statuses = [r["status"] for r in cases]
    verdict = ("every graded check passed" if cases and all(s in ("pass", "info", "skip") for s in statuses)
               else "graded checks failed; see the cases" if cases else "no case of this engine in the run")
    today = _dt.date.today().isoformat()
    lines = [
        f"# Validation record — {spec['title']}",
        "",
        f"**{RESEARCH_USE_ONLY}** This document records research targets against the commissioning literature; it is not a "
        "clinical commissioning and grants no acceptance level (a department that uses radiarch grants acceptance against this evidence).",
        "",
        f"Date: {today}. Harness run: `{'` + `'.join(run.get('runs', [run_dir.name]))}` (radiarch commit {run.get('radiarch_commit')}, {'fast mode' if run.get('fast') else 'full mode'}, "
        f"{_cpu_model()}, Python {run.get('python')}).",
        "",
        "## 1. What was tested",
        "",
        "| Item | Value |",
        "|---|---|",
    ]
    for k, v in ident.items():
        if isinstance(v, dict):
            v = json.dumps(v)
        elif k in ("binary", "launcher", "bdl_path", "scanner_dir"):
            v = _rel(v)
        lines.append(f"| {k} | `{v}` |" if k.endswith("sha256") or k in ("binary", "bdl_path", "scanner_dir", "kernel_fingerprint") else f"| {k} | {v} |")
    lines += ["", "## 2. Outcome", "", f"**{verdict}.**", "", "| Case | Kind | Status | Checks |", "|---|---|---|---|"]
    for r in cases:
        checks = r.get("checks", [])
        lines.append(f"| {r['name']} | {r['kind']} | **{r['status']}** | {sum(1 for c in checks if c.get('passed') is True)} pass, "
                     f"{sum(1 for c in checks if c.get('passed') is False)} fail, {sum(1 for c in checks if c.get('passed') is None)} informative |")
    lines += ["", "## 3. Cases", ""]
    for r in cases:
        lines += _case_section(r)
    lines += ["## 4. Known limitations", ""]
    for lim in spec["limitations"]:
        lines.append(f"- {lim}")
    lines += [
        "",
        "## 5. References",
        "",
        "Tolerances and reference values are those cited in `radiarch/validation/references/*.json` (AAPM MPPG 5.a/5.b, TG-119, TG-218, "
        "IAEA TECDOC-1583, TG-185/TG-224, NIST PSTAR, Beyer 2013, Mynampati 2012 for the TG-119 planning means, Bortfeld 1997 for the "
        "proton range model); each check carries its source in the table above.",
        "",
        "## 6. Signatures",
        "",
        "The signatories confirm that the run above was executed on the stated engine build and that the outcome is recorded here "
        "without alteration. Signing records a review of research evidence; it is not a clinical release.",
        "",
        "| Role | Name | Date | Signature |",
        "|---|---|---|---|",
        "| Medical physicist (review of physics cases) |  |  |  |",
        "| Project lead |  |  |  |",
        "",
        f"Generated by `radiarch.validation.report` from `{_rel(run_dir)}/results.json`.",
        "",
    ]
    return "\n".join(lines)


def merge_runs(run_dir: Path, extra: Sequence[Path] = ()) -> Dict[str, Any]:
    """The main run with cases rerun later (a single case after a grading fix, say) replacing theirs by name;
    the merged record lists every run it draws on."""
    run = load_run(run_dir)
    run["runs"] = [run_dir.name]
    for e in extra:
        other = load_run(Path(e))
        replaced = {r["name"]: r for r in other["results"]}
        run["results"] = [replaced.pop(r["name"], r) for r in run["results"]] + list(replaced.values())
        run["runs"].append(Path(e).name)
    return run


def write_reports(run_dir: Path, out_dir: Path = REPORTS_DIR, engines: Optional[List[str]] = None, extra: Sequence[Path] = ()) -> List[Path]:
    run = merge_runs(run_dir, extra)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for engine in engines or list(ENGINE_CASES):
        ident = engine_identity(engine)
        stamp = _dt.date.today().isoformat()
        path = out_dir / f"{stamp}-{engine}-v{ident.get('engine_version', '0')}-{run.get('radiarch_commit', 'unknown')}.md"
        path.write_text(render(engine, run, run_dir), encoding="utf-8")
        written.append(path)
    (out_dir / "LATEST.md").write_text("\n".join(f"- [{p.name}]({p.name})" for p in written) + "\n", encoding="utf-8")
    return written


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="radiarch validation document")
    ap.add_argument("--results", type=Path, default=None, help="a run directory under validation/results; default: the newest")
    ap.add_argument("--out", type=Path, default=REPORTS_DIR)
    ap.add_argument("--engines", nargs="*", default=None, choices=list(ENGINE_CASES))
    ap.add_argument("--also", nargs="*", type=Path, default=[], help="later runs whose cases replace the main run's by name")
    args = ap.parse_args(argv)
    run_dir = args.results or latest_run()
    if run_dir is None or not (run_dir / "results.json").is_file():
        print("no harness run found; run `python -m radiarch.validation.run --all` first", file=sys.stderr)
        return 2
    for p in write_reports(run_dir, args.out, args.engines, args.also):
        print("wrote", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
