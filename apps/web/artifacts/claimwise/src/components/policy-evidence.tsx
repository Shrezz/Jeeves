import type { PolicyPassage } from '@workspace/api-client-react';

export function PolicyEvidence({sources, label}: {sources: PolicyPassage[]; label?: string}) {
  if (!sources.length) return null;
  return <details className="mt-3 border-t border-primary/20 pt-2 text-xs leading-5">
        <summary className="cursor-pointer font-semibold text-primary">Policy evidence{label && ` · ${label}`} · {Array.from(new Set(sources.map(s => s.page))).sort((a, b) => a - b).map(p => 'p. ' + p).join(', ')}</summary>
        <ul className="mt-2 space-y-2">{sources.map((s, i) => <li key={i} className="border-l-2 border-primary/40 pl-3"><p className="font-semibold">Page {s.page}{s.section && ' · ' + s.section}</p><blockquote>“{s.excerpt}”</blockquote></li>)}</ul>
      </details>;
}
