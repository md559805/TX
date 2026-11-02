#!/usr/bin/env python3
"""Convenience launcher. Run `python app.py` for the GUI, or `python app.py --help`."""
from tx.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
