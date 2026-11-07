import { useId } from 'react';
import type { Claim, ManualClaimStatus } from '@workspace/api-client-react';
import { claimStatusLabel, MANUAL_CLAIM_STATUS_VALUES } from '@workspace/domain';

export type StatusNotice = { kind: 'success' | 'error'; text: string };

type Props = {
  current: Claim['status'];
  open: boolean;
  selected: ManualClaimStatus | '';
  note: string;
  busy: boolean;
  waitFor: string;
  notice: StatusNotice | null;
  onOpen: () => void;
  onCancel: () => void;
  onSelect: (status: ManualClaimStatus | '') => void;
  onNote: (value: string) => void;
  onSave: (status: ManualClaimStatus) => void;
};

const button = 'min-h-10 rounded-lg px-3 py-2 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50';
const field = 'mt-1.5 w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-ring';

export function ClaimStatusCard({ current, open, selected, note, busy, waitFor, notice, onOpen, onCancel, onSelect, onNote, onSave }: Props) {
  const id = useId();
  return (
    <section aria-label="Claim details" className="rounded-2xl border border-card-border bg-card p-5">
      <h2 className="font-display text-xl">Claim details</h2>
      <dl className="my-4"><dt className="text-xs font-semibold text-muted-foreground">Current status</dt>
        <dd className="mt-1 inline-block rounded-full bg-secondary px-3 py-1 text-sm font-semibold text-secondary-foreground">{claimStatusLabel(current)}</dd>
      </dl>
      {!open ? (
        <button type="button" data-testid="button-update-status" className={`${button} border border-input text-primary hover:bg-secondary`} onClick={onOpen}>Update status</button>
      ) : (
        <form className="space-y-3 border-t border-card-border pt-4" onSubmit={(event) => { event.preventDefault(); if (selected && !busy && !waitFor) onSave(selected); }}>
          <fieldset disabled={busy} className="space-y-3">
            <div><label htmlFor={id + '-status'} className="text-sm font-semibold">New status</label>
              <select autoFocus required id={id + '-status'} value={selected} className={field} onChange={(event) => onSelect(event.target.value as ManualClaimStatus | '')}>
                <option value="">Choose a status</option>
                {MANUAL_CLAIM_STATUS_VALUES.map((status) => <option key={status} value={status}>{claimStatusLabel(status)}</option>)}
              </select>
            </div>
            <div><label htmlFor={id + '-note'} className="text-sm font-semibold">Note <span className="font-normal text-muted-foreground">(optional)</span></label>
              <textarea id={id + '-note'} value={note} rows={2} maxLength={12000} className={field} onChange={(event) => onNote(event.target.value)} />
            </div>
            {waitFor && <p className="text-xs text-muted-foreground">{waitFor}</p>}
            <div className="flex flex-wrap gap-2">
              <button type="submit" disabled={!selected || !!waitFor} className={`${button} bg-primary text-primary-foreground hover:bg-primary/90`}>{busy ? 'Saving…' : 'Save status'}</button>
              <button type="button" className={`${button} border border-input hover:bg-secondary`} onClick={onCancel}>Cancel</button>
            </div>
          </fieldset>
        </form>
      )}
      {notice && <p role={notice.kind === 'error' ? 'alert' : 'status'} className={`mt-3 text-sm ${notice.kind === 'error' ? 'text-destructive' : 'text-primary'}`}>{notice.text}</p>}
    </section>
  );
}
