from __future__ import annotations

from pathlib import Path
import runpy


def main() -> None:
    local_script = Path(__file__).resolve().with_name("unified_bcc_price.py")
    runpy.run_path(str(local_script), run_name="__main__")


if __name__ == "__main__":
    main()
