"""Workflow registry: maps workflow IDs to runner functions.

Each runner is a module-level ``run(plan)`` function in its own file.
The planner imports ``RUNNERS`` to dispatch workflows.
"""

from __future__ import annotations

from . import proton_basic, proton_optimized, proton_robust, photon_ccc
from ._helpers import PlannerError

# Workflow ID → runner function mapping
RUNNERS = {
    "proton-impt-basic": proton_basic.run,
    "proton-impt-optimized": proton_optimized.run,
    "proton-robust": proton_robust.run,
    "photon-ccc": photon_ccc.run,
}

__all__ = ["RUNNERS", "PlannerError"]
