"""The nuclear halo's share of the lateral variance (nuclear on minus off) per MCsquare build, against Geant4's.
python table.py SUMMARY [TAG]: TAG names the build whose electromagnetic-only runs are the baseline (default r42)."""
import re, sys
rows = {}
for l in open(sys.argv[1]):
    c = l.split()
    if len(c) == 7 and c[0] != "run":
        rows[c[0]] = [float(v) for v in c[1:]]
# columns: R80, peak/entrance, rms@0.5, halo@0.5, rms@0.8, halo@0.8
for E in ("200", "225"):
    g_n, g_e = rows.get(f"g4-{E}-QGSP_BIC_EMZ"), rows.get(f"g4-{E}-G4EmStandardPhysics_option4")
    if not (g_n and g_e):
        continue
    m_e = rows[f"w{E}e-{sys.argv[2] if len(sys.argv) > 2 else 'r42'}"]
    print(f"\n{E} MeV  (EM only: Geant4 rms {g_e[2]:.2f}/{g_e[4]:.2f} mm, MCsquare {m_e[2]:.2f}/{m_e[4]:.2f} mm at 0.5/0.8 R80)")
    print(f"{'code':10} {'rms 0.5R':>8} {'dvar 0.5R':>10} {'vs G4':>7} {'>10mm 0.5R':>11} {'rms 0.8R':>8} {'dvar 0.8R':>10} {'vs G4':>7} {'>10mm 0.8R':>11} {'pk/ent':>7}")
    gv5, gv8 = g_n[2] ** 2 - g_e[2] ** 2, g_n[4] ** 2 - g_e[4] ** 2
    print(f"{'Geant4':10} {g_n[2]:8.2f} {gv5:10.1f} {'':>7} {g_n[3]:11.2f} {g_n[4]:8.2f} {gv8:10.1f} {'':>7} {g_n[5]:11.2f} {g_n[1]:7.3f}")
    for tag in sorted({k.split("-", 1)[1] for k in rows if k.startswith(f"w{E}n-")}):
        r = rows.get(f"w{E}n-{tag}")
        if not r: continue
        v5, v8 = r[2] ** 2 - m_e[2] ** 2, r[4] ** 2 - m_e[4] ** 2
        print(f"{tag:10} {r[2]:8.2f} {v5:10.1f} {100*(v5/gv5-1):+6.0f}% {r[3]:11.2f} {r[4]:8.2f} {v8:10.1f} {100*(v8/gv8-1):+6.0f}% {r[5]:11.2f} {r[1]:7.3f}")
