# Bundled OCR models

TX ships these ONNX models so the default Persian/English OCR path works offline. RapidOCR is configured with explicit local paths; it does not download models implicitly.

| File | Purpose | Bytes | SHA-256 |
|---|---|---:|---|
| `ch_PP-OCRv5_det_mobile.onnx` | Text-line detection | 4819576 | `4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae` |
| `arabic_PP-OCRv5_rec_mobile.onnx` | Arabic-script recognition (Persian, English, Arabic-script family) | 8023828 | `c1192e632d0baa9146ae5b756a0e635e3dc63c1733737ebfd1629e87144e9295` |
| `ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx` | Optional text-line orientation classifier (bundled, disabled by default because it can rotate correct Persian/English artwork) | 1018508 | `54379ae5174d026780215fc748a7f31910dee36818e63d49e17dc598ecc82df7` |

Provenance: RapidOCR v3.10.0 model registry, ModelScope release `RapidAI/RapidOCR` tag `v3.10.0`:

```text
https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx
https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/arabic_PP-OCRv5_rec_mobile.onnx
https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/cls/ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx
```

Upstream PaddleOCR models and RapidOCR conversions are Apache-2.0. See `LICENSE-PaddleOCR.txt` and `LICENSE-RapidOCR.txt`.
