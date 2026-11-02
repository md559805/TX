#!/usr/bin/env python3
"""Download official English, Persian, and orientation packs (~15 MB)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tx.core.language_setup import install_language_packs


def main() -> int:
    try:
        destination = install_language_packs(progress=lambda message, fraction: print(message, flush=True))
        print(f"\nReady: {destination}")
        return 0
    except Exception as exc:
        print(f"\nSetup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
