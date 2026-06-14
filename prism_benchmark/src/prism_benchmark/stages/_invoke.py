"""Shared helper for invoking legacy root-level scripts in-process.

Replaces the historical pattern of running each step via ``subprocess.run``
on a child Python interpreter. By importing the script's module and calling
its ``main()`` function directly we get:

- a real Python traceback when something fails (no ``CalledProcessError``)
- ability to mock / patch internals during tests
- one less process boundary per step (faster and lower memory)

Legacy scripts resolve case JSON via ``legacy_script_config`` (e.g. ``Challenge_Dataset`` / ``SDoH_Dataset``)
that assume ``cwd == legacy_root``; this helper temporarily ``os.chdir``s
into ``legacy_root`` for the duration of the call and restores the previous
cwd afterwards. It also makes sure ``legacy_root`` is on ``sys.path`` so
the module can be imported.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

from prism_benchmark.legacy_registry import (
    get_legacy_module_target,
    get_legacy_script_path,
)


def invoke_legacy_main(legacy_root: Path, script_key: str) -> None:
    """Import the legacy module for ``script_key`` and call its ``main()``.

    Parameters
    ----------
    legacy_root: Path
        Directory containing the legacy root-level scripts. Will be made
        the working directory while ``main()`` runs.
    script_key: str
        Key from ``prism_benchmark.legacy_registry.LEGACY_MODULES``.
    """
    script_path = get_legacy_script_path(legacy_root, script_key)
    if not script_path.exists():
        raise FileNotFoundError(f"[{script_key}] Script not found: {script_path}")

    module_name, func_name = get_legacy_module_target(script_key)

    legacy_root_str = str(legacy_root)
    for sub in ("lib", "config", "stages", ""):
        sub_path = str(legacy_root / sub) if sub else legacy_root_str
        if sub_path not in sys.path:
            sys.path.insert(0, sub_path)

    prev_cwd = os.getcwd()
    os.chdir(legacy_root_str)
    try:
        if module_name in sys.modules:
            mod = importlib.reload(sys.modules[module_name])
        else:
            mod = importlib.import_module(module_name)
        fn = getattr(mod, func_name, None)
        if fn is None or not callable(fn):
            raise AttributeError(
                f"[{script_key}] Module {module_name!r} has no callable {func_name!r}"
            )
        print(f"=== Invoking {module_name}.{func_name}() (legacy_root={legacy_root}) ===")
        fn()
    finally:
        os.chdir(prev_cwd)
