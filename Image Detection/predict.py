import argparse
import os
import sys
from pathlib import Path

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import cv2
import numpy as np
import tensorflow as tf
from PIL import Image, ImageChops

# Add parent directory to path so we can import from DTI-Backend if available
backend_path = Path(__file__).resolve().parent.parent / "DTI-Backend"
if backend_path.exists() and str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from data_preprocessing import CLASS_NAMES, IMG_SIZE, VALID_EXTENSIONS, get_preprocess_fn
from model_loading import load_keras_model


def parse_args():
    parser = argparse.ArgumentParser(
        description="Predict whether an image is authentic or manipulated using hybrid forensic analysis & deep learning."
    )
    parser.add_argument(
        "--image",
        required=True,
        help="Path to the image to analyze.",
    )
    parser.add_argument(
        "--model",
        default="efficientnetb0",
        choices=["mobilenetv2", "resnet50", "efficientnetb0"],
        help="Backbone used when training the saved model.",
    )
    parser.add_argument(
        "--model-path",
        help="Path to the saved .keras model. Defaults to <model>_fake_detector.keras.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.50,
        help="Decision threshold for manipulation detection (default 0.50).",
    )
    parser.add_argument(
        "--save-heatmap",
        help="Optional path to save the generated tampering heatmap overlay PNG.",
    )
    return parser.parse_args()


def validate_image_path(image_path):
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {path}")

    if path.suffix.lower() not in VALID_EXTENSIONS:
        raise ValueError(
            f"Unsupported image extension '{path.suffix}'. "
            f"Use one of: {', '.join(sorted(VALID_EXTENSIONS))}."
        )

    return path


def compute_forensics(image_path: Path):
    """Compute ELA and noise residual metrics from image file."""
    img = Image.open(image_path).convert("RGB")
    
    # 1. ELA
    import io
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    buf.seek(0)
    comp = Image.open(buf)
    diff = ImageChops.difference(img, comp)
    diff_arr = np.array(diff, dtype=np.float32)
    ela_gray = np.mean(diff_arr, axis=2)

    mean_err = float(np.mean(ela_gray))
    std_err = float(np.std(ela_gray))
    p95_err = float(np.percentile(ela_gray, 95))
    ela_score = float(np.clip((std_err / 20.0), 0.0, 1.0))

    # 2. Noise residual
    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY).astype(np.float32)
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    abs_lap = np.abs(lap)
    local_noise = cv2.blur(abs_lap, (16, 16))

    h, w = gray.shape
    block = max(16, min(h, w) // 16)
    block_vars = []
    for y in range(0, h - block + 1, block):
        for x in range(0, w - block + 1, block):
            b = abs_lap[y : y + block, x : x + block]
            block_vars.append(np.var(b))

    block_vars = np.array(block_vars, dtype=np.float32)
    med_var = float(np.median(block_vars)) if len(block_vars) > 0 else 1.0
    max_var = float(np.max(block_vars)) if len(block_vars) > 0 else 1.0
    noise_ratio = float(max_var / (med_var + 1e-4))
    if noise_ratio <= 25.0:
        noise_score = float(np.clip((noise_ratio - 1.0) / 200.0, 0.0, 0.12))
    else:
        noise_score = float(np.clip(0.12 + 0.88 * ((noise_ratio - 25.0) / 80.0), 0.12, 1.0))

    # 3. Heatmap
    ela_norm = (ela_gray - np.min(ela_gray)) / (np.ptp(ela_gray) + 1e-5)
    noise_norm = (local_noise - np.min(local_noise)) / (np.ptp(local_noise) + 1e-5)
    combined = (0.6 * ela_norm) + (0.4 * noise_norm)
    smoothed = cv2.GaussianBlur(combined, (15, 15), 0)
    heat_uint8 = np.clip(smoothed * 255.0, 0, 255).astype(np.uint8)
    colored_heatmap = cv2.applyColorMap(heat_uint8, cv2.COLORMAP_JET)

    return {
        "ela_score": ela_score,
        "mean_ela_error": mean_err,
        "p95_ela_error": p95_err,
        "noise_score": noise_score,
        "noise_discrepancy_ratio": noise_ratio,
        "heatmap": colored_heatmap,
    }


def load_and_prepare_image(image_path, model_name):
    image = tf.keras.utils.load_img(image_path, target_size=(IMG_SIZE, IMG_SIZE))
    image_array = tf.keras.utils.img_to_array(image)
    image_array = tf.expand_dims(image_array, axis=0)
    preprocess_fn = get_preprocess_fn(model_name)
    return preprocess_fn(image_array)


def main():
    args = parse_args()
    image_path = validate_image_path(args.image)

    model_path = Path(args.model_path or f"{args.model}_fake_detector.keras")
    if not model_path.is_file():
        # Check current dir or parent Image Detection dir
        candidate = Path(__file__).resolve().parent / f"{args.model}_fake_detector.keras"
        if candidate.is_file():
            model_path = candidate
        else:
            raise FileNotFoundError(
                f"Saved model not found: {model_path}. Train the model first or pass --model-path."
            )

    model = load_keras_model(model_path)
    image_batch = load_and_prepare_image(str(image_path), args.model)

    # Raw model output: class 0 = fake, class 1 = real -> raw output is P(real)
    raw_real = float(model.predict(image_batch, verbose=0)[0][0])
    
    # Calibrated deep model score
    calibrated_real = float(1.0 / (1.0 + np.exp(-10.0 * (raw_real - 0.265))))
    model_fake_prob = 1.0 - calibrated_real

    # Forensic analysis
    forensics = compute_forensics(image_path)
    ela_score = forensics["ela_score"]
    noise_score = forensics["noise_score"]

    # Hybrid multi-signal fusion
    weighted_fake = float((0.40 * model_fake_prob) + (0.35 * ela_score) + (0.25 * noise_score))
    max_forensic_anomaly = max(ela_score, noise_score)
    if max_forensic_anomaly >= 0.70:
        combined_fake = float(max(weighted_fake, 0.65 + 0.30 * ((max_forensic_anomaly - 0.70) / 0.30)))
    else:
        combined_fake = weighted_fake

    combined_fake = float(np.clip(combined_fake, 0.01, 0.99))
    combined_real = 1.0 - combined_fake

    is_fake = combined_fake >= args.threshold
    prediction_label = "MANIPULATED" if is_fake else "AUTHENTIC"
    confidence = combined_fake if is_fake else combined_real

    print("=" * 60)
    print("HYBRID IMAGE MANIPULATION DETECTION REPORT")
    print("=" * 60)
    print(f"Target Image:      {image_path}")
    print(f"Model:             {model_path.name}")
    print(f"Prediction:        {prediction_label}")
    print(f"Confidence:        {confidence * 100:.2f}%")
    print("-" * 60)
    print(f"Fake Probability:  {combined_fake:.4f}")
    print(f"Real Probability:  {combined_real:.4f}")
    print(f"Deep CNN Score:    Raw Real={raw_real:.4f} -> Calibrated Fake={model_fake_prob:.4f}")
    print(f"ELA Anomaly Score: {ela_score:.4f} (p95={forensics['p95_ela_error']:.1f})")
    print(f"Noise Inconsistency:{noise_score:.4f} (ratio={forensics['noise_discrepancy_ratio']:.1f})")
    print("=" * 60)

    if args.save_heatmap:
        save_p = Path(args.save_heatmap)
        cv2.imwrite(str(save_p), forensics["heatmap"])
        print(f"Tampering heatmap overlay saved to: {save_p}")


if __name__ == "__main__":
    main()
