"""Top-level pytest configuration for the Radiarch test suite.

Prepends the in-tree ``src/`` directory to ``sys.path`` so the tests
always run against the live source tree, regardless of how (or whether)
``radiarch`` has been installed into the active environment.

**Why this exists.** The vendored OpenTPS tree
(``src/opentps/core/processing/doseCalculation/...``) is a deeply nested
namespace; setuptools' modern *strict* editable install snapshots the
package list at install time. If anyone adds a new ``__init__.py`` —
or runs ``pip install -e ./src`` before the full subpackage tree is
in place — the installed ``__editable___radiarch_*_finder.py`` ends
up with stale ``NAMESPACES`` entries that route those submodules
through PEP-420 namespace lookup instead of regular package loading,
which breaks downstream imports like
``opentps.core.processing.doseCalculation.protons.MCsquare``.

Putting ``src/`` on ``sys.path`` first sidesteps the editable-install
finder entirely for test runs. Production (the Docker image) uses a
proper site-packages install and is unaffected.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir():
    src_str = str(_SRC)
    # Prepend so the in-tree source wins over any (possibly stale)
    # editable install in the active venv.
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    elif sys.path.index(src_str) != 0:
        sys.path.remove(src_str)
        sys.path.insert(0, src_str)
