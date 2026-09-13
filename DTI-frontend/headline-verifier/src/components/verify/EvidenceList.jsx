import { useState, useMemo } from 'react';
import { EvidenceCard } from './EvidenceCard';
import { BookOpen, Filter, ArrowDownWideNarrow, HelpCircle, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react';

export const EvidenceList = ({ sources = [], evidence = [], limitations = [] }) => {
  const [filterStance, setFilterStance] = useState('All');
  const [sortBy, setSortBy] = useState('relevance');
  const [showLimitations, setShowLimitations] = useState(false);

  // Combine items, preferring rich evidence citations
  const items = useMemo(() => {
    if (evidence && evidence.length > 0) return evidence;
    if (sources && sources.length > 0) return sources;
    return [];
  }, [evidence, sources]);

  const uniqueStances = useMemo(() => {
    const stances = items.map((s) => s.stance).filter(Boolean);
    return ['All', ...new Set(stances.map((st) => st.charAt(0).toUpperCase() + st.slice(1)))];
  }, [items]);

  const filteredAndSorted = useMemo(() => {
    let result = [...items];

    if (filterStance !== 'All') {
      result = result.filter(
        (s) => s.stance && s.stance.toLowerCase() === filterStance.toLowerCase()
      );
    }

    return result.sort((a, b) => {
      if (sortBy === 'relevance') {
        const scoreA = a.relevance ?? (a.credibility === 'High' ? 0.9 : a.credibility === 'Medium' ? 0.6 : 0.3);
        const scoreB = b.relevance ?? (b.credibility === 'High' ? 0.9 : b.credibility === 'Medium' ? 0.6 : 0.3);
        return scoreB - scoreA;
      }
      return (a.title || '').localeCompare(b.title || '');
    });
  }, [items, sortBy, filterStance]);

  if (!items || items.length === 0) {
    return (
      <div className="p-8 text-center bg-background-card rounded-xl border border-border-default border-dashed animate-in fade-in duration-500 delay-300 fill-mode-both">
        <BookOpen className="h-8 w-8 text-text-muted mx-auto mb-3 opacity-50" />
        <p className="text-text-secondary text-sm">No external citations retrieved for this claim.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 animate-in fade-in duration-500 delay-300 fill-mode-both">
      {/* Header with Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-bold text-text-primary flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-accent-blue" />
            Evidence Citations ({items.length})
          </h3>

          {limitations && limitations.length > 0 && (
            <button
              onClick={() => setShowLimitations(!showLimitations)}
              className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-background-secondary border border-border-default text-text-secondary hover:text-text-primary transition-colors cursor-pointer"
            >
              <HelpCircle className="h-3.5 w-3.5 text-accent-blue" />
              Why this result?
              {showLimitations ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
          )}
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {uniqueStances.length > 1 && (
            <div className="relative flex items-center">
              <Filter className="h-3.5 w-3.5 text-text-muted absolute left-2.5 pointer-events-none" />
              <select
                value={filterStance}
                onChange={(e) => setFilterStance(e.target.value)}
                className="pl-8 pr-8 py-1.5 bg-background-secondary border border-border-default rounded-lg text-xs font-medium text-text-primary focus:outline-none focus:border-accent-blue cursor-pointer"
              >
                {uniqueStances.map((item) => (
                  <option key={item} value={item}>Stance: {item}</option>
                ))}
              </select>
            </div>
          )}

          <div className="relative flex items-center">
            <ArrowDownWideNarrow className="h-3.5 w-3.5 text-text-muted absolute left-2.5 pointer-events-none" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="pl-8 pr-8 py-1.5 bg-background-secondary border border-border-default rounded-lg text-xs font-medium text-text-primary focus:outline-none focus:border-accent-blue cursor-pointer"
            >
              <option value="relevance">Highest Relevance</option>
              <option value="title">Title A-Z</option>
            </select>
          </div>
        </div>
      </div>

      {/* Collapsible "Why this result? / Methodological Limitations" Drawer */}
      {showLimitations && limitations && limitations.length > 0 && (
        <div className="p-4 rounded-xl bg-background-secondary/70 border border-accent-blue/30 text-xs text-text-secondary animate-in fade-in duration-300">
          <div className="flex items-center gap-2 mb-2 font-semibold text-text-primary">
            <AlertCircle className="h-4 w-4 text-accent-blue" />
            Methodological Notes & Limitations
          </div>
          <ul className="list-disc list-inside space-y-1.5 leading-relaxed pl-1">
            {limitations.map((lim, idx) => (
              <li key={idx} className="text-text-secondary">{lim}</li>
            ))}
          </ul>
          <div className="mt-3 pt-2 border-t border-border-default/50 text-[11px] text-text-muted">
            The verdict is weighted by source authority tiers (Official &gt; Institutional &gt; News Media &gt; Reference &gt; Web) and penalized for source age through an exponential freshness decay model.
          </div>
        </div>
      )}

      {/* Citations Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {filteredAndSorted.map((item, idx) => (
          <EvidenceCard key={idx} evidence={item} />
        ))}
      </div>

      {filteredAndSorted.length === 0 && (
        <div className="p-8 text-center bg-background-secondary rounded-xl border border-border-dim col-span-full">
          <p className="text-text-secondary text-sm">No evidence matches the selected filter.</p>
        </div>
      )}
    </div>
  );
};
