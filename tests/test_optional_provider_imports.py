"""Optional provider SDKs stay out of base batch and provider imports."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_batch_and_non_deepagents_providers_import_without_deepagents_extras() -> None:
    project_root = Path(__file__).resolve().parents[1]
    script = r"""
import builtins

blocked = ("deepagents", "langchain", "langgraph")
original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if any(name == package or name.startswith(package + ".") for package in blocked):
        raise AssertionError(f"optional module import attempted: {name}")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import lightspeed_agentic.batch
from lightspeed_agentic.factory import create_provider

assert create_provider("gemini").name == "gemini"
assert create_provider("openai").name == "openai"
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "src")
    result = subprocess.run(  # noqa: S603 - controlled inline import-isolation test script
        [sys.executable, "-c", script],
        cwd=project_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
