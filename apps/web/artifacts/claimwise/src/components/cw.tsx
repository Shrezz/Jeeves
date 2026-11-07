import type { ReactNode, ButtonHTMLAttributes } from 'react';
import { AlertTriangle, CheckCircle2, Clock, CircleDot, Info, XCircle } from 'lucide-react';

export function cx(...c: (string | false | undefined | null)[]) {
  return c.filter(Boolean).join(' ');
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'outline' | 'ghost' | 'amber' };
export function Btn({ variant = 'primary', className, ...p }: BtnProps) {
  const v = {
    primary: 'bg-primary text-primary-foreground hover:bg-[hsl(178_64%_22%)] shadow-[0_1px_0_hsl(178_64%_18%)]',
    outline: 'border border-input bg-card text-foreground hover:border-primary hover:text-primary',
    ghost: 'text-muted-foreground hover:bg-secondary hover:text-secondary-foreground',
    amber: 'border border-[hsl(38_70%_60%)] bg-accent text-accent-foreground hover:bg-[hsl(38_92%_86%)]',
  }[variant];
  return (
    <button
      type="button"
      {...p}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-[background-color,border-color,color,transform] duration-150 active:translate-y-px disabled:opacity-50 disabled:cursor-not-allowed',
        v,
        className,
      )}
    />
  );
}

export type Tone = 'ok' | 'pending' | 'error' | 'info' | 'neutral';
const toneMap: Record<Tone, { cls: string; Icon: typeof Info }> = {
  ok: { cls: 'bg-secondary text-secondary-foreground border-[hsl(178_40%_75%)]', Icon: CheckCircle2 },
  pending: { cls: 'bg-accent text-accent-foreground border-[hsl(38_70%_65%)]', Icon: Clock },
  error: { cls: 'bg-[hsl(4_70%_95%)] text-[hsl(4_66%_32%)] border-[hsl(4_60%_78%)]', Icon: XCircle },
  info: { cls: 'bg-[hsl(200_40%_94%)] text-[hsl(200_50%_25%)] border-[hsl(200_30%_80%)]', Icon: Info },
  neutral: { cls: 'bg-muted text-muted-foreground border-border', Icon: CircleDot },
};

export function Status({ tone, children, testId }: { tone: Tone; children: ReactNode; testId?: string }) {
  const { cls, Icon } = toneMap[tone];
  return (
    <span data-testid={testId} className={cx('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold', cls)}>
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {children}
    </span>
  );
}

export function Notice({ tone, title, children }: { tone: Tone; title: string; children?: ReactNode }) {
  const { cls } = toneMap[tone];
  const Icon = tone === 'error' ? AlertTriangle : toneMap[tone].Icon;
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={cx('flex gap-3 rounded-xl border p-3.5 text-sm', cls)}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>
        <p className="font-semibold">{title}</p>
        {children && <div className="mt-0.5 opacity-90">{children}</div>}
      </div>
    </div>
  );
}

export function Panel({ title, action, children, className }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx('rounded-2xl border border-card-border bg-card p-5 shadow-[0_1px_2px_hsl(192_30%_12%/0.04)]', className)}>
      {(title || action) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-semibold">{label}</label>
      {children}
      {hint && !error && <p id={`${id}-hint`} className="text-xs text-muted-foreground">{hint}</p>}
      {error && (
        <p id={`${id}-err`} className="flex items-center gap-1.5 text-xs font-semibold text-destructive">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden /> Error: {error}
        </p>
      )}
    </div>
  );
}

export const inputCls =
  'w-full rounded-lg border border-input bg-[hsl(40_40%_99%)] px-3 py-2 text-sm placeholder:text-muted-foreground/70 transition-colors hover:border-[hsl(178_30%_55%)] focus:border-primary focus:outline-none focus-visible:outline-2 aria-[invalid=true]:border-destructive aria-[invalid=true]:border-2';

export function Mark({ className }: { className?: string }) {
  return <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" className={className} />;
}
