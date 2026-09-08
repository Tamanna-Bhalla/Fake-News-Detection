import { useState } from 'react';
import { ShieldCheck, AlertTriangle, Eye, Activity, Cpu, Sparkles, Layers } from 'lucide-react';
import { Badge } from '../ui/Badge';

export const ImageVerificationResult = ({ result }) => {
  const [showHeatmap, setShowHeatmap] = useState(false);

  if (!result) return null;

  const {
    is_fake,
    verdict,
    manipulation_type,
    confidence,
    probabilities,
    explanation,
    forensic_details,
    heatmap_base64,
    error,
  } = result;

  if (error) {
    return (
      <div className="w-full bg-background-card border border-verdict-false/30 rounded-xl p-6">
        <div className="flex items-start gap-4">
          <AlertTriangle className="h-6 w-6 text-verdict-false flex-shrink-0 mt-1" />
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-text-primary mb-2">
              Image Analysis Failed
            </h3>
            <p className="text-text-secondary">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (is_fake === null) {
    return (
      <div className="w-full bg-background-card border border-text-muted/30 rounded-xl p-6">
        <p className="text-text-secondary text-center">
          {explanation || 'Unable to analyze the image.'}
        </p>
      </div>
    );
  }

  const isSuspicious = is_fake;
  const statusColor = isSuspicious ? 'verdict-false' : 'verdict-true';
  const displayVerdict = verdict || (isSuspicious ? 'Manipulated / Tampered' : 'Authentic');
  const confidencePercent = (confidence * 100).toFixed(1);

  const elaMetrics = forensic_details?.ela_metrics;
  const noiseMetrics = forensic_details?.noise_metrics;

  return (
    <div className={`w-full bg-background-card border border-${statusColor}/30 rounded-xl p-6 flex flex-col gap-6`}>
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
          <div className="space-y-2.5">
            <div>
              <div className="flex justify-between mb-1 text-xs">
                <span className="font-medium text-text-secondary">Manipulated / Spliced Probability</span>
                <span className="font-semibold text-text-primary">
                  {(probabilities.fake * 100).toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-background-secondary h-2.5 rounded-full overflow-hidden">
                <div
                  className="h-full bg-verdict-false transition-all duration-500"
                  style={{ width: `${probabilities.fake * 100}%` }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between mb-1 text-xs">
                <span className="font-medium text-text-secondary">Authentic / Consistent Probability</span>
                <span className="font-semibold text-text-primary">
                  {(probabilities.real * 100).toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-background-secondary h-2.5 rounded-full overflow-hidden">
                <div
                  className="h-full bg-verdict-true transition-all duration-500"
                  style={{ width: `${probabilities.real * 100}%` }}
                />
              </div>
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between text-xs text-text-muted border-t border-border-default/50 pt-3">
            <span>Overall Analysis Confidence: <strong className="text-text-primary">{confidencePercent}%</strong></span>
            {forensic_details?.dimensions && (
              <span>Original Size: {forensic_details.dimensions.width} &times; {forensic_details.dimensions.height}px</span>
            )}
          </div>
        </div>
      </div>

      {/* Forensic Signal Breakdown Panel */}
      {forensic_details && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3.5 bg-background-secondary/40 rounded-xl border border-border-default/60 text-xs">
          <div className="flex flex-col gap-1 p-2 rounded-lg bg-background-card/50">
            <span className="text-text-muted flex items-center gap-1 font-medium">
              <Layers className="h-3.5 w-3.5 text-accent-blue" />
              Error Level (ELA)
            </span>
            <span className="text-sm font-semibold text-text-primary">
              {elaMetrics ? `${(elaMetrics.ela_anomaly_score * 100).toFixed(0)}% Discrepancy` : 'N/A'}
            </span>
            <span className="text-[10px] text-text-muted">
              JPEG quantization grid difference
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
              Spatial PRNU & noise consistency
            </span>
          </div>

          <div className="flex flex-col gap-1 p-2 rounded-lg bg-background-card/50">
            <span className="text-text-muted flex items-center gap-1 font-medium">
              <Cpu className="h-3.5 w-3.5 text-indigo-400" />
              Neural Classifier
            </span>
            <span className="text-sm font-semibold text-text-primary">
              {forensic_details.calibrated_model_fake_prob
                ? `${(forensic_details.calibrated_model_fake_prob * 100).toFixed(0)}% Artifact Score`
                : 'N/A'}
            </span>
            <span className="text-[10px] text-text-muted">
              Calibrated EfficientNetB0 features
            </span>
          </div>
        </div>
      )}

      {/* Interactive Tampering Heatmap Section */}
      {heatmap_base64 && (
        <div className="flex flex-col gap-3 p-4 bg-background-secondary/30 rounded-xl border border-border-default/80">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-accent-blue" />
              <h4 className="text-sm font-semibold text-text-primary">
                Tampering Localization Heatmap
              </h4>
            </div>
            <button
              onClick={() => setShowHeatmap(!showHeatmap)}
              className="px-3 py-1.5 text-xs font-medium bg-background-card hover:bg-background-secondary border border-border-default rounded-lg text-text-primary flex items-center gap-1.5 transition-colors"
            >
              <Eye className="h-3.5 w-3.5 text-accent-blue" />
              {showHeatmap ? 'Hide Heatmap' : 'View Tampering Heatmap'}
            </button>
          </div>

          {showHeatmap && (
            <div className="flex flex-col items-center gap-2 animate-in fade-in duration-300">
              <div className="relative rounded-lg overflow-hidden border border-border-default max-h-80 w-auto bg-black/40">
                <img
                  src={heatmap_base64}
                  alt="Tampering Heatmap"
                  className="max-h-80 w-auto object-contain mx-auto"
                />
              </div>
              <p className="text-[11px] text-text-muted text-center max-w-md">
                Red and yellow highlights represent regions with anomalous compression error levels or inconsistent sensor noise signatures. Blue represents consistent background.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Non-Definitive Probabilistic Disclaimer */}
      <p className="text-[11px] text-text-muted italic border-t border-border-default/40 pt-2">
        Disclaimer: Digital manipulation analysis generates probabilistic evidence based on pixel statistics, compression history, and deep artifact signatures. It does not provide absolute certainty.
      </p>
    </div>
  );
};
