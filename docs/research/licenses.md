# Licence matrix for Proseway (Apache-2.0)

Checked 2026-11-21. Versions are the latest on PyPI or npm that day. Licence sources are the GitHub repo licence (GitHub API), PyPI/npm metadata and the linked LICENSE files. This is not legal advice.

**Compatible?** means the package can be a dependency of, or bundled with, an Apache-2.0 project without imposing extra terms on Proseway or its users.

## Do NOT bundle / depend on

| Item | Why |
|---|---|
| **EbookLib** 0.21 | **AGPL-3.0-or-later**, confirmed ([GitHub](https://github.com/aerkalov/ebooklib), [PyPI](https://pypi.org/project/EbookLib/)). Write EPUB directly instead: it is a zip of XHTML, OPF and NAV files, which `zipfile` plus string templates or lxml can produce. |
| **PyMuPDF / pymupdf4llm / pymupdf-layout** 2.1 | **AGPL-3.0 or Artifex commercial** ([GitHub](https://github.com/pymupdf/PyMuPDF), [PyPI](https://pypi.org/project/PyMuPDF/)). |
| **marker-pdf / surya-ocr / indra-ocr weights** | Code is Apache-2.0, but marker-pdf hard-depends on indra-ocr and surya, whose **weights** use a modified OpenRAIL-M. That licence bans use by entities above $5M (Surya 2.5) or $20M (Indra) in revenue or funding, **and bans anyone offering a product that "competes with" Datalab's** ([Surya LICENSE](https://huggingface.co/datalab-to/surya-ocr-2.5/raw/main/LICENSE), [Indra LICENSE](https://huggingface.co/datalab-to/indra-ocr/raw/main/LICENSE)). Proseway users could not rely on it. |
| **MinerU** 4.2.3 | "MinerU Open Source License": Apache-2.0 **plus** MAU and revenue thresholds, an attribution duty and automatic termination ([LICENSE.md](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md)). Not OSI, so it cannot pass through as plain Apache. The MinerU2.5-2509 VLM weights are **AGPL-3.0** ([HF](https://huggingface.co/opendatalab/MinerU2.5-2509-1.2B)). |
| **Nougat base weights** | **CC-BY-NC-4.0**, non-commercial ([HF](https://huggingface.co/facebook/nougat-base)). |
| **Ghostscript** (needed by OCRmyPDF) | **AGPL or commercial** ([ghostscript.com/licensing](https://ghostscript.com/licensing)). Never bundle. Only use it if the user installed it. |
| **Unstructured hi_res YOLOX weights** | The model card states no licence ([HF](https://huggingface.co/unstructuredio/yolo_x_layout)). Avoid until clarified. |

## Extraction and OCR libraries

| Dependency | Version checked | Licence | Compatible? | Notes / source |
|---|---|---|---|---|
| pypdfium2 | 5.15.2 | Apache-2.0 / BSD-3-Clause. PDFium is BSD-style. | Yes | The wheel bundles PDFium, and its dependency licences must be shipped with it (already in the wheel). [README](https://github.com/pypdfium2-team/pypdfium2#licensing) |
| pypdf | 7.1.1 | BSD-3-Clause | Yes | [PyPI](https://pypi.org/project/pypdf/) |
| pdfminer.six | 20260107 | MIT | Yes | [GitHub](https://github.com/pdfminer/pdfminer.six) |
| pdfplumber | 0.11.11 | MIT | Yes | [PyPI](https://pypi.org/project/pdfplumber/) |
| pdftext | 0.7.1 | Apache-2.0 | Yes | No model weights. [PyPI](https://pypi.org/project/pdftext/) |
| PyMuPDF / pymupdf4llm | 2.1 / 2.1 | AGPL-3.0 / commercial | **No** | see above |
| docling (docling-slim), docling-core, docling-parse, docling-ibm-models | 2.151.1 / 2.108.0 / 7.27.0 / 4.0.4 | MIT | Yes | [GitHub](https://github.com/docling-project/docling) |
| Docling Heron layout weights | HF, 2026-02 | Apache-2.0 | Yes | [HF](https://huggingface.co/docling-project/docling-layout-heron) |
| Docling TableFormer weights (docling-models) | HF, 2025-12 | CDLA-Permissive-2.0 / Apache-2.0 | Yes | CDLA-P-2.0 asks only that its text accompany redistributed data. [HF](https://huggingface.co/docling-project/docling-models) |
| CodeFormulaV2 weights | HF | CDLA-Permissive-2.0 | Yes | [HF](https://huggingface.co/docling-project/CodeFormulaV2) |
| torch (Docling dependency) | 2.15.0 | Apache-2.0 AND BSD-2/BSD-3 AND MIT AND others, all permissive (PyPI licence expression) | Yes | [PyPI](https://pypi.org/project/torch/) |
| onnxruntime | 1.32.0 | MIT | Yes | [PyPI](https://pypi.org/project/onnxruntime/) |
| marker-pdf / surya-ocr / indra-ocr | 2.2.0 / 0.24.0 / 1.1.2 | Code Apache-2.0. Weights modified OpenRAIL-M. | **No (weights)** | see above |
| mineru | 4.2.3 | Apache-2.0 + extra terms | **No** | see above |
| unstructured | 0.27.37 | Apache-2.0 | Code yes, hi_res weights unclear | [GitHub](https://github.com/Unstructured-IO/unstructured) |
| GROBID | 0.9.1 | Apache-2.0 | Yes | Java service. [GitHub](https://github.com/grobidOrg/grobid) |
| nougat-ocr | 0.1.17 | Code MIT. Weights CC-BY-NC-4.0 (base) / CC-BY-4.0 (small). | **No** (base) | [HF base](https://huggingface.co/facebook/nougat-base) |
| olmocr | 0.4.27 | Apache-2.0 (code and weights) | Yes | GPU only. [HF](https://huggingface.co/allenai/olmOCR-2-7B-1025) |
| rapidocr | 3.10.0 | Apache-2.0. Models from PaddleOCR are Apache-2.0. | Yes | Keep `MODEL_LICENSES.md` attribution. [README](https://github.com/RapidAI/RapidOCR#license) |
| Tesseract + tessdata | 5.5.4 | Apache-2.0 | Yes | System binary. [GitHub](https://github.com/tesseract-ocr/tesseract), [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) |
| pytesseract / tesserocr | 0.3.13 / 2.13.0 | Apache-2.0 / MIT | Yes | [PyPI](https://pypi.org/project/pytesseract/), [PyPI](https://pypi.org/project/tesserocr/) |
| OCRmyPDF | 17.14.2 | MPL-2.0 | Yes as an optional call. **Ghostscript dependency is AGPL.** | [README](https://github.com/ocrmypdf/OCRmyPDF#license) |
| paddleocr / paddlepaddle | 3.7.0 / 3.3.1 | Apache-2.0 | Yes | [GitHub](https://github.com/PaddlePaddle/PaddleOCR) |
| easyocr | 1.7.2 | Apache-2.0 | Yes | [GitHub](https://github.com/JaidedAI/EasyOCR) |
| python-doctr | 1.1.0 | Apache-2.0 (code and weights) | Yes | [GitHub](https://github.com/mindee/doctr) |
| EbookLib | 0.21 | AGPL-3.0-or-later | **No** | see above |

## Backend

| Dependency | Version checked | Licence | Compatible? | Source |
|---|---|---|---|---|
| FastAPI | 0.165.0 | MIT | Yes | [GitHub](https://github.com/fastapi/fastapi) |
| Starlette | 1.10.0 | BSD-3-Clause | Yes | [GitHub](https://github.com/Kludex/starlette) |
| uvicorn | 0.54.0 | BSD-3-Clause | Yes | [GitHub](https://github.com/Kludex/uvicorn) |
| pydantic / pydantic-core | 2.14.4 / 2.50.5 | MIT | Yes | [GitHub](https://github.com/pydantic/pydantic) |
| python-multipart | 0.0.34 | Apache-2.0 | Yes | [GitHub](https://github.com/Kludex/python-multipart) |
| psutil | 7.2.2 | BSD-3-Clause | Yes | [GitHub](https://github.com/giampaolo/psutil) |
| rapidfuzz | 3.14.6 | MIT | Yes | [GitHub](https://github.com/rapidfuzz/RapidFuzz) |
| segno | 1.6.6 | BSD-3-Clause | Yes | [GitHub](https://github.com/heuer/segno) |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Yes | Direct dependency (`>=42`) since HTTPS phone sharing: makes the local CA and the server certificate (`src/proseway/certs.py`). Already required by pdfminer.six, so it adds nothing to the install. Wheels embed OpenSSL 3 (Apache-2.0). [PyPI](https://pypi.org/project/cryptography/), [LICENSE](https://github.com/pyca/cryptography/blob/main/LICENSE) |
| hatchling | 1.33.0 | MIT | Yes (build-time only, not shipped) | [GitHub](https://github.com/pypa/hatch) |

## Frontend

| Dependency | Version checked | Licence | Compatible? | Notes / source |
|---|---|---|---|---|
| react / react-dom | 19.3.1 | MIT | Yes | [npm](https://www.npmjs.com/package/react) |
| vite | 8.3.8 | MIT | Yes | Build-time only. [GitHub](https://github.com/vitejs/vite) |
| typescript | 5.9.3 | Apache-2.0 | Yes | Build-time only. [GitHub](https://github.com/microsoft/TypeScript) |
| @tanstack/react-virtual | (not used) | MIT | n/a | Considered for virtualised rendering; Proseway uses CSS `content-visibility` and chapter-by-chapter loading instead. |
| alternatives: react-virtuoso / react-window | 4.18.24 / 2.5.3 | MIT / MIT | Yes | [npm](https://www.npmjs.com/package/react-virtuoso), [npm](https://www.npmjs.com/package/react-window) |
| vitest | 5.1.1 | MIT | Yes | Dev only. [GitHub](https://github.com/vitest-dev/vitest) |
| @playwright/test | 1.65.1 | Apache-2.0 | Yes | Dev only. Browser binaries are downloaded at test time and are not redistributed. [GitHub](https://github.com/microsoft/playwright) |

## Fonts (self-hosted in the npm build / Python wheel)

All six are **SIL OFL-1.1**. Fontsource npm packages carry the same licence (`@fontsource/*` 5.3.x, license field `OFL-1.1`). The OFL allows bundling with any software, open source or commercial, as long as the fonts are not sold on their own (OFL FAQ 1.4, 1.22). It also explicitly endorses self-hosted `@font-face` (FAQ 2.1). Bundled copies must include the **copyright statement, licence notice and licence text** (FAQ 1.20) ([OFL FAQ](https://openfontlicense.org/ofl-faq/)). OFL fonts do not change Proseway's Apache-2.0 licence (FAQ 1.3).

| Font | Licence | Reserved Font Name | Redistribution in wheel/npm? | Source |
|---|---|---|---|---|
| Literata | OFL-1.1 | none | Yes | [LICENSE](https://github.com/googlefonts/literata) |
| Source Serif 4 | OFL-1.1 | **"Source"** (Adobe) | Yes, unmodified | [LICENSE](https://github.com/adobe-fonts/source-serif) |
| Atkinson Hyperlegible Next | OFL-1.1 | none | Yes | [LICENSE](https://github.com/googlefonts/atkinson-hyperlegible-next). Checked the **Next** family only, not the original Atkinson Hyperlegible. |
| Inter | OFL-1.1 | none | Yes | [LICENSE](https://github.com/rsms/inter) |
| OpenDyslexic | OFL-1.1 | **"OpenDyslexic"** | Yes, unmodified | [LICENSE](https://github.com/antijingoist/opendyslexic) |
| Lexend | OFL-1.1 | "RevReading Lexend" (not "Lexend") | Yes | [LICENSE](https://github.com/googlefonts/lexend) |

**Reserved Font Name caveat:** under the OFL FAQ, a format conversion counts as modification unless only WOFF compression is added (FAQ 2.2, 2.2.1). Subsetting is always modification (FAQ 2.6), and a modified font may not keep a Reserved Font Name. For **Source Serif 4** and **OpenDyslexic**, ship the upstream or Fontsource-built files as they are and do not subset them in our build. If we must subset, rename the family (for example "Proseway Serif"). Literata, Inter and Atkinson Hyperlegible Next have no RFN, so they can be subset freely as long as the OFL notice is kept.

## Housekeeping

- Ship a `THIRD_PARTY_NOTICES` file (Python wheel and npm bundle) listing each bundled package plus the OFL texts. Include the RapidOCR/PaddleOCR and Docling model attributions when those extras download weights.
- Model weights are downloaded at runtime, not bundled. Record each model's licence URL in the app's "About / licences" screen.

### What Proseway actually ships (checked 2026-11-21)

- **Fonts:** Proseway ships the Fontsource-built WOFF2/WOFF files unchanged. Fontsource splits each family into Unicode-range files; we don't subset or modify them ourselves. Whether Fontsource's range-splitting counts as "modification" under OFL FAQ 2.6 is unsettled. The files keep their original names and metadata, and Fontsource distributes Source Serif 4 and OpenDyslexic this way publicly. If this matters to a downstream distributor, swap in the upstream release files for those two families.
- **Licence texts:** every bundled package and font has its full licence text in `THIRD_PARTY_NOTICES.txt`. `web/scripts/notices.mjs` generates it at build time, and it's served with the app at `/THIRD_PARTY_NOTICES.txt`.
- **Dev-only tools:** `@axe-core/playwright` (MPL-2.0) is used only in tests. It is never bundled.
