import os
import io
import base64
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import tensorflow as tf
import numpy as np
import cv2
from PIL import Image, ImageChops, ImageOps

logger = logging.getLogger(__name__)


class ForensicAnalyzer:
    """Forensic analysis suite for image manipulation detection.
    
    Implements:
      1. Error Level Analysis (ELA) for JPEG compression disparity.
      2. High-Pass Spatial Noise Residual Analysis for sensor noise inconsistencies.
      3. Anomaly Localization Heatmap (Base64 PNG overlay).
    """

    @staticmethod
    def compute_ela(image: Image.Image, quality: int = 90) -> Tuple[np.ndarray, Dict[str, float]]:
        """Compute Error Level Analysis (ELA) between the image and a recompressed JPEG version."""
        image_rgb = image.convert("RGB")
        
        # Save to memory buffer at standard quality
        buffer = io.BytesIO()
        image_rgb.save(buffer, "JPEG", quality=quality)
        buffer.seek(0)
        compressed = Image.open(buffer)

        # Compute difference
        diff = ImageChops.difference(image_rgb, compressed)
        diff_arr = np.array(diff, dtype=np.float32)
        ela_gray = np.mean(diff_arr, axis=2)

        mean_error = float(np.mean(ela_gray))
        std_error = float(np.std(ela_gray))
        max_error = float(np.max(ela_gray))
        p95_error = float(np.percentile(ela_gray, 95))

        # Check local patch variance (measure spatial inconsistency)
        h, w = ela_gray.shape
        grid_h, grid_w = max(4, h // 32), max(4, w // 32)
        patch_means = []
        for y in range(0, h - grid_h + 1, grid_h):
            for x in range(0, w - grid_w + 1, grid_w):
                patch = ela_gray[y : y + grid_h, x : x + grid_w]
                patch_means.append(np.mean(patch))

        patch_means = np.array(patch_means, dtype=np.float32)
        if mean_error < 1.0:
            patch_variance_ratio = float(np.std(patch_means) / (mean_error + 1.0))
            ela_score = float(np.clip(std_error / 15.0, 0.0, 0.35))
        else:
            patch_variance_ratio = float(np.std(patch_means) / (mean_error + 2.0))
            ela_score = float(np.clip((patch_variance_ratio * 0.4) + (std_error / 25.0 * 0.6), 0.0, 1.0))

        metrics = {
            "mean_error": round(mean_error, 3),
            "std_error": round(std_error, 3),
            "max_error": round(max_error, 3),
            "p95_error": round(p95_error, 3),
            "patch_variance_ratio": round(patch_variance_ratio, 3),
            "ela_anomaly_score": round(ela_score, 4),
        }

        return ela_gray, metrics

    @staticmethod
    def compute_noise_residual(image: Image.Image) -> Tuple[np.ndarray, Dict[str, float]]:
        """Compute high-pass spatial noise residual to detect sensor noise anomalies and inpainting."""
        rgb_arr = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2GRAY).astype(np.float32)

        # High-pass filter using Laplacian
        laplacian = cv2.Laplacian(gray, cv2.CV_32F)
        abs_lap = np.abs(laplacian)

        # Compute local noise energy using spatial box filter
        kernel_size = 16
        local_noise_energy = cv2.blur(abs_lap, (kernel_size, kernel_size))

        mean_noise = float(np.mean(local_noise_energy))
        std_noise = float(np.std(local_noise_energy))

        # Check noise variance across image grid
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
        noise_discrepancy_ratio = float(max_var / (med_var + 1e-4))

        # Normalized noise inconsistency score:
        # In natural authentic photographs, depth of field and scene textures cause normal ratios up to 25.
        # Spliced / manipulated regions typically cause ratios > 50 to 200+.
        if noise_discrepancy_ratio <= 25.0:
            noise_score = float(np.clip((noise_discrepancy_ratio - 1.0) / 200.0, 0.0, 0.12))
        else:
            noise_score = float(np.clip(0.12 + 0.88 * ((noise_discrepancy_ratio - 25.0) / 80.0), 0.12, 1.0))

        metrics = {
            "mean_noise_level": round(mean_noise, 3),
            "noise_std": round(std_noise, 3),
            "noise_discrepancy_ratio": round(noise_discrepancy_ratio, 3),
            "noise_anomaly_score": round(noise_score, 4),
        }

        return local_noise_energy, metrics

    @staticmethod
    def generate_heatmap(ela_gray: np.ndarray, noise_map: np.ndarray) -> str:
        """Combine ELA and noise residuals to generate a colorized tampering heatmap overlay as Base64."""
        # Resize noise_map to match ela_gray if dimensions differ
        if noise_map.shape != ela_gray.shape:
            noise_map = cv2.resize(noise_map, (ela_gray.shape[1], ela_gray.shape[0]))

        # Min-max normalization of both signals
        ela_norm = (ela_gray - np.min(ela_gray)) / (np.ptp(ela_gray) + 1e-5)
        noise_norm = (noise_map - np.min(noise_map)) / (np.ptp(noise_map) + 1e-5)

        # Weighted combination favoring ELA for compression differences and noise for splicing
        combined = (0.6 * ela_norm) + (0.4 * noise_norm)

        # Smooth to produce clean, coherent spatial blobs
        blurred = cv2.GaussianBlur(combined, (15, 15), 0)
        heat_uint8 = np.clip(blurred * 255.0, 0, 255).astype(np.uint8)

        # Apply JET colormap (blue = low anomaly, red = high anomaly)
        colored = cv2.applyColorMap(heat_uint8, cv2.COLORMAP_JET)

        # Add alpha channel so it functions as an overlay
        alpha = np.clip(heat_uint8 * 1.5, 60, 200).astype(np.uint8)
        bgra = cv2.cvtColor(colored, cv2.COLOR_BGR2BGRA)
        bgra[:, :, 3] = alpha

        # Encode as PNG base64
        success, encoded = cv2.imencode(".png", bgra)
        if not success:
            return ""

        b64_str = base64.b64encode(encoded).decode("utf-8")
        return f"data:image/png;base64,{b64_str}"


class ImageManipulationDetector:
    """Production service for detecting fake/manipulated images using a hybrid
    forensic analysis engine (ELA + Noise Residuals) fused with a calibrated EfficientNetB0 CNN.
    """

    IMG_SIZE = 224
    CLASS_NAMES = ["fake", "real"]
    VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}

    def __init__(self, model_path: Optional[str] = None):
        """Initialize the image detector with model weights and forensic analyzer."""
        if model_path is None:
            base_dir = Path(__file__).parent.parent.parent.parent
            model_path = base_dir / "Image Detection" / "efficientnetb0_fake_detector.keras"

        self.model_path = Path(model_path)
        self.model = None
        self.preprocess_fn = None
        self.forensics = ForensicAnalyzer()

        if self.model_path.exists():
            self._load_model()
        else:
            logger.warning("image_model_not_found path=%s", self.model_path)

    def _load_model(self):
        """Load the Keras model with quantization config patching if needed."""
        try:
            self.model = tf.keras.models.load_model(self.model_path)
            self._set_preprocess_fn()
            logger.info("loaded_image_model path=%s", self.model_path)
        except (TypeError, ValueError) as exc:
            if self.model_path.suffix != ".keras" or "quantization_config" not in str(exc):
                raise
            self._load_with_patch()

    def _load_with_patch(self):
        """Load model with quantization config patching."""
        from contextlib import contextmanager

        @contextmanager
        def _patch_dense_from_config():
            dense_layer = tf.keras.layers.Dense
            original_from_config = dense_layer.from_config.__func__

            def patched_from_config(cls, config):
                cfg = dict(config)
                cfg.pop("quantization_config", None)
                return original_from_config(cls, cfg)

            dense_layer.from_config = classmethod(patched_from_config)
            try:
                yield
            finally:
                dense_layer.from_config = classmethod(original_from_config)

        with _patch_dense_from_config():
            self.model = tf.keras.models.load_model(self.model_path)
        self._set_preprocess_fn()
        logger.info("loaded_image_model_with_patch path=%s", self.model_path)

    def _set_preprocess_fn(self):
        """Set preprocessing function based on EfficientNetB0."""
        self.preprocess_fn = tf.keras.applications.efficientnet.preprocess_input

    def _safe_load_image(self, image_bytes: bytes) -> Image.Image:
        """Safely parse image bytes and handle color profiles and transparency."""
        image = Image.open(io.BytesIO(image_bytes))

        # Handle EXIF orientation if present
        try:
            image = ImageOps.exif_transpose(image)
        except Exception:
            pass

        # Handle RGBA / Palette / Grayscale gracefully
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            bg = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            bg.paste(image, mask=image.split()[-1])
            return bg

        return image.convert("RGB")

    def _prepare_cnn_input(self, image: Image.Image) -> tf.Tensor:
        """Resize and preprocess image for the deep CNN model."""
        resized = image.resize((self.IMG_SIZE, self.IMG_SIZE), Image.Resampling.BILINEAR)
        arr = tf.keras.utils.img_to_array(resized)
        batch = tf.expand_dims(arr, axis=0)
        return self.preprocess_fn(batch)

    def _calibrate_model_score(self, raw_sigmoid: float) -> Tuple[float, float]:
        """Calibrate raw model sigmoid output.
        
        The model was trained with:
          class 0 = 'fake' (0.0)
          class 1 = 'real' (1.0)
        Raw sigmoid score represents P(real).
        
        Because out-of-domain images exhibit calibration bias (unmanipulated images scoring ~0.35-0.45),
        we apply a smooth calibration mapping:
          Scores >= 0.50 indicate high authenticity.
          Scores around 0.35-0.45 are borderline.
          Scores < 0.25 indicate strong manipulation artifacts.
        """
        raw_real = float(np.clip(raw_sigmoid, 0.0, 1.0))

        # Center logistic calibration at empirical decision boundary 0.265
        midpoint = 0.265
        scale = 10.0
        calibrated_real = float(1.0 / (1.0 + np.exp(-scale * (raw_real - midpoint))))
        calibrated_fake = 1.0 - calibrated_real

        return calibrated_real, calibrated_fake

    def predict(self, image_bytes: bytes, threshold: float = 0.50) -> Dict[str, Any]:
        """Perform comprehensive forensic and deep learning image manipulation analysis.
        
        Args:
            image_bytes: Raw image file bytes.
            threshold: Classification decision threshold (default 0.50).
            
        Returns:
            dict containing:
              - is_fake: bool (True = manipulated/fake, False = authentic/real)
              - verdict: str ('Authentic', 'Likely Authentic', 'Suspicious', 'Manipulated')
              - manipulation_type: str
              - confidence: float (0.0 to 1.0)
              - probabilities: dict with 'fake' and 'real' probabilities
              - forensic_details: dict with ELA, noise, and model metrics
              - heatmap_base64: data URI string of the tampering heatmap overlay
              - explanation: human-readable explanation
              - error: Optional error string
        """
        try:
            image = self._safe_load_image(image_bytes)
        except Exception as exc:
            logger.warning("invalid_image_file error=%s", exc)
            return {
                "is_fake": None,
                "verdict": "Unknown",
                "manipulation_type": None,
                "confidence": 0.0,
                "classification": {"label": "unknown", "probability": 0.5},
                "anomaly_analysis": {"ela_score": 0.0, "noise_score": 0.0, "forensic_details": None},
                "localization": {"available": False, "heatmap_type": "forensic_anomaly", "heatmap_base64": None},
                "probabilities": {"fake": 0.0, "real": 0.0},
                "explanation": f"Failed to load image: {type(exc).__name__}",
                "forensic_details": None,
                "heatmap_base64": None,
                "disclaimer": "Failed to decode image stream.",
                "error": f"Invalid image file: {str(exc)}",
            }

        # Out-of-Distribution & Unsupported Quality Guardrails
        if image.width < 32 or image.height < 32:
            return {
                "is_fake": None,
                "verdict": "Unsupported / Low quality",
                "manipulation_type": "Low Resolution",
                "confidence": 0.0,
                "classification": {"label": "unknown", "probability": 0.5},
                "anomaly_analysis": {"ela_score": 0.0, "noise_score": 0.0, "forensic_details": None},
                "localization": {"available": False, "heatmap_type": "forensic_anomaly", "heatmap_base64": None},
                "probabilities": {"fake": 0.0, "real": 0.0},
                "explanation": f"Image resolution ({image.width}x{image.height}px) is too low for reliable forensic analysis.",
                "forensic_details": {"dimensions": {"width": image.width, "height": image.height}},
                "heatmap_base64": None,
                "disclaimer": "Input resolution is insufficient to extract compression grids or sensor noise residuals.",
                "error": None,
            }

        gray_arr = np.array(image.convert("L"), dtype=np.float32)
        if float(np.std(gray_arr)) < 1.5:
            return {
                "is_fake": None,
                "verdict": "Unsupported / Low quality",
                "manipulation_type": "Uniform Content",
                "confidence": 0.0,
                "classification": {"label": "unknown", "probability": 0.5},
                "anomaly_analysis": {"ela_score": 0.0, "noise_score": 0.0, "forensic_details": None},
                "localization": {"available": False, "heatmap_type": "forensic_anomaly", "heatmap_base64": None},
                "probabilities": {"fake": 0.0, "real": 0.0},
                "explanation": "Image content is uniform or lacks spatial variance necessary for forensic analysis.",
                "forensic_details": {"dimensions": {"width": image.width, "height": image.height}},
                "heatmap_base64": None,
                "disclaimer": "Uniform images lack textural signal for noise or compression analysis.",
                "error": None,
            }

        # 1. Forensic Stream: ELA
        try:
            ela_map, ela_metrics = self.forensics.compute_ela(image)
        except Exception as exc:
            logger.warning("ela_failed error=%s", exc)
            ela_map = np.zeros((image.height, image.width), dtype=np.float32)
            ela_metrics = {"ela_anomaly_score": 0.0, "mean_error": 0.0}

        # 2. Forensic Stream: Noise Residual Analysis
        try:
            noise_map, noise_metrics = self.forensics.compute_noise_residual(image)
        except Exception as exc:
            logger.warning("noise_analysis_failed error=%s", exc)
            noise_map = np.zeros((image.height, image.width), dtype=np.float32)
            noise_metrics = {"noise_anomaly_score": 0.0, "noise_discrepancy_ratio": 1.0}

        # 3. Spatial Forensic Anomaly Map (formerly "tampering heatmap")
        try:
            heatmap_b64 = self.forensics.generate_heatmap(ela_map, noise_map)
        except Exception as exc:
            logger.warning("heatmap_failed error=%s", exc)
            heatmap_b64 = None

        # 4. Deep Model Stream
        model_real_score = 0.5
        model_fake_score = 0.5
        raw_model_output = None

        if self.model is not None:
            try:
                prepared = self._prepare_cnn_input(image)
                preds = self.model.predict(prepared, verbose=0)
                raw_val = float(preds[0][0])
                raw_model_output = round(raw_val, 4)
                model_real_score, model_fake_score = self._calibrate_model_score(raw_val)
            except Exception as exc:
                logger.exception("deep_model_prediction_failed error=%s", exc)
                model_real_score = 0.5
                model_fake_score = 0.5

        # 5. Multi-Signal Fusion
        ela_score = ela_metrics.get("ela_anomaly_score", 0.0)
        noise_score = noise_metrics.get("noise_anomaly_score", 0.0)

        # Weighted combination: 40% CNN representation, 35% ELA compression, 25% noise discrepancy
        weighted_fake = float(
            (0.40 * model_fake_score) + (0.35 * ela_score) + (0.25 * noise_score)
        )

        # Forensic anomaly booster: if either ELA or Noise shows strong physical inconsistency (>= 0.70),
        # flag physical anomaly evidence.
        max_forensic_anomaly = max(ela_score, noise_score)
        if max_forensic_anomaly >= 0.70:
            combined_fake_prob = float(max(weighted_fake, 0.65 + 0.30 * ((max_forensic_anomaly - 0.70) / 0.30)))
        else:
            combined_fake_prob = weighted_fake

        combined_fake_prob = float(np.clip(combined_fake_prob, 0.01, 0.99))
        combined_real_prob = float(1.0 - combined_fake_prob)

        # Determine Categorical Verdict
        if combined_fake_prob >= 0.65:
            verdict = "Manipulated / Tampered"
            is_fake = True
            confidence = combined_fake_prob
        elif combined_fake_prob >= 0.50:
            verdict = "Suspicious / Potential Manipulation"
            is_fake = True
            confidence = combined_fake_prob
        elif combined_fake_prob >= 0.35:
            verdict = "Likely Authentic"
            is_fake = False
            confidence = combined_real_prob
        else:
            verdict = "Authentic"
            is_fake = False
            confidence = combined_real_prob

        # Determine Manipulation Category
        if not is_fake:
            manipulation_type = "Consistent / Authentic"
        else:
            if ela_score > 0.60 and noise_score > 0.50:
                manipulation_type = "Splicing & Noise Inconsistency"
            elif ela_score > 0.60:
                manipulation_type = "Compression Artifact / Splicing"
            elif noise_score > 0.50:
                manipulation_type = "Inpainting / Object Insertion"
            else:
                manipulation_type = "Deep Tampering Anomaly"

        # Generate Human-Readable Forensic Explanation
        confidence_pct = confidence * 100.0
        if is_fake:
            reasons = []
            if ela_score > 0.50:
                reasons.append(f"inconsistent JPEG compression levels (ELA anomaly {ela_score:.2f})")
            if noise_score > 0.45:
                reasons.append(f"spatial sensor noise variance anomalies (ratio {noise_metrics.get('noise_discrepancy_ratio', 1.0):.1f})")
            if model_fake_score > 0.55:
                reasons.append(f"neural manipulation artifact detector ({model_fake_score*100:.1f}%)")

            reason_text = ", and ".join(reasons) if reasons else "detected anomalies in image texture"
            explanation = (
                f"Image flagged as {verdict.lower()} ({confidence_pct:.1f}% confidence) "
                f"due to {reason_text}. See forensic anomaly map for artifact regions."
            )
        else:
            explanation = (
                f"Image appears {verdict.lower()} ({confidence_pct:.1f}% confidence). "
                f"Compression error levels and high-frequency sensor noise are spatially uniform."
            )

        forensic_details = {
            "ela_metrics": ela_metrics,
            "noise_metrics": noise_metrics,
            "deep_model_raw": raw_model_output,
            "calibrated_model_fake_prob": round(model_fake_score, 4),
            "combined_manipulation_score": round(combined_fake_prob, 4),
            "dimensions": {"width": image.width, "height": image.height},
        }

        classification_res = {
            "label": "suspicious" if is_fake else "authentic",
            "probability": round(combined_fake_prob if is_fake else combined_real_prob, 4)
        }

        anomaly_analysis_res = {
            "ela_score": round(ela_score, 4),
            "noise_score": round(noise_score, 4),
            "forensic_details": forensic_details
        }

        localization_res = {
            "available": heatmap_b64 is not None,
            "heatmap_type": "forensic_anomaly",
            "heatmap_base64": heatmap_b64
        }

        return {
            "is_fake": is_fake,
            "verdict": verdict,
            "manipulation_type": manipulation_type,
            "confidence": round(confidence, 4),
            "probabilities": {
                "fake": round(combined_fake_prob, 4),
                "real": round(combined_real_prob, 4),
            },
            "classification": classification_res,
            "anomaly_analysis": anomaly_analysis_res,
            "localization": localization_res,
            "forensic_details": forensic_details,
            "heatmap_base64": heatmap_b64,
            "explanation": explanation,
            "disclaimer": "Automated forensic assessment: visual anomalies indicate statistical discrepancies, not definitive proof of manipulation.",
            "error": None,
        }



# Global singleton instance (lazy loaded)
_detector_instance = None


def get_image_detector() -> ImageManipulationDetector:
    """Get or initialize the global ImageManipulationDetector singleton."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = ImageManipulationDetector()
    return _detector_instance
