import { useState } from 'react';
import { ShieldCheck, AlertTriangle, Eye, Activity, Cpu, Sparkles, Layers, Info } from 'lucide-react';
import { Badge } from '../ui/Badge';

export const ImageVerificationResult = ({ result }) => {
  const [showHeatmap, setShowHeatmap] = useState(false);

  if (!result) return null;

  // Extract from either root result or nested image_assessment
  const assessment = result.image_assessment || result;
  const classification = assessment.classification || {};
  const anomaly = assessment.anomaly_analysis || {};
  const localization = assessment.localization || {};

  const is_fake = classification.is_manipulated ?? result.is_fake;
  const verdict = assessment.verdict || classification.status_label || result.verdict;
  const manipulation_type = classification.manipulation_type || result.manipulation_type;
  const confidence = assessment.confidence ?? classification.confidence ?? result.confidence;
  const probabilities = classification.probabilities || result.probabilities;
  const explanation = assessment.summary || classification.explanation || result.explanation;
  const forensic_details = assessment.forensic_details || result.forensic_details || {};
  const heatmap_base64 = localization.heatmap_base64 || result.heatmap_base64;
  const error = result.error || assessment.error_code;
  const status = assessment.status || 'completed';

  if (error) {
    return (
      <div className="w-full bg-background-card border border-verdict-false/30 rounded-xl p-6">
        <div className="flex items-start gap-4">
          <AlertTriangle className="h-6 w-6 text-verdict-false flex-shrink-0 mt-1" />
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-text-primary mb-2">
              Image Forensics Unavailable
            </h3>
            <p className="text-text-secondary text-sm">
              {typeof error === 'string' ? error : error.message || 'Image analysis encountered an issue.'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Handle Unsupported / Low quality or Unknown
  const isOutOfDistribution = verdict === 'Unsupported / Low quality' || verdict === 'Unknown' || status === 'unavailable';

  if (is_fake === null || isOutOfDistribution) {
    return (
      <div className="w-full bg-background-card border border-amber-500/40 rounded-xl p-6 flex flex-col gap-4">
        <div className="flex items-start gap-4">
          <Info className="h-6 w-6 text-amber-400 flex-shrink-0 mt-1" />
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <h3 className="text-lg font-bold text-text-primary">
                Forensic Assessment Inconclusive
              </h3>
              <Badge variant="warning">
                {verdict || 'Unsupported / Low quality'}
              </Badge>
            </div>
            <p className="text-text-secondary text-sm leading-relaxed mb-3">
              {explanation || 'The image could not be reliably classified due to resolution, compression, or format constraints.'}
            </p>
            <div className="p-3 bg-background-secondary/50 rounded-lg border border-border-default text-xs text-text-muted">
              <strong>Quality Criteria:</strong> Forensic analysis requires images between 32&times;32px and 4096&times;4096px with sufficient high-frequency textural detail to evaluate compression grids and sensor noise residuals.
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isSuspicious = is_fake === true;
  const statusColor = isSuspicious ? 'verdict-false' : 'verdict-true';
  const displayVerdict = verdict || (isSuspicious ? 'Manipulated / Tampered' : 'Authentic / Consistent');
  const confidencePercent = confidence !== null && confidence !== undefined
    ? (confidence * 100).toFixed(1)
    : 'N/A';

  const elaMetrics = anomaly.ela_metrics || forensic_details.ela_metrics;
  const noiseMetrics = anomaly.noise_metrics || forensic_details.noise_metrics;
  const fakeProb = probabilities?.fake ?? probabilities?.manipulated ?? 0;
  const realProb = probabilities?.real ?? probabilities?.authentic ?? (1 - fakeProb);

  return (
    <div className={`w-full bg-background-card border border-${statusColor}/30 rounded-xl p-6 flex flex-col gap-6 shadow-sm`}>
      {/* Top Banner */}
      <div className="flex items-start gap-4">
        <div className={`h-12 w-12 rounded-lg bg-${statusColor}/20 flex items-center justify-center flex-shrink-0`}>
          {isSuspicious ? (
            <AlertTriangle className={`h-6 w-6 text-${statusColor}`} />
          ) : (
            <ShieldCheck className={`h-6 w-6 text-${statusColor}`} />
          )}
        </div>

        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <h3 className="text-lg font-bold text-text-primary">
              Image Forensics Engine
            </h3>
            <Badge variant={isSuspicious ? 'false' : 'true'}>
              {displayVerdict}
            </Badge>
            {manipulation_type && manipulation_type !== 'Consistent / Authentic' && (
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-background-secondary border border-border-default text-text-secondary font-medium">
                {manipulation_type}
              </span>
            )}
          </div>

          <p className="text-text-secondary text-sm leading-relaxed mb-4">
            {explanation}
          </p>

          {/* Probability Bars */}
          {probabilities && (
            <div className="space-y-2.5">
              <div>
                <div className="flex justify-between mb-1 text-xs">
                  <span className="font-medium text-text-secondary">Manipulated / Spliced Probability</span>
                  <span className="font-semibold text-text-primary">
                    {(fakeProb * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-background-secondary h-2.5 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-verdict-false transition-all duration-500"
                    style={{ width: `${fakeProb * 100}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between mb-1 text-xs">
                  <span className="font-medium text-text-secondary">Authentic / Consistent Probability</span>
                  <span className="font-semibold text-text-primary">
                    {(realProb * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-background-secondary h-2.5 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-verdict-true transition-all duration-500"
                    style={{ width: `${realProb * 100}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          <div className="mt-4 flex items-center justify-between text-xs text-text-muted border-t border-border-default/50 pt-3">
            <span>Calibrated Forensic Confidence: <strong className="text-text-primary">{confidencePercent}%</strong></span>
            {forensic_details?.dimensions && (
              <span>Dimensions: {forensic_details.dimensions.width} &times; {forensic_details.dimensions.height}px</span>
            )}
          </div>
        </div>
      </div>

      {/* Forensic Anomaly Signals Breakdown */}
      {(elaMetrics || noiseMetrics || forensic_details.calibrated_model_fake_prob !== undefined) && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3.5 bg-background-secondary/40 rounded-xl border border-border-default/60 text-xs">
          <div className="flex flex-col gap-1 p-2 rounded-lg bg-background-card/50">
            <span className="text-text-muted flex items-center gap-1 font-medium">
              <Layers className="h-3.5 w-3.5 text-accent-blue" />
              Error Level Analysis (ELA)
            </span>
            <span className="text-sm font-semibold text-text-primary">
              {elaMetrics ? `${(elaMetrics.ela_anomaly_score * 100).toFixed(0)}% Residual` : 'N/A'}
            </span>
            <span className="text-[10px] text-text-muted">
              JPEG re-compression error gradient
            </span>
          </div>

          <div className="flex flex-col gap-1 p-2 rounded-lg bg-background-card/50">
            <span className="text-text-muted flex items-center gap-1 font-medium">
              <Activity className="h-3.5 w-3.5 text-amber-500" />
              Sensor Noise Variance
            </span>
            <span className="text-sm font-semibold text-text-primary">
              {noiseMetrics ? `${noiseMetrics.noise_discrepancy_ratio.toFixed(1)}x Discrepancy` : 'N/A'}
            </span>
            <span className="text-[10px] text-text-muted">
              PRNU & wavelet residual consistency
            </span>
          </div>

          <div className="flex flex-col gap-1 p-2 rounded-lg bg-background-card/50">
            <span className="text-text-muted flex items-center gap-1 font-medium">
              <Cpu className="h-3.5 w-3.5 text-indigo-400" />
              Calibrated Deep Feature
            </span>
            <span className="text-sm font-semibold text-text-primary">
              {forensic_details.calibrated_model_fake_prob !== undefined
                ? `${(forensic_details.calibrated_model_fake_prob * 100).toFixed(0)}% Discrepancy`
                : 'N/A'}
            </span>
            <span className="text-[10px] text-text-muted">
              Platt-scaled EfficientNetB0 output
            </span>
          </div>
        </div>
      )}

      {/* Forensic Anomaly Map Section */}
      {heatmap_base64 && (
        <div className="flex flex-col gap-3 p-4 bg-background-secondary/30 rounded-xl border border-border-default/80">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-accent-blue" />
              <div>
                <h4 className="text-sm font-semibold text-text-primary">
                  Forensic Anomaly Map (Residual Analysis)
                </h4>
                <p className="text-[11px] text-text-muted">
                  Visualizes spatial variations in compression error and sensor noise
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowHeatmap(!showHeatmap)}
              className="px-3 py-1.5 text-xs font-medium bg-background-card hover:bg-background-secondary border border-border-default rounded-lg text-text-primary flex items-center gap-1.5 transition-colors"
            >
              <Eye className="h-3.5 w-3.5 text-accent-blue" />
              {showHeatmap ? 'Hide Anomaly Map' : 'View Anomaly Map'}
            </button>
          </div>

          {showHeatmap && (
            <div className="flex flex-col items-center gap-2 animate-in fade-in duration-300">
              <div className="relative rounded-lg overflow-hidden border border-border-default max-h-80 w-auto bg-black/40">
                <img
                  src={heatmap_base64}
                  alt="Forensic Anomaly Map"
                  className="max-h-80 w-auto object-contain mx-auto"
                />
              </div>
              <p className="text-[11px] text-text-muted text-center max-w-lg">
                <strong>Color legend:</strong> Warm tones (yellow, red) denote regions with statistically elevated compression error levels or anomalous noise residual patterns. Cool tones (blue) indicate baseline consistency.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Prominent Disclaimer Banner */}
      <div className="p-3 bg-background-secondary/60 rounded-lg border border-border-default/70 flex items-start gap-2.5">
        <Info className="h-4 w-4 text-accent-blue flex-shrink-0 mt-0.5" />
        <p className="text-[11px] text-text-muted leading-relaxed">
          <strong className="text-text-primary">Automated forensic assessment:</strong> Visual anomalies indicate statistical discrepancies (such as multiple compression cycles, resizing, or sensor noise inconsistency), not definitive proof of malicious manipulation.
        </p>
      </div>
    </div>
  );
};
