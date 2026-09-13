import { ExternalLink, Link as LinkIcon, ShieldCheck, CheckCircle2, XCircle, MinusCircle, Hash } from 'lucide-react';
import { Badge } from '../ui/Badge';

export const EvidenceCard = ({ evidence }) => {
  const {
    title,
    snippet,
    excerpt,
    credibility,
    url,
    publisher,
    published_at,
    relevance,
    source_type,
    stance,
    content_hash,
  } = evidence;

  const displayExcerpt = excerpt || snippet || 'No excerpt available from source.';
  const displayPublisher = publisher || (url ? new URL(url).hostname.replace('www.', '') : null);

  // Stance styling
  const stanceConfig = {
    supports: {
      label: 'Supports Claim',
      icon: CheckCircle2,
      style: 'text-verdict-true border-verdict-true/40 bg-verdict-true/10',
    },
    refutes: {
      label: 'Refutes Claim',
      icon: XCircle,
      style: 'text-verdict-false border-verdict-false/40 bg-verdict-false/10',
    },
    neutral: {
      label: 'Neutral Context',
      icon: MinusCircle,
      style: 'text-text-secondary border-border-default bg-background-card',
    },
    unrelated: {
      label: 'Unrelated',
      icon: MinusCircle,
      style: 'text-text-muted border-border-dim bg-background-card/50',
    },
  };

  const currentStance = stanceConfig[stance?.toLowerCase()] || null;

  // Source Type formatting
  const sourceTypeLabels = {
    official: 'Official Source',
    institutional: 'Academic / Institution',
    news: 'News Outlet',
    encyclopedia: 'Reference / Wiki',
    general: 'General Web',
  };

  const formattedDate = published_at
    ? new Date(published_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
    : null;

  return (
    <div className="p-5 bg-background-secondary rounded-xl border border-border-dim hover:border-border-emphasis transition-all duration-200 flex flex-col gap-3 h-full shadow-sm">
      {/* Top Header: Stance & Source Category */}
      <div className="flex items-center justify-between gap-2 flex-wrap text-xs">
        <div className="flex items-center gap-2">
          {currentStance && (
            <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border text-xs font-semibold ${currentStance.style}`}>
              <currentStance.icon className="h-3 w-3" />
              {currentStance.label}
            </span>
          )}
          {source_type && (
            <span className="text-[11px] px-2 py-0.5 rounded bg-background-card border border-border-default text-text-secondary font-medium">
              {sourceTypeLabels[source_type.toLowerCase()] || source_type}
            </span>
          )}
        </div>

        {relevance !== undefined && relevance > 0 && (
          <span className="text-[11px] text-text-muted font-medium">
            Relevance: <strong className="text-text-primary">{(relevance * 100).toFixed(0)}%</strong>
          </span>
        )}
      </div>

      {/* Title */}
      <h4 className="text-sm md:text-base font-semibold text-text-primary line-clamp-2">
        {title || 'Untitled Document'}
      </h4>

      {/* Publisher & Metadata */}
      {(displayPublisher || formattedDate) && (
        <div className="flex items-center gap-2 text-xs text-text-muted">
          {displayPublisher && <span className="font-medium text-text-secondary">{displayPublisher}</span>}
          {displayPublisher && formattedDate && <span>•</span>}
          {formattedDate && <span>{formattedDate}</span>}
        </div>
      )}

      {/* Excerpt Quote */}
      <div className="p-3 bg-background-card/80 rounded-lg border-l-2 border-accent-blue/60 text-xs text-text-secondary leading-relaxed line-clamp-4 italic flex-1">
        "{displayExcerpt}"
      </div>

      {/* Footer: Content Hash and Source Link */}
      <div className="flex items-center justify-between pt-3 mt-2 border-t border-border-dim text-xs">
        {content_hash ? (
          <span
            className="inline-flex items-center gap-1 text-[10px] text-text-muted font-mono"
            title={`SHA-256 Snapshot: ${content_hash}`}
          >
            <Hash className="h-3 w-3" />
            {content_hash.slice(0, 10)}...
          </span>
        ) : (
          <span />
        )}

        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 font-bold text-accent-blue hover:text-accent-blue/80 transition-colors"
          >
            Read Source <ExternalLink className="h-3.5 w-3.5" />
          </a>
        ) : (
          <span className="inline-flex items-center gap-1 text-text-muted">
            <LinkIcon className="h-3.5 w-3.5" /> No link
          </span>
        )}
      </div>
    </div>
  );
};
