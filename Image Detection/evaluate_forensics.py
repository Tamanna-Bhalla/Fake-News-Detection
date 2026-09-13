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

    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        roc_auc_score, confusion_matrix, balanced_accuracy_score,
        brier_score_loss, average_precision_score
    )

    y_true = np.array(y_true)
    baseline_cnn_preds = np.array(baseline_cnn_preds)
    baseline_cnn_scores = np.array(baseline_cnn_scores)

    improved_preds = np.array(improved_preds)
    improved_scores = np.array(improved_scores)

    def calculate_ece(y_true, y_prob, n_bins=10):
        """Calculate Expected Calibration Error (ECE)."""
        bin_limits = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        n = len(y_true)
        for i in range(n_bins):
            in_bin = (y_prob >= bin_limits[i]) & (y_prob < bin_limits[i + 1])
            bin_size = np.sum(in_bin)
            if bin_size > 0:
                bin_acc = np.mean(y_true[in_bin])
                bin_conf = np.mean(y_prob[in_bin])
                ece += (bin_size / n) * np.abs(bin_acc - bin_conf)
        return ece

    cm_base = confusion_matrix(y_true, baseline_cnn_preds)
    cm_imp = confusion_matrix(y_true, improved_preds)

    tn_base, fp_base, fn_base, tp_base = cm_base.ravel()
    tn_imp, fp_imp, fn_imp, tp_imp = cm_imp.ravel()

    spec_base = tn_base / (tn_base + fp_base) if (tn_base + fp_base) > 0 else 0.0
    spec_imp = tn_imp / (tn_imp + fp_imp) if (tn_imp + fp_imp) > 0 else 0.0

    fnr_base = fn_base / (fn_base + tp_base) if (fn_base + tp_base) > 0 else 0.0
    fnr_imp = fn_imp / (fn_imp + tp_imp) if (fn_imp + tp_imp) > 0 else 0.0

    brier_base = brier_score_loss(y_true, baseline_cnn_scores)
    brier_imp = brier_score_loss(y_true, improved_scores)

    ece_base = calculate_ece(y_true, baseline_cnn_scores)
    ece_imp = calculate_ece(y_true, improved_scores)

    auprc_base = average_precision_score(y_true, baseline_cnn_scores)
    auprc_imp = average_precision_score(y_true, improved_scores)

    # Compute Comprehensive Metrics Table
    metrics_list = [
        ("Accuracy", f"{accuracy_score(y_true, baseline_cnn_preds):.4f}", f"{accuracy_score(y_true, improved_preds):.4f}"),
        ("Balanced Accuracy", f"{balanced_accuracy_score(y_true, baseline_cnn_preds):.4f}", f"{balanced_accuracy_score(y_true, improved_preds):.4f}"),
        ("Precision", f"{precision_score(y_true, baseline_cnn_preds, zero_division=0):.4f}", f"{precision_score(y_true, improved_preds, zero_division=0):.4f}"),
        ("Recall (Sensitivity)", f"{recall_score(y_true, baseline_cnn_preds, zero_division=0):.4f}", f"{recall_score(y_true, improved_preds, zero_division=0):.4f}"),
        ("Specificity (TNR)", f"{spec_base:.4f}", f"{spec_imp:.4f}"),
        ("F1-Score", f"{f1_score(y_true, baseline_cnn_preds, zero_division=0):.4f}", f"{f1_score(y_true, improved_preds, zero_division=0):.4f}"),
        ("False Positive Rate (FPR)", f"{fp_base / (fp_base + tn_base):.4f}", f"{fp_imp / (fp_imp + tn_imp):.4f}"),
        ("False Negative Rate (FNR)", f"{fnr_base:.4f}", f"{fnr_imp:.4f}"),
        ("AUROC", f"{roc_auc_score(y_true, baseline_cnn_scores):.4f}", f"{roc_auc_score(y_true, improved_scores):.4f}"),
        ("AUPRC", f"{auprc_base:.4f}", f"{auprc_imp:.4f}"),
        ("Brier Calibration Score", f"{brier_base:.4f}", f"{brier_imp:.4f}"),
        ("Expected Calibration Error", f"{ece_base:.4f}", f"{ece_imp:.4f}"),
    ]

    print("\nBenchmark Results Summary Table:")
    print(f"| {'Metric':<30} | {'Existing Model (Raw CNN)':<25} | {'Improved Hybrid Model':<25} |")
    print(f"|{'-'*32}|{'-'*27}|{'-'*27}|")
    for name, base_val, imp_val in metrics_list:
        print(f"| {name:<30} | {base_val:<25} | {imp_val:<25} |")

    print("\nImproved Model Confusion Matrix:")
    print(f"  True Authentic -> Correctly Classified: {cm_imp[0, 0]} | Misclassified as Fake: {cm_imp[0, 1]}")
    print(f"  True Spliced   -> Correctly Classified: {cm_imp[1, 1]} | Misclassified as Real: {cm_imp[1, 0]}")


if __name__ == "__main__":
    evaluate_system()

