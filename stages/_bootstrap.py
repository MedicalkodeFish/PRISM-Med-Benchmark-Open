# -*- coding: utf-8 -*-
"""Path bootstrap for benchmark_stages entry scripts."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import prism_bootstrap

prism_bootstrap.install_import_paths(_ROOT)
