# Changelog

## 1.2.4 — 2026-11-01

### Fixed
- Multi-file preview is now switchable: the Preview tab has a file chooser plus previous/next file buttons, and it stays in sync with the Source files list.
- Clicking a file row now selects it even when the click lands on the file name, metadata, icon, or status dot; those labels no longer swallow mouse clicks.
- Page controls are clearly per-file: they reset to page 1 when changing files and are disabled for single-page files or unavailable previews.
- The Text/Preview tab highlight now always matches the visible panel.

### Tests
- Added multi-file preview regression tests and `scripts/smoke_preview.py`.

## 1.2.3 — 2026-11-01

### Fixed
- Fixed a Windows theme-toggle crash: `AttributeError: 'int' object has no attribute 'setAutoFillBackground'`. The preview page number (`preview_page`) and the preview container widget now use separate attributes (`preview_page_widget`), so switching light/dark mode after preview navigation no longer treats an integer as a widget.
- Reduced Windows frameless-dialog `QWindowsWindow::setGeometry` warnings by letting the dialog minimum size follow its wrapped content and sizing the dialog before it is shown.

### Tests
- Added a regression test that changes the preview page number, clears the selection, and toggles the theme twice without crashing.

## 1.2.2 — 2026-11-01

### Fixed
- Removed the remaining black/dark background behind the Source files and Extraction settings cards on Windows dark-mode Qt setups. The app now sets a full light/dark palette and explicitly paints the left scroll area, file list, and preview viewports.
- Removed the native Windows drop shadow around the OCR setup and About dialogs by using opaque, frameless dialogs with a small custom title bar. No translucent-background black halos are introduced.
- Fixed clipped/cut-off status text in OCR setup. The status box now uses stylesheet padding instead of QLabel contents margins, so multi-line engine status is fully visible.
- OCR setup now distinguishes missing bundled RapidOCR model files from missing Python packages, instead of reporting both as “missing models”.

### Tests
- Added regression checks for explicit theme palettes/surfaces, frameless shadow-free dialogs, readable setup status, and RapidOCR model-vs-dependency diagnostics.
- Added `scripts/smoke_dialogs.py` and refreshed GUI/responsive screenshots.

## 1.2.1 — 2026-10-31

### Fixed
- Removed the Qt graphics drop-shadow effect from cards. On some Windows/Qt backends it rendered as opaque black borders/halos around the Source files card, Extraction settings card, and nearby controls. Cards now use the stylesheet border only.
- Replaced invalid CSS `rgba(...)` shadow color strings with valid Qt hex colors, and added a regression check that card shadows do not reintroduce opaque graphics effects.

## 1.2.0 — 2026-10-31

### Added
- Bundled local RapidOCR / ONNX Runtime engine with Arabic-script PP-OCRv5 detection/recognition models for Persian + English artwork, advertisements, and multi-column layouts. No implicit model downloads.
- `Engine` setting and `--engine auto|rapid|tesseract` CLI flag. Auto uses RapidOCR for complex layouts and Tesseract for clean scans when available.
- Conservative numeric-line recovery: Tesseract crops can restore dropped digits without replacing RapidOCR's Persian letters.
- Responsive layout regression script (`scripts/smoke_responsive.py`) and screenshots at 720×520, 900×640, 1180×780, 1440×900.
- Synthetic Persian advertisement regression fixture covering mixed Persian/English, prices, size ranges, and icon-heavy lines.

### Changed
- Window minimum reduced from 1060×720 to 720×520. Narrow windows stack the panels vertically; settings scroll; header/toolbar actions wrap.
- OCR setup and doctor report both RapidOCR and optional Tesseract status.
- Persian normalization now repairs common OCR glue (می/نمی prefixes, plural suffixes, conjunction و), normalizes Arabic-form letters/digits to Persian, and keeps ZWNJ.

### Fixed
- Layout cutoff on smaller windows: fixed-width left panel and nonwrapping toolbars replaced with adaptive/scrollable/wrapping layouts.
- Advertisement-style Persian lines are no longer reduced to Latin gibberish by the default engine; complex layouts use the bundled detector/recognizer instead of Tesseract page segmentation.

### Notes
- The advertisement fixture is representative, not the user's original image. Real-world accuracy still depends on source resolution/contrast.

## 1.1.0 — 2026-10-30

### Changed
- App name is now **TX**.
- Added **Created by Matt** to the app header, About dialog, documentation, and license.
- Persian OCR now reconstructs text from hOCR word boxes instead of relying on Tesseract's plain-text writer, which can glue RTL words together.
- Replaced the all-direction stroke-thickening retry with a spacing-safe vertical-only enhancement.
- Normalized Arabic-form yeh/kaf to Persian ی/ک in Persian OCR output.

### Fixed
- Persian words such as «فارسی است» are no longer emitted as «فارسیاست» in the regression sample.
- Multi-line Persian paragraphs and mixed Persian/English lines keep word spacing and ZWNJ half-spaces.
- Large rendered PDF pages get a bounded downscale recovery pass so Persian lines are less likely to be dropped.

### Tests
- Added regression tests for Persian word spacing, paragraphs, mixed lines, hOCR reconstruction, and Persian letter normalization.

## 1.0.0

- Initial local image/PDF OCR app with English and Persian support, smart PDF text extraction, GUI, CLI, and Persian documentation.
