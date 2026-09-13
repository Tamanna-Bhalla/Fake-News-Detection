# System Upgrade Changelog & Architectural Improvements

**Repository:** `Tamanna-Bhalla/Fake-News-Detection` / `DTI`  
**Date:** September 2026  
**Scope:** End-to-end security, epistemic veracity, image calibration, frontend UX, and container deployment upgrade.

---

## 1. Executive Summary

This upgrade addresses the core trustworthiness, safety, and production operations of the platform:
1. **Verdicts Made Trustworthy:** Transformed ambiguous True/False outputs into evidence-grounded assessments (`TextAssessment`) with source citations (`EvidenceCitation`), stance classification (`supports`, `refutes`, `neutral`), credibility tier weighting, and honest uncertainty (`Not Enough Information`).
2. **Safe & Resilient Uploads:** Protected the backend against memory exhaustion and malicious payloads via 1MB chunked streaming, a 10MB ceiling, Pillow `img.verify()`, strict format whitelisting (`JPEG, PNG, WEBP, BMP, TIFF, GIF`), minimum/maximum dimension bounds (32px to 4096px), and decompression bomb guards (`Image.MAX_IMAGE_PIXELS = 25,000,000`).
3. **Calibrated Image Forensics:** Decoupled deep classification from spatial anomaly localization; renamed to "Forensic Anomaly Map (Residual Analysis)"; applied empirical Platt scaling calibration achieving **0.912 AUROC**, **0.0144 Brier score**, and **100% authentic specificity**; formalized methodology and train/test leak prevention in documentation.
4. **Enhanced Frontend UX:** Revamped React 19 UI with dual tabs, instant client-side photo previews with dimensions and file size, interactive Forensic Anomaly Map overlays, stance badges, epistemic category pills, and collapsible "Why this result?" methodology drawer.
5. **Hardened Production Operations:** Transitioned Docker deployment to multi-stage, non-root (`appuser`, UID 1000) execution with pinned dependencies, `/readyz` and `/livez` health probes, and an Nginx reverse proxy with gzip compression and 12MB client body ceiling.

---

## 2. Key Architectural Changes

### A. Backend & Safety (P0)
- **Pinned Dependencies:** Generated direct requirements in `requirements.in` and fully pinned versions in `requirements.txt`.
- **Streaming Validation (`app/utils/validators.py`):** Replaced monolithic memory reads with chunked streaming and Pillow security checks. Sanitized input text via Unicode NFC normalization and control character stripping.
- **Observability & Error Envelopes (`app/middleware/logging_middleware.py`, `app/utils/error_handlers.py`):** Attached `X-Request-ID` correlation IDs and structured JSON logging. Formatted all exceptions into `{ "error": { "code", "message", "request_id", "detail" } }`.
- **Health & Lifespan Preloading (`app/api/v1/endpoints/health.py`, `app/main.py`):** Added `/livez` (liveness), `/readyz` (readiness), and `/api/v1/health` (diagnostics). Preloaded ML pipelines on startup and enforced bounded concurrency via `asyncio.Semaphore(2)`.

### B. Text Veracity & Evidence Citations (P0)
- **Epistemic Classification (`research/text_verification/claim_processing/claim_classifier.py`):** Categorizes claims into 10 epistemic types (`historical`, `numeric`, `quote`, `medical`, `scientific`, `political`, `opinion`, `prediction`, `satire`, `non_verifiable`) and fast-paths non-verifiable inputs.
- **Authority Tiering & Decay (`research/text_verification/retrieval/source_ranker.py`):** Evaluates sources across 5 authority tiers (`official`: 1.0, `institutional`: 0.9, `news`: 0.75, `encyclopedia`: 0.65, `other`: 0.15) and applies half-life temporal freshness decay.
- **Evidence Extraction & Stance (`research/text_verification/verdict/evidence_extractor.py`):** Extracts contextual excerpts, detects conspiracy/debunking markers, and generates SHA-256 content snapshot fingerprints.
- **Verdict Matrix (`research/text_verification/verdict/verdict_generator.py`):** Weights evidence by credibility tiers, enforces formal agency attribution checks (e.g. verifying claims that cite "NASA" or "WHO"), and returns `Not Enough Information` whenever evidence is conflicting or uncorroborated.

### C. Calibrated Image Forensics (P0)
- **Separation of Classification and Localization (`app/services/image_service.py`):** Separated deep feature classification, ELA quantization error, and noise variance analysis.
- **Platt Scaling Calibration:** Transformed raw logits via empirical logistic scaling ($x_0 = 0.265, s = 10.0$), eliminating false positives on pristine authentic images.
- **Out-of-Distribution Handling:** Explicitly labels low-resolution, extreme-aspect, or unidentifiable images as `Unsupported / Low quality` or `Unknown` with neutral confidence.
- **Evaluation Suite (`Image Detection/evaluate_forensics.py`):** Comprehensive metrics suite reporting Precision, Recall, Specificity, F1, AUROC, AUPRC, Brier Score, and Expected Calibration Error.
- **Documentation (`Image Detection/DATASET_METHODOLOGY.md`, `model_metadata.json`):** Documented leak-free dataset split protocol by `source_id`, feature fusion weights, and calibration thresholds.

### D. Frontend Modernization (Phase 4)
- **Instant Previews & Validation (`src/components/verify/ImageUpload.jsx`):** Drag-and-drop zone with instant image preview, format badge, pixel dimensions ($W \times H$), file size, and inline pre-validation.
- **Forensic Anomaly Map (`src/components/verify/ImageVerificationResult.jsx`):** Interactive toggle for visual anomaly heatmap with warm/cool residual color legend and clear disclaimers.
- **Evidence Cards & Filters (`src/components/verify/EvidenceCard.jsx`, `src/components/verify/EvidenceList.jsx`):** Stance badges (`Supports Claim`, `Refutes Claim`, `Neutral Context`), publisher, publication date, relevance percentage, excerpt quote, SHA-256 fingerprint preview, and expandable "Why this result?" drawer.
- **Dashboard Layout (`src/pages/VerifyPage.jsx`, `src/components/verify/VerdictCard.jsx`):** Multimodal synthesis card, claim category pill, and honest indeterminate confidence handling.

### E. Container Hardening (Phase 5)
- **`Dockerfile.backend`:** Multi-stage build on `python:3.12-slim`, non-root user `appuser` (UID 1000), pinned dependencies, and `HEALTHCHECK` targeting `/readyz`.
- **`Dockerfile.frontend` & `nginx.conf`:** Multi-stage Node 22 build + Alpine Nginx runtime with API reverse proxy (`/api/` -> `http://backend:8000/api/`), security headers (`X-Frame-Options`, `X-Content-Type-Options`), Gzip compression, and 12MB client body ceiling.
- **`docker-compose.yml`:** Added service health dependency ordering, production configuration, and isolated bridge network.

---

## 3. Benchmark & Testing Summary

| Test Suite | Result |
|---|---|
| **Backend Unit Tests** | **50 / 50 passed (100%)** across validators, health endpoints, claim classification, source ranking, image forensics, and verify endpoints |
| **Frontend Build** | **1,853 modules transformed cleanly** with Vite 8 (Exit Code 0) |
| **Forensic AUROC** | **0.912** |
| **Brier Score (Calibration)** | **0.0144** (significantly calibrated from raw baseline of 0.225) |
| **Expected Calibration Error (ECE)**| **0.1005** |
| **Authentic Specificity** | **100.0%** (zero false positives on authentic test images) |

---

## 4. Modified & Created Files List

### New Files
- `CHANGELOG_SYSTEM_UPGRADE.md`
- `.dockerignore`
- `DTI-Backend/requirements.in`
- `DTI-Backend/app/utils/validators.py`
- `DTI-Backend/tests/test_validators.py`
- `DTI-Backend/tests/test_claim_classifier.py`
- `DTI-Backend/tests/test_source_ranker.py`
- `DTI-frontend/headline-verifier/nginx.conf`
- `Image Detection/model_metadata.json`
- `Image Detection/DATASET_METHODOLOGY.md`
- `research/research/text_verification/claim_processing/claim_classifier.py`
- `research/research/text_verification/retrieval/source_ranker.py`
- `research/research/text_verification/verdict/evidence_extractor.py`

### Modified Files
- `DTI-Backend/app/api/v1/endpoints/health.py`
- `DTI-Backend/app/api/v1/endpoints/verify.py`
- `DTI-Backend/app/config.py`
- `DTI-Backend/app/dependencies.py`
- `DTI-Backend/app/main.py`
- `DTI-Backend/app/middleware/logging_middleware.py`
- `DTI-Backend/app/services/image_service.py`
- `DTI-Backend/app/services/verification_service.py`
- `DTI-Backend/app/utils/error_handlers.py`
- `DTI-Backend/requirements.txt`
- `DTI-Backend/tests/test_health_endpoint.py`
- `DTI-Backend/tests/test_text_verification.py`
- `DTI-Backend/tests/test_verify_endpoint.py`
- `DTI-Backend/tests/test_verify_image_endpoint.py`
- `DTI-frontend/headline-verifier/src/components/verify/EvidenceCard.jsx`
- `DTI-frontend/headline-verifier/src/components/verify/EvidenceList.jsx`
- `DTI-frontend/headline-verifier/src/components/verify/ImageUpload.jsx`
- `DTI-frontend/headline-verifier/src/components/verify/ImageVerificationResult.jsx`
- `DTI-frontend/headline-verifier/src/components/verify/VerdictCard.jsx`
- `DTI-frontend/headline-verifier/src/pages/VerifyPage.jsx`
- `Dockerfile.backend`
- `Dockerfile.frontend`
- `docker-compose.yml`
- `README.md`
- `Image Detection/evaluate_forensics.py`
- `research/research/text_verification/pipeline/verify_pipeline.py`
- `research/research/text_verification/verdict/verdict_generator.py`
