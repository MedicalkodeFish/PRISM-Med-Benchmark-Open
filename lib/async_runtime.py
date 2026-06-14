# -*- coding: utf-8 -*-
"""Windows asyncio event-loop policies used by legacy benchmark scripts."""
from __future__ import annotations

import asyncio
import sys


def apply_windows_selector_event_loop_policy() -> None:
    """Classification pipelines (aiohttp via chat2llm): Selector on Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def apply_windows_proactor_event_loop_policy() -> None:
    """Reasoning flaw judges: Proactor on Windows (legacy default for those scripts)."""
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
