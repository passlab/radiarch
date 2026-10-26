"""The radiarch scripting SDK (roadmap R10): the planning services as Python objects, over the REST API.

>>> from radiarch.sdk import Radiarch, ops
>>> rx = Radiarch("http://localhost:8000/api/v1", api_key="...")    # or Radiarch.local()
>>> geo = rx.build_geometry("1.2.3", data_root="/data/case1", spacing_mm=3).derive(ops.expand("PTV", "CTV", 5))
>>> opt = geo.photon_beams([0, 72, 144, 216, 288]).optimize([ops.uniform("PTV", 60), ops.maximum("SpinalCord", 45)])
>>> ev = opt.sequence([ops.uniform("PTV", 60)]).evaluate(60, goals="rtog-0617", target="PTV", fractions=30)

Research use only; not for clinical use.
"""

from . import ops
from .client import Radiarch, RadiarchError
from .objects import Arcs, BeamModel, Dose, Evaluation, Export, Geometry, Optimization, ProtocolRun, Registration, Sequence

__all__ = ["Radiarch", "RadiarchError", "ops", "Geometry", "BeamModel", "Optimization", "Sequence", "Arcs", "Dose",
           "Evaluation", "Export", "Registration", "ProtocolRun"]
