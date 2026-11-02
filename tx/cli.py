from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from tx import APP_NAME, __version__
from tx.core.engine import ExtractionService, managed_tessdata_dir
from tx.core.models import ExtractionOptions, results_to_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tx",
        description="Extract English and Persian text from images and PDFs, locally.",
    )
    parser.add_argument("files", nargs="*", help="Image or PDF files. Omit to open the GUI.")
    parser.add_argument("-o", "--output", help="Write UTF-8 text to this file instead of stdout.")
    parser.add_argument("-l", "--lang", default="eng+fas", help="OCR languages: eng, fas, or eng+fas (default).")
    parser.add_argument("--dpi", type=int, default=300, help="PDF render quality: 200, 300, or 400 (default 300).")
    parser.add_argument("--force-ocr", action="store_true", help="OCR every PDF page and merge with existing text.")
    parser.add_argument("--no-enhance", action="store_true", help="Disable contrast cleanup and the Persian stroke retry.")
    parser.add_argument("--no-orientation", action="store_true", help="Disable automatic rotation detection.")
    parser.add_argument("--no-labels", action="store_true", help="Omit file/page separators in the output.")
    parser.add_argument("--engine", choices=("auto", "rapid", "tesseract"), default="auto", help="OCR engine: auto (default), rapid (bundled layout-aware models), or tesseract.")
    parser.add_argument("--tesseract", help="Path to the Tesseract executable.")
    parser.add_argument("--tessdata", help="Path to a tessdata folder.")
    parser.add_argument("--json", action="store_true", help="Print structured JSON instead of plain text.")
    parser.add_argument("--doctor", action="store_true", help="Check the OCR installation and exit.")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return parser


def options_from_args(args: argparse.Namespace) -> ExtractionOptions:
    languages = tuple(x.strip() for x in args.lang.split("+") if x.strip())
    return ExtractionOptions(
        languages=languages,
        dpi=args.dpi,
        smart_pdf=not args.force_ocr,
        enhance=not args.no_enhance,
        detect_orientation=not args.no_orientation,
        tesseract_path=args.tesseract,
        tessdata_dir=args.tessdata,
        engine=args.engine,
    )


def run_cli(args: argparse.Namespace) -> int:
    options = options_from_args(args)
    service = ExtractionService(options)
    if args.doctor:
        info = service.diagnose()
        info.update(
            python=sys.version.split()[0],
            managed_tessdata=str(managed_tessdata_dir()),
            gui_dependencies=_gui_dependencies(),
        )
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0 if info.get("available") and not info.get("missing") else 1
    if not args.files:
        return launch_gui()

    def password_provider(request) -> None:
        try:
            request.password = getpass.getpass(f"Password for {request.path.name}: ")
        except (EOFError, KeyboardInterrupt):
            request.password = None
        request.ready.set()

    results = []
    try:
        for index, name in enumerate(args.files):
            result = service.extract(
                name,
                progress=lambda p: print(f"{p.message} · {Path(name).name}", file=sys.stderr),
                password_provider=password_provider,
                file_index=index,
                file_count=len(args.files),
            )
            results.append(result)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130

    if args.json:
        payload = [
            {
                "file": str(r.path),
                "ok": r.ok,
                "elapsed_seconds": round(r.elapsed, 3),
                "error": r.error,
                "pages": [
                    {"page": p.number, "method": p.method, "text": p.text, "error": p.error}
                    for p in r.pages
                ],
            }
            for r in results
        ]
        output = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    else:
        output = results_to_text(results, labels=not args.no_labels)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Saved {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output)
    return 0 if all(r.ok for r in results) else 1


def _gui_dependencies() -> dict:
    import importlib.util

    return {name: importlib.util.find_spec(name) is not None for name in ("PySide6", "PIL", "pypdfium2", "pillow_heif")}


def launch_gui() -> int:
    try:
        from tx.gui_entry import main as gui_main
    except ImportError as exc:
        print(
            "The GUI dependencies are missing. Install them with:\n"
            "  python -m pip install -r requirements.txt\n"
            f"Details: {exc}",
            file=sys.stderr,
        )
        return 1
    return gui_main()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.files or args.doctor:
        return run_cli(args)
    return launch_gui()


if __name__ == "__main__":
    raise SystemExit(main())
