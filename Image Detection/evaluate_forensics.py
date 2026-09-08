import os
import io
import sys
from pathlib import Path
import tensorflow as tf
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

# Add backend to path
backend_path = Path(__file__).resolve().parent.parent / "DTI-Backend"
if backend_path.exists() and str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.services.image_service import get_image_detector


def generate_synthetic_evaluation_suite(n_pairs=25, seed=42):
    """Generate a controlled test suite of authentic and manipulated images to benchmark forensic detectors.
    
    Creates:
      - Authentic natural photographic gradients with consistent sensor noise and uniform JPEG compression.
      - Spliced images with foreign object insertions, different compression qualities, and boundary seams.
    """
    np.random.seed(seed)
    test_samples = []  # (image_bytes, is_manipulated_label)

    for i in range(n_pairs):
        w, h = 400, 300
        # 1. Generate base authentic image
        freq_x = np.random.uniform(1.0, 4.0)
        freq_y = np.random.uniform(1.0, 4.0)
        x = np.linspace(0, 1, w)
        y = np.linspace(0, 1, h)
        xx, yy = np.meshgrid(x, y)
        base = (0.5 + 0.3 * np.sin(xx * freq_x) + 0.2 * np.cos(yy * freq_y)) * 200
        noise = np.random.normal(0, np.random.uniform(2.0, 5.0), (h, w))
        raw = np.clip(base + noise, 0, 255).astype(np.uint8)
        img_auth = Image.fromarray(raw).convert("RGB")

        # Save authentic at natural JPEG quality
        buf_auth = io.BytesIO()
        q_auth = int(np.random.choice([75, 80, 85, 90, 95]))
        img_auth.save(buf_auth, "JPEG", quality=q_auth)
        test_samples.append((buf_auth.getvalue(), 0))  # 0 = Authentic

        # 2. Generate manipulated image (splicing with different compression & noise profile)
        buf_base = io.BytesIO()
        img_auth.save(buf_base, "JPEG", quality=75)
        buf_base.seek(0)
        img_tampered = Image.open(buf_base).convert("RGB")

        # Foreign patch
        patch_w = np.random.randint(60, 120)
        patch_h = np.random.randint(60, 120)
        pos_x = np.random.randint(20, w - patch_w - 20)
        pos_y = np.random.randint(20, h - patch_h - 20)

        patch_noise = np.random.normal(128, 35, (patch_h, patch_w, 3)).astype(np.uint8)
        patch_img = Image.fromarray(patch_noise)
        img_tampered.paste(patch_img, (pos_x, pos_y))

        # Recompress spliced image at higher quality
        buf_tampered = io.BytesIO()
        img_tampered.save(buf_tampered, "JPEG", quality=90)
        test_samples.append((buf_tampered.getvalue(), 1))  # 1 = Manipulated

    return test_samples


def evaluate_system():
    print("=" * 60)
    print("EVALUATING IMAGE MANIPULATION DETECTION PIPELINE")
    print("=" * 60)
    print("Generating evaluation benchmark suite (50 images: 25 authentic, 25 manipulated)...")
    samples = generate_synthetic_evaluation_suite(n_pairs=25)

    detector = get_image_detector()

    y_true = []
    baseline_cnn_preds = []
    baseline_cnn_scores = []

    improved_preds = []
    improved_scores = []

    for img_bytes, label in samples:
        y_true.append(label)

        # Baseline CNN logic (uncalibrated sigmoid at threshold 0.5)
        # Note: In raw model, class 0 = fake, 1 = real -> raw output is P(real)
        # So fake probability = 1.0 - raw_val
        raw_res = detector.predict(img_bytes)
        forensics = raw_res.get("forensic_details", {})
        raw_val = forensics.get("deep_model_raw")
        if raw_val is None:
            raw_val = 0.5
        
        # Raw baseline: fake if (1.0 - raw_val) >= 0.50
        baseline_fake_score = 1.0 - raw_val
        baseline_cnn_scores.append(baseline_fake_score)
        baseline_cnn_preds.append(1 if baseline_fake_score >= 0.50 else 0)

        # Improved Hybrid System
        imp_score = raw_res["probabilities"]["fake"]
        imp_pred = 1 if raw_res["is_fake"] else 0
        improved_scores.append(imp_score)
        improved_preds.append(imp_pred)

    y_true = np.array(y_true)
    baseline_cnn_preds = np.array(baseline_cnn_preds)
    baseline_cnn_scores = np.array(baseline_cnn_scores)

    improved_preds = np.array(improved_preds)
    improved_scores = np.array(improved_scores)

    # Compute Metrics
    metrics = {
        "Metric": ["Accuracy", "Precision", "Recall", "F1-Score", "ROC-AUC", "False Positive Rate (FPR)"],
        "Existing Model (Raw CNN @ 0.50)": [
            f"{accuracy_score(y_true, baseline_cnn_preds):.4f}",
            f"{precision_score(y_true, baseline_cnn_preds, zero_division=0):.4f}",
            f"{recall_score(y_true, baseline_cnn_preds, zero_division=0):.4f}",
            f"{f1_score(y_true, baseline_cnn_preds, zero_division=0):.4f}",
            f"{roc_auc_score(y_true, baseline_cnn_scores):.4f}",
            f"{np.mean((baseline_cnn_preds == 1) & (y_true == 0)):.4f}",
        ],
        "Improved Hybrid Forensic Model": [
            f"{accuracy_score(y_true, improved_preds):.4f}",
            f"{precision_score(y_true, improved_preds, zero_division=0):.4f}",
            f"{recall_score(y_true, improved_preds, zero_division=0):.4f}",
            f"{f1_score(y_true, improved_preds, zero_division=0):.4f}",
            f"{roc_auc_score(y_true, improved_scores):.4f}",
            f"{np.mean((improved_preds == 1) & (y_true == 0)):.4f}",
        ],
    }

    print("\nBenchmark Results Summary Table:")
    print(f"| {'Metric':<30} | {'Existing Model (Raw CNN)':<25} | {'Improved Hybrid Model':<25} |")
    print(f"|{'-'*32}|{'-'*27}|{'-'*27}|")
    for i in range(len(metrics["Metric"])):
        print(f"| {metrics['Metric'][i]:<30} | {metrics['Existing Model (Raw CNN @ 0.50)'][i]:<25} | {metrics['Improved Hybrid Forensic Model'][i]:<25} |")

    cm = confusion_matrix(y_true, improved_preds)
    print("\nImproved Model Confusion Matrix:")
    print(f"  True Authentic -> Correctly Classified: {cm[0, 0]} | Misclassified as Fake: {cm[0, 1]}")
    print(f"  True Spliced   -> Correctly Classified: {cm[1, 1]} | Misclassified as Real: {cm[1, 0]}")


if __name__ == "__main__":
    evaluate_system()
