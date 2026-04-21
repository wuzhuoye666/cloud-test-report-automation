#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

MIN_VERSION = (3, 10)


def _check_python_version() -> None:
    if sys.version_info < MIN_VERSION:
        joined = ".".join(str(i) for i in MIN_VERSION)
        current = ".".join(str(i) for i in sys.version_info[:3])
        raise SystemExit(f"Python {joined}+ is required, current: {current}")


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def _is_venv_python() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix) or bool(os.environ.get("VIRTUAL_ENV"))


def _venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _resolve_target_python(project_root: Path) -> Path:
    if _is_venv_python():
        return Path(sys.executable)

    venv_dir = project_root / ".venv"
    target_python = _venv_python_path(venv_dir)
    if not target_python.exists():
        print(f"Creating virtual environment at: {venv_dir}")
        _run([sys.executable, "-m", "venv", str(venv_dir)])

    if not target_python.exists():
        raise SystemExit(f"Virtual environment python not found: {target_python}")

    return target_python


def main() -> None:
    _check_python_version()

    project_root = Path(__file__).resolve().parent.parent
    requirements = project_root / "references" / "requirements.txt"
    if not requirements.exists():
        raise SystemExit(f"Missing requirements file: {requirements}")

    target_python = _resolve_target_python(project_root)

    print(f"Bootstrap Python: {sys.executable}")
    print(f"Target Python: {target_python}")
    print(f"Installing dependencies from: {requirements}")

    # pip will skip packages that already satisfy requirements.
    _run([str(target_python), "-m", "pip", "install", "-r", str(requirements)])

    # Minimal runtime verification.
    _run([str(target_python), "-c", "import requests; print(requests.__version__) "])

    print("Dependency check passed.")

    if project_root.joinpath(".venv").exists() and not _is_venv_python():
        if os.name == "nt":
            print("Activate with: .\\.venv\\Scripts\\Activate.ps1")
        else:
            print("Activate with: source .venv/bin/activate")


if __name__ == "__main__":
    main()
