"""Radiobiology (roadmap R5): EQD2 and BED, gEUD, LKB NTCP, Poisson TCP.

* ``eqd2``: the linear-quadratic equivalent dose in 2 Gy fractions,
  ``D (d + α/β) / (2 + α/β)`` with ``d = D / n``; ``bed = D (1 + d/(α/β))``.
  Applied per voxel, a total dose over ``n`` fractions becomes an EQD2
  volume on which 2 Gy constraints and the NTCP parameters below apply.
* ``geud``: the generalized equivalent uniform dose ``(mean(D^a))^(1/a)``
  (Niemierko 1999); ``a = 1/n`` of the LKB model.
* ``lkb_ntcp``: the Lyman–Kutcher–Burman model, ``Φ((gEUD − TD50) / (m TD50))``.
* ``poisson_tcp``: the Poisson model with the ``D50`` and ``γ50`` of a
  population (voxel-wise product of ``0.5^exp(2γ50(1 − D/D50)/ln 2)``).

The parameter sets ship with their sources and are literature values for
2 Gy fractions; they are research reference points, not a commissioning.
"""

from __future__ import annotations

import math
from typing import Dict, Optional

import numpy as np
from scipy.special import ndtr

from ..models.evaluation import NTCPParameters, TCPParameters


def eqd2(dose_gy, fractions: int, alpha_beta_gy: float) -> np.ndarray:
    """Per-voxel EQD2 of a total dose delivered in ``fractions`` equal fractions."""
    d = np.asarray(dose_gy, dtype=np.float64)
    n = int(fractions)
    if n < 1:
        raise ValueError("fractions must be >= 1")
    ab = float(alpha_beta_gy)
    if ab <= 0:
        raise ValueError("alpha/beta must be positive")
    per_fraction = d / n
    return d * (per_fraction + ab) / (2.0 + ab)


def bed(dose_gy, fractions: int, alpha_beta_gy: float) -> np.ndarray:
    d = np.asarray(dose_gy, dtype=np.float64)
    n = int(fractions)
    if n < 1:
        raise ValueError("fractions must be >= 1")
    return d * (1.0 + (d / n) / float(alpha_beta_gy))


def geud(doses, a: float) -> float:
    d = np.asarray(doses, dtype=np.float64).ravel()
    if d.size == 0:
        return 0.0
    if abs(a) < 1e-9:
        return float(np.exp(np.mean(np.log(np.maximum(d, 1e-12)))))
    return float(np.mean(np.power(np.maximum(d, 0.0), a)) ** (1.0 / a))


def lkb_ntcp(doses, td50_gy: float, m: float, n: float) -> Dict[str, float]:
    """LKB NTCP of a structure's (EQD2) voxel doses; returns gEUD and NTCP."""
    a = 1.0 / float(n) if n > 0 else 1e9
    g = geud(doses, a)
    t = (g - float(td50_gy)) / (float(m) * float(td50_gy))
    return {"geud_gy": g, "t": float(t), "ntcp": float(ndtr(t))}


def poisson_tcp(doses, d50_gy: float, gamma50: float, volume_fractions=None) -> Dict[str, float]:
    """Poisson TCP over the target voxels: the product of per-voxel control probabilities."""
    d = np.asarray(doses, dtype=np.float64).ravel()
    if d.size == 0:
        return {"tcp": 0.0, "eud_gy": 0.0}
    w = np.full(d.size, 1.0 / d.size) if volume_fractions is None else np.asarray(volume_fractions, dtype=np.float64).ravel()
    exponent = np.exp(2.0 * float(gamma50) * (1.0 - d / float(d50_gy)) / math.log(2.0))
    log_tcp_voxel = exponent * math.log(0.5)                      # ln of 0.5 ** exponent
    log_tcp = float(np.sum(w * log_tcp_voxel))
    tcp = math.exp(max(log_tcp, -700.0))
    # the uniform dose with the same TCP
    eud = float(d50_gy) * (1.0 - math.log(2.0) * math.log(max(-log_tcp, 1e-300) / math.log(2.0)) / (2.0 * float(gamma50))) if log_tcp < 0 else float(d.max())
    return {"tcp": tcp, "eud_gy": eud}


# ---------------------------------------------------------------------------
# Parameter sets (2 Gy per fraction; EQD2 inputs)
# ---------------------------------------------------------------------------

NTCP_MODELS: Dict[str, NTCPParameters] = {
    "lung-pneumonitis-quantec": NTCPParameters(
        model_id="lung-pneumonitis-quantec", structure="Lungs", endpoint="symptomatic radiation pneumonitis",
        td50_gy=30.8, m=0.37, n=0.99, alpha_beta_gy=3.0,
        source="Marks LB et al., QUANTEC lung, IJROBP 2010;76(3S):S70-S76 (fit to the pooled mean-lung-dose data; n≈1 so the gEUD is the mean dose)"),
    "esophagus-stricture-burman": NTCPParameters(
        model_id="esophagus-stricture-burman", structure="Esophagus", endpoint="clinical stricture / perforation",
        td50_gy=68.0, m=0.11, n=0.69, alpha_beta_gy=3.0,
        source="Burman C et al., IJROBP 1991;21:123-135 (LKB fit of the Emami tolerance data)"),
    "esophagus-esophagitis-quantec": NTCPParameters(
        model_id="esophagus-esophagitis-quantec", structure="Esophagus", endpoint="acute grade >= 2 esophagitis",
        td50_gy=47.0, m=0.36, n=1.0, alpha_beta_gy=10.0,
        source="Werner-Wasik M et al., QUANTEC esophagus, IJROBP 2010;76(3S):S86-S93 (mean-dose model, approximate fit reported there)"),
    "heart-pericarditis-martel": NTCPParameters(
        model_id="heart-pericarditis-martel", structure="Heart", endpoint="pericarditis",
        td50_gy=48.0, m=0.10, n=0.35, alpha_beta_gy=3.0,
        source="Martel MK et al., IJROBP 1998;40:155-161; cited by Gagliardi G et al., QUANTEC heart, IJROBP 2010;76(3S):S77-S85"),
    "parotid-xerostomia-quantec": NTCPParameters(
        model_id="parotid-xerostomia-quantec", structure="Parotid", endpoint="salivary flow < 25 % of baseline at 1 year",
        td50_gy=39.9, m=0.40, n=1.0, alpha_beta_gy=3.0,
        source="Dijkema T et al., IJROBP 2010;78:449-453 (combined Michigan-Utrecht data), summarized in Deasy JO et al., QUANTEC salivary, IJROBP 2010;76(3S):S58-S63"),
    "spinal-cord-myelopathy-burman": NTCPParameters(
        model_id="spinal-cord-myelopathy-burman", structure="SpinalCord", endpoint="myelopathy",
        td50_gy=66.5, m=0.175, n=0.05, alpha_beta_gy=2.0,
        source="Burman C et al., IJROBP 1991;21:123-135 (cervical cord); QUANTEC (Kirkpatrick 2010) reports 0.2 % at 50 Gy, 6 % at 60 Gy"),
    "rectum-bleeding-quantec": NTCPParameters(
        model_id="rectum-bleeding-quantec", structure="Rectum", endpoint="grade >= 2 late rectal toxicity",
        td50_gy=76.9, m=0.13, n=0.09, alpha_beta_gy=3.0,
        source="Michalski JM et al., QUANTEC rectum, IJROBP 2010;76(3S):S123-S129 (parameters from the pooled analyses cited there)"),
    "liver-rild-dawson": NTCPParameters(
        model_id="liver-rild-dawson", structure="Liver", endpoint="radiation-induced liver disease (primary liver cancer excluded)",
        td50_gy=39.8, m=0.12, n=0.97, alpha_beta_gy=2.5,
        source="Dawson LA et al., IJROBP 2002;53:810-821; QUANTEC liver (Pan 2010)"),
    "kidney-burman": NTCPParameters(
        model_id="kidney-burman", structure="Kidneys", endpoint="clinical nephritis",
        td50_gy=28.0, m=0.10, n=0.70, alpha_beta_gy=2.5,
        source="Burman C et al., IJROBP 1991;21:123-135"),
    "brain-necrosis-burman": NTCPParameters(
        model_id="brain-necrosis-burman", structure="Brain", endpoint="necrosis / infarction",
        td50_gy=60.0, m=0.15, n=0.25, alpha_beta_gy=2.0,
        source="Burman C et al., IJROBP 1991;21:123-135"),
    "brainstem-burman": NTCPParameters(
        model_id="brainstem-burman", structure="Brainstem", endpoint="necrosis / infarction",
        td50_gy=65.0, m=0.16, n=0.16, alpha_beta_gy=2.0,
        source="Burman C et al., IJROBP 1991;21:123-135"),
    "optic-chiasm-burman": NTCPParameters(
        model_id="optic-chiasm-burman", structure="OpticChiasm", endpoint="blindness",
        td50_gy=65.0, m=0.14, n=0.25, alpha_beta_gy=2.0,
        source="Burman C et al., IJROBP 1991;21:123-135"),
}

TCP_MODELS: Dict[str, TCPParameters] = {
    "nsclc-martel": TCPParameters(
        model_id="nsclc-martel", structure="PTV", endpoint="30-month local control, NSCLC",
        d50_gy=84.5, gamma50=1.5, alpha_beta_gy=10.0,
        source="Martel MK et al., Lung Cancer 1999;24:31-37 (D50 84.5 Gy for 30-month local progression-free survival); γ50 1.5 as in Okunieff P et al., IJROBP 1995;32:1227-1237"),
    "prostate-levegrun": TCPParameters(
        model_id="prostate-levegrun", structure="PTV", endpoint="biochemical control, prostate",
        d50_gy=57.3, gamma50=1.5, alpha_beta_gy=1.5,
        source="Levegrün S et al., IJROBP 2001;51:1064-1080 (stage-pooled D50 and slope, approximately)"),
    "head-neck-okunieff": TCPParameters(
        model_id="head-neck-okunieff", structure="PTV", endpoint="local control, head and neck squamous cell carcinoma",
        d50_gy=51.1, gamma50=1.6, alpha_beta_gy=10.0,
        source="Okunieff P et al., IJROBP 1995;32:1227-1237 (pooled head-and-neck dose-response)"),
}

DEFAULT_ALPHA_BETA: Dict[str, float] = {
    "tumour": 10.0, "late": 3.0, "spinalcord": 2.0, "brain": 2.0, "brainstem": 2.0, "opticchiasm": 2.0, "opticnrv": 2.0,
    "lungs": 3.0, "lung": 3.0, "heart": 3.0, "esophagus": 3.0, "parotid": 3.0, "rectum": 3.0, "bladder": 5.0, "liver": 2.5,
    "kidneys": 2.5, "kidney": 2.5, "ptv": 10.0, "gtv": 10.0, "ctv": 10.0,
}


def default_alpha_beta(structure_name: str) -> float:
    key = "".join(ch for ch in structure_name.lower() if ch.isalnum())
    for name, ab in DEFAULT_ALPHA_BETA.items():
        if key.startswith(name):
            return ab
    return DEFAULT_ALPHA_BETA["late"]


__all__ = ["eqd2", "bed", "geud", "lkb_ntcp", "poisson_tcp", "NTCP_MODELS", "TCP_MODELS", "DEFAULT_ALPHA_BETA", "default_alpha_beta"]
