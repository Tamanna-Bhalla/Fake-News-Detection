import { VerdictBadge } from './VerdictBadge';
import { ConfidenceMeter } from './ConfidenceMeter';
import { Tag } from 'lucide-react';

export const VerdictCard = ({ claim, verdict, confidence, summary, conflictingSources, claimType }) => {
  const isConfidenceAvailable = confidence !== null && confidence !== undefined;
  const formattedConfidence = isConfidenceAvailable ? `${Math.round(confidence * 100)}%` : 'N/A';

  const claimTypeLabels = {
    historical: 'Historical Fact',
    numeric: 'Numeric / Statistical',
    quote: 'Quote Attribution',
    medical: 'Medical / Health',
    scientific: 'Scientific Claim',
    political: 'Political Assertion',
    opinion: 'Subjective Opinion',
    prediction: 'Future Prediction',
    satire: 'Satire / Humor',
    non_verifiable: 'Non-Verifiable Statement',
    current_event: 'Current Event',
  };

  return (
    <div className="p-6 md:p-8 bg-background-card rounded-xl border border-border-default shadow-sm flex flex-col gap-6 animate-in slide-in-from-bottom-2 duration-500">
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="flex flex-col gap-2 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-text-muted uppercase tracking-widest">Analyzed Claim</span>
            {claimType && (
              <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-background-secondary border border-border-default text-text-secondary font-medium">
                <Tag className="h-3 w-3 text-accent-blue" />
                {claimTypeLabels[claimType] || claimType}
              </span>
            )}
          </div>
          <h2 className="text-xl md:text-2xl font-bold text-text-primary leading-snug">
            "{claim}"
          </h2>
        </div>
        <div className="shrink-0 flex flex-col items-end gap-2">
          <VerdictBadge verdict={verdict} />
          <p className="text-right text-xs text-text-secondary">
            {isConfidenceAvailable ? (
              <>Confidence: <strong className="text-text-primary">{formattedConfidence}</strong></>
            ) : (
              <span className="text-text-muted italic">Confidence: Inconclusive</span>
            )}
          </p>
          {conflictingSources ? (
            <span className="text-xs font-semibold px-2 py-1 rounded-full bg-verdict-misleading/15 text-verdict-misleading border border-verdict-misleading/40">
              Conflicting Sources
            </span>
          ) : null}
        </div>
      </div>

      {summary ? (
        <p className="text-sm text-text-secondary leading-relaxed border-l-2 border-accent-blue pl-3">
          {summary}
        </p>
      ) : null}
      
      {isConfidenceAvailable && (
        <div className="pt-4 border-t border-border-dim">
          <ConfidenceMeter confidence={confidence} />
        </div>
      )}
    </div>
  );
};