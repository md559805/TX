# PyInstaller spec for TX. Build with: pyinstaller tx.spec
# RapidOCR/ONNX models are bundled; Tesseract is optional unless you bundle it yourself.
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

block_cipher = None
binaries = (
    collect_dynamic_libs("pypdfium2")
    + collect_dynamic_libs("pillow_heif")
    + collect_dynamic_libs("onnxruntime")
)
datas = [
    ("tx/assets", "tx/assets"),
    ("tx/docs", "tx/docs"),
    ("tx/core/language_packs.json", "tx/core"),
]
datas += collect_data_files("rapidocr", include_py_files=False)
datas += collect_data_files("onnxruntime", include_py_files=False)

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=["pypdfium2", "pypdfium2.raw", "pillow_heif", "rapidocr", "onnxruntime", "bidi"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TX",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="tx/assets/icon.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="TX",
)
