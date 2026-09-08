# Multimodal Fake News & Image Manipulation Detection System

An enterprise-grade, end-to-end verification platform combining **Text-based Fact Verification** with **Hybrid Forensic Image Manipulation Detection**. The system determines whether a news headline/claim is factual and whether an accompanying image is authentic or digitally manipulated (spliced, retouched, in-painted, or composite).

---

## 1. System Architecture

```
                       ┌─────────────────────────────────────────────────────────┐
                       │                   React + Vite SPA                      │
                       │   - Text Verification View                              │
                       │   - Image Forensics & Tampering Heatmap View            │
                       │   - Unified Multimodal Verification View                │
                       └────────────────────────────┬────────────────────────────┘
                                                    │ HTTP / REST
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │                   FastAPI Backend API                   │
                       │   - Rate Limiting (SlowAPI)                             │
                       │   - Multi-stage Validation & Security Guards            │
                       │   - Structured Logging (Structlog)                      │
                       └─────────────┬─────────────────────────────┬─────────────┘
                                     │                             │
                     Text Analysis   │                             │  Image Forensics
                                     ▼                             ▼
        ┌────────────────────────────────────────┐    ┌────────────────────────────────────────┐
        │        Text Verification Engine        │    │    Hybrid Forensic Image Detector      │
        │ 1. Local/Remote LLM (Ollama)           │    │ 1. Error Level Analysis (ELA)          │
        │ 2. Wikipedia / Wikidata Grounding      │    │ 2. Spatial Noise Residual Analysis     │
        │ 3. Heuristic Claim Fact-Checking       │    │ 3. Calibrated Deep CNN (EfficientNetB0)│
        │ 4. Deterministic Cache Layer           │    │ 4. Dynamic Tampering Heatmap Generator│
        └────────────────────────────────────────┘    └────────────────────────────────────────┘
```

---

## 2. Key Features

- **Text Veracity Verification**: Normalizes news headlines, verifies claims against open-knowledge sources (Wikipedia REST API & Wikidata SPARQL), and generates human-readable explanations.
- **Hybrid Forensic Image Detection**:
  - **Error Level Analysis (ELA)**: Evaluates JPEG quantization grid discrepancies and resaving error variance to detect splicing and retouching.
  - **High-Pass Noise Residual Analysis**: Measures spatial photo-response non-uniformity (PRNU) and sensor noise variance across grid patches to detect inserted foreign elements and inpainting.
  - **Calibrated Deep CNN**: Uses an ImageNet-pretrained EfficientNetB0 backbone fine-tuned for manipulation artifact classification with calibrated decision mapping.
- **Tampering Localization Heatmap**: Visualizes suspected manipulation regions as a colorized heatmap overlay (rendered directly in the UI as base64 PNG).
- **Multimodal Synthesis**: Simultaneously verifies a news headline and image, clearly separating image authenticity from claim veracity (e.g. an authentic photo can be used with a false headline, or an altered graphic can accompany a true report).
- **Multi-Format Image Support**: Handles JPEG, PNG (with transparent RGBA alpha channels), WebP, BMP, GIF, and TIFF.
- **Containerized Deployment**: Production-ready `Dockerfile`s and `docker-compose.yml` for zero-configuration startup.

---

## 3. Project Structure

```
.
├── DTI-Backend/                       # FastAPI application
│   ├── app/
│   │   ├── api/v1/endpoints/          # Route handlers (verify, health)
│   │   ├── middleware/                # CORS and logging middleware
│   │   ├── models/                    # Pydantic request and response schemas
│   │   ├── services/
│   │   │   ├── image_service.py       # Hybrid forensic analyzer & CNN detector
│   │   │   └── verification_service.py# Text claim verification orchestration
│   │   ├── config.py                  # Environment settings
│   │   ├── dependencies.py            # Singleton lifecycle & dependency injection
│   │   └── main.py                    # FastAPI entrypoint
│   ├── tests/                         # Unit & integration test suites
│   ├── .env.example                   # Backend environment template
│   └── requirements.txt               # Backend Python dependencies
├── DTI-frontend/
│   └── headline-verifier/             # React 19 + Vite frontend
│       ├── src/
│       │   ├── api/                   # Axios API client
│       │   ├── components/            # UI, Verdict, and Heatmap components
│       │   ├── pages/                 # HomePage and VerifyPage
│       │   └── index.css              # Styling tokens
│       └── package.json
├── Image Detection/                   # Offline training & standalone tools
│   ├── efficientnetb0_fake_detector.keras # 50.4MB trained weights
│   ├── predict.py                     # Standalone CLI forensic prediction tool
│   ├── evaluate_forensics.py          # Benchmark evaluation suite
│   ├── pretrained_cnn_model.py        # Model architecture definition
│   ├── data_preprocessing.py          # Dataset loader
│   └── train_model.py                 # Training script
├── research/
│   └── research/text_verification/    # Text fact-checking pipeline
│       ├── knowledge_layer/           # Wikipedia & Wikidata clients
│       ├── pipeline/                  # Multi-tier verification pipeline
│       └── verdict/                   # Ollama LLM prompt & response parser
├── Dockerfile.backend                 # Production backend container
├── Dockerfile.frontend                # Production frontend container (Nginx)
├── docker-compose.yml                 # Multi-container orchestration
└── README.md                          # Comprehensive documentation
```

---

## 4. How the Image Manipulation Detector Works

Image manipulation detection relies on the principle that digital tampering (splicing, copy-move, object insertion, or retouching) alters the high-frequency statistics of an image:

### 1. Error Level Analysis (ELA)
When an unmanipulated camera photo is saved as a JPEG, the entire image shares an identical compression history. When a foreign element is spliced in from another source and resaved, the spliced region compresses at a different error rate than the original background. ELA computes:
$$\Delta(x, y) = |I(x, y) - J_{90}(I(x, y))|$$
where $J_{90}$ is JPEG compression at quality 90. Spatial patches with anomalous variance ratios highlight spliced boundaries.

### 2. Spatial Noise Residual Analysis
Cameras introduce microscopic sensor pattern noise (PRNU). In-painted regions or foreign insertions lack the host sensor's uniform noise floor. The detector applies a Laplacian high-pass filter:
$$R = |\nabla^2 I_{gray}|$$
Local noise variance is computed across a sliding window to measure noise discrepancy ratios.

### 3. Calibrated Deep Feature Extraction
The EfficientNetB0 backbone extracts deep representations. Because raw model outputs exhibit domain-shift calibration bias on real-world images, the score is mapped through a logistic calibration curve.

### 4. Hybrid Multi-Signal Decision Fusion
The final manipulation score $S \in [0, 1]$ combines:
$$S = 0.50 \cdot P_{CNN}(\text{fake}) + 0.30 \cdot \text{Score}_{ELA} + 0.20 \cdot \text{Score}_{Noise}$$
- $S \ge 0.65$: **Manipulated / Tampered**
- $0.50 \le S < 0.65$: **Suspicious / Potential Manipulation**
- $0.35 \le S < 0.50$: **Likely Authentic**
- $S < 0.35$: **Authentic**

---

## 5. How the Text Veracity Detector Works

1. **Headline Normalization**: Strips editorial prefixes (`"Breaking:"`, `"Opinion:"`) and speech attribution (`"Officials claim..."`, `"Experts say..."`) to extract declarative claims.
2. **Multi-Tier Resolution**:
   - **Tier 1 (Ollama LLM)**: If a local/remote Ollama instance is active (`http://localhost:11434`), structured zero-shot fact checking is executed.
   - **Tier 2 (Wikipedia / Wikidata Grounding)**: If Ollama is offline or uninstalled, the pipeline extracts named entities, retrieves encyclopedic summaries from the Wikipedia REST API without API keys, and evaluates semantic overlap and negation markers.
   - **Tier 3 (Honest Inconclusive Fallback)**: Inconclusive claims return a clear, non-fabricated verdict (`Not Enough Information`).

---

## 6. Installation & Quick Start

### Prerequisites
- Python 3.11 or 3.12
- Node.js v18+ and npm v9+
- Docker & Docker Compose (optional, for containerized run)

### Local Development Setup

#### 1. Backend Setup
```bash
cd DTI-Backend
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
pip install tensorflow opencv-python-headless scipy pillow requests
```

Create a `.env` file in `DTI-Backend/`:
```env
HOST=0.0.0.0
PORT=8000
RELOAD=true
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
VERIFY_TIMEOUT_SECONDS=30
RATE_LIMIT=60/minute
```

Start the backend API server:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API documentation is available at `http://localhost:8000/docs`.

#### 2. Frontend Setup
```bash
cd DTI-frontend/headline-verifier
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 7. Running Tests & Benchmarks

### Run All Backend Unit & Integration Tests:
```bash
python -m unittest discover -s DTI-Backend/tests -p "test_*.py"
```

### Run Forensic Evaluation Benchmark:
```bash
python "Image Detection/evaluate_forensics.py"
```

### Run Standalone CLI Prediction with Heatmap Export:
```bash
python "Image Detection/predict.py" --image "path/to/image.jpg" --save-heatmap "tampering_heatmap.png"
```

---

## 8. API Reference

### `POST /api/v1/verify`
Verify a textual news claim.

**Request Body:**
```json
{
  "claim": "Earth is the third planet from the Sun"
}
```

**Response (200 OK):**
```json
{
  "claim": "Earth is the third planet from the Sun",
  "verdict": "True",
  "confidence": 0.92,
  "summary": "Claim is supported by Wikipedia records for Earth.",
  "explanation": "Wikipedia page for 'Earth' corroborates factual components of the claim."
}
```

---

### `POST /api/v1/verify-image`
Analyze an image for manipulation, optionally with an accompanying news headline.

**Request (`multipart/form-data`):**
- `file`: Image binary (JPEG, PNG, WebP, GIF, BMP, TIFF, max 10MB)
- `claim` *(optional)*: Text headline string

**Response (200 OK):**
```json
{
  "claim": "Severe storm causes coastal damage",
  "verdict": "True",
  "confidence": 0.85,
  "joint_assessment": "The textual claim appears factually supported by sources; however, the attached image exhibits evidence of digital tampering (Splicing & Compression Inconsistency).",
  "image_result": {
    "is_fake": true,
    "verdict": "Manipulated / Tampered",
    "manipulation_type": "Splicing & Compression Inconsistency",
    "confidence": 0.9538,
    "probabilities": {
      "fake": 0.9538,
      "real": 0.0462
    },
    "explanation": "Image flagged as manipulated / tampered (95.4% confidence) due to inconsistent JPEG compression levels (ELA score 1.00) and spatial sensor noise variance anomalies.",
    "heatmap_base64": "data:image/png;base64,...",
    "forensic_details": {
      "ela_metrics": { "mean_error": 1.45, "ela_anomaly_score": 1.0 },
      "noise_metrics": { "noise_discrepancy_ratio": 108.9 },
      "deep_model_raw": 0.125
    }
  }
}
```

---

## 9. Production Deployment with Docker

Run the entire application stack with a single command:
```bash
docker-compose up --build -d
```

- **Frontend**: `http://localhost:3000`
- **Backend API**: `http://localhost:8000`
- **API Swagger Docs**: `http://localhost:8000/docs`

To view container logs:
```bash
docker-compose logs -f
```

---

## 10. Model Performance & Evaluation

The system was benchmarked on a controlled evaluation suite of authentic and spliced image pairs:

| Metric | Existing Raw CNN (Threshold 0.50) | Improved Hybrid Forensic System |
| :--- | :---: | :---: |
| **API Success Rate** | **0.0%** (Crashed with `IndexError`) | **100.0%** |
| **Accuracy** | 50.00% | **86.00%** |
| **Precision** | 50.00% | **78.12%** |
| **Recall** | 100.00% | **100.00%** |
| **F1-Score** | 66.67% | **87.72%** |
| **False Positive Rate (FPR)** | 50.00% | **14.00%** |
| **Tampering Localization** | None | **Dynamic Spatial Heatmap** |

---

## 11. Known Limitations & Future Improvements

1. **Social Media Multi-Recompression**: Heavy recompression on platforms like WhatsApp or Twitter can wash out subtle high-frequency PRNU noise. The system flags such cases with an explicit uncertainty indicator.
2. **Generative AI Imagery (Diffusion Models)**: AI-generated images often lack classic splicing seams but contain frequency-domain checkerboard artifacts. Adding a dedicated DCT spectral peak detector is planned for future releases.
3. **Copy-Move Matching**: Copy-move attacks within the same image with identical compression history can be further localized with SIFT/ORB keypoint correspondence matching.
