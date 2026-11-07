import { useEffect, useState } from 'react';
import { Link } from 'wouter';
import { ArrowRight, BookOpen, CarFront, Check, ClipboardList, FileText, HeartPulse, House, LockKeyhole, PawPrint, ReceiptText, Umbrella } from 'lucide-react';
import { Mark, cx } from '@/components/cw';

const exampleSteps = ['Coverage', 'Estimate', 'Packet'] as const;
const insuranceCategories = [
  { name: 'Home', icon: House, available: true },
  { name: 'Health', icon: HeartPulse },
  { name: 'Pet', icon: PawPrint },
  { name: 'Vehicle', icon: CarFront },
  { name: 'Umbrella', icon: Umbrella },
];
const capabilities = [
  { icon: BookOpen, title: 'Find the clause', detail: 'Upload your policy PDF and ask about a loss in your own words. Jeeves points you to the wording and page behind its answer.' },
  { icon: ReceiptText, title: 'Understand the numbers', detail: 'See how the deductible affects a reported repair cost. A covered loss can still have an estimated payment of $0.' },
  { icon: ClipboardList, title: 'Prepare a claim packet', detail: 'Ask Jeeves to prepare a draft with your incident details, expenses, and policy evidence. Review it, request changes, or approve it.' },
];

function WindowSketch() {
  return <svg aria-hidden="true" viewBox="0 0 100 100" fill="none" className="h-20 w-20 shrink-0 text-[#e6efce] sm:h-24 sm:w-24">
    <g stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round">
      <path fill="#416662" d="M17 15h58v68H17z" /><path d="M22 20h48v58H22zM46 20v58M22 48h48M12 84h69v4H12z" />
      <path d="m55 26 4 8-5 4 7 4-1 6m-1-14 8-3m-8 3-7-1" />
      <path d="M73 28c8-1 14-6 17-13" strokeDasharray="3 4" />
    </g>
    <circle cx="82" cy="21" r="8" fill="#f6c987" stroke="#203f40" strokeWidth="1.6" />
    <path d="M76 16q7 1 9 12m-6-14q7 3 9 9" stroke="#875422" strokeWidth="1.1" />
  </svg>;
}

function ClaimExample() {
  const [step, setStep] = useState<(typeof exampleSteps)[number]>('Coverage');
  return (
    <aside aria-labelledby="example-heading" className="relative min-w-0 overflow-hidden rounded-3xl border border-[#c6d4c6] bg-[#fffefa] shadow-[0_20px_44px_-30px_#254b46]">
      <div className="flex items-center justify-between gap-3 border-b border-white/10 bg-[#214a47] px-5 py-5 text-white sm:px-7">
        <div>
          <p className="font-mono text-[11px] font-medium uppercase tracking-[.14em] text-[#d4e3c9]">Home insurance / Fictional example</p>
          <h2 id="example-heading" className="mt-2 font-display text-[2rem] leading-tight sm:text-4xl">The broken window</h2>
        </div>
        <WindowSketch />
      </div>
      <div className="p-5 sm:p-7">
        <p className="font-display text-xl leading-snug text-[#263c39]">“A baseball broke my front window. I paid $150 for the repair. Is it covered?”</p>
        <div role="group" aria-label="Explore the claim example" className="mt-5 grid grid-cols-3 gap-1 rounded-xl border border-[#d4ded1] bg-[#eff3eb] p-1">
          {exampleSteps.map(label => <button type="button" key={label} aria-pressed={step === label} aria-controls="example-result" onClick={() => setStep(label)}
            className={cx('min-h-10 rounded-lg px-1 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring', step === label ? 'bg-[#214a47] text-white' : 'text-[#39534d] hover:bg-white')}>{label}</button>)}
        </div>
        <div id="example-result" aria-live="polite" aria-atomic="true" className="mt-4 min-h-36 text-sm leading-6 text-[#42514b]">
          {step === 'Coverage' && <>
            <p className="font-semibold text-[#214a47]">The cause matters.</p>
            <blockquote className="my-2 border-l-[3px] border-[#b77a3a] pl-3">“Accidental impact by a sports ball, including a baseball, is covered unless another exclusion applies.”</blockquote>
            <p className="flex items-center gap-1.5 text-xs font-semibold text-[#47625a]"><BookOpen size={15} aria-hidden /> Sample policy · page 2, §2.2</p>
          </>}
          {step === 'Estimate' && <>
            <p className="flex items-baseline justify-between gap-2"><span className="font-semibold text-[#214a47]">Estimated payment</span><strong className="font-display text-3xl text-[#214a47]">$0</strong></p>
            <p className="my-2">Even if the full $150 repair is eligible, it falls below this policy’s $1,000 deductible.</p>
            <p className="flex items-center gap-1.5 text-xs font-semibold text-[#47625a]"><BookOpen size={15} aria-hidden /> Sample policy · page 3, §4</p>
          </>}
          {step === 'Packet' && <>
            <p className="font-semibold text-[#214a47]">Draft for homeowner review</p>
            <ul className="mt-2 space-y-1">
              <li className="flex items-start gap-2"><Check size={16} className="mt-1 shrink-0 text-primary" aria-hidden /> Incident and $150 reported repair</li>
              <li className="flex items-start gap-2"><Check size={16} className="mt-1 shrink-0 text-primary" aria-hidden /> Supporting clauses from pages 2 and 3</li>
              <li className="flex items-start gap-2"><FileText size={15} className="mt-1 shrink-0" aria-hidden /> Invoice still to attach</li>
            </ul>
          </>}
        </div>
      </div>
    </aside>
  );
}

export default function Landing() {
  useEffect(() => { document.title = 'Jeeves — Insurance paperwork and claims'; }, []);
  return (
    <div className="min-h-[100dvh] bg-[#f8f7f0] text-[#1e3533]">
      <header className="border-b border-[#d6ded1]">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-5 py-4 sm:px-10">
          <span className="inline-flex items-center gap-2 text-lg font-bold tracking-tight"><Mark className="h-8 w-8" />Jeeves</span>
          <nav aria-label="Account" className="flex items-center gap-2 sm:gap-4">
            <Link href="/sign-in" data-testid="link-sign-in" className="rounded-lg px-2 py-2 text-sm font-semibold hover:underline">Sign in</Link>
            <Link href="/sign-up" data-testid="link-sign-up-header" className="rounded-lg border border-[#7c9488] px-3 py-2 text-sm font-semibold hover:bg-white">Create account</Link>
          </nav>
        </div>
      </header>
      <main>
        <section aria-labelledby="home-heading" className="overflow-hidden">
          <div className="mx-auto grid max-w-7xl items-center gap-9 px-5 py-10 sm:px-10 sm:py-14 lg:grid-cols-[1.03fr_1fr] lg:gap-16 lg:py-16">
            <div className="min-w-0">
              <p className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[.12em] text-[#426459]"><span aria-hidden className="h-2 w-2 rounded-full bg-[#ad6e35]" />Meet Jeeves · Your insurance assistant</p>
              <h1 id="home-heading" className="mt-5 max-w-[16ch] text-balance font-display text-[clamp(2.8rem,5.6vw,4.8rem)] leading-[1.02] tracking-[-.045em]">One assistant for <span className="text-[#276c5c]">paperwork and claims.</span></h1>
              <p className="mt-5 max-w-lg text-base leading-7 text-[#4f5f58] sm:text-lg sm:leading-8">Start with home insurance. Upload your policy and tell Jeeves what happened. See which clauses apply, what your deductible means, and what goes into a claim packet you can review.</p>
              <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-3">
                <Link href="/sign-up" data-testid="link-sign-up" className="inline-flex min-h-12 items-center gap-3 rounded-xl bg-[#214a47] px-5 font-semibold text-white hover:bg-[#163b39]">Start with my home policy <ArrowRight size={18} aria-hidden /></Link>
                <a href="#how-jeeves-helps" className="rounded py-2 text-sm font-semibold underline decoration-[#a0b6a6] underline-offset-4 hover:decoration-current">How it works</a>
              </div>
            </div>
            <ClaimExample />
          </div>
        </section>

        <section aria-labelledby="categories-heading" className="border-t border-[#d6ded1] bg-[#eef2e9]">
          <div className="mx-auto max-w-7xl px-5 py-7 sm:px-10">
            <h2 id="categories-heading" className="font-display text-2xl">Insurance categories</h2>
            <ul className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
              {insuranceCategories.map(({name, icon: Icon, available}) => <li key={name} className={cx('flex items-center gap-3 rounded-xl border px-3 py-3', available ? 'border-[#98b7a3] bg-[#e0eddf]' : 'border-[#d2dbcd] bg-[#f8faf5]')}>
                <Icon size={21} strokeWidth={1.6} aria-hidden className={available ? 'text-[#235b47]' : 'text-[#56685c]'} />
                <div><p className="text-sm font-semibold">{name}</p><p className={cx('mt-0.5 text-xs', available ? 'font-semibold text-[#235b47]' : 'text-[#56645a]')}>{available ? 'Available now' : 'Coming soon'}</p></div>
              </li>)}
            </ul>
          </div>
        </section>

        <section id="how-jeeves-helps" aria-labelledby="steps-heading" className="scroll-mt-4 bg-[#193b39] text-[#f8f7ef]">
          <div className="mx-auto max-w-7xl px-5 py-10 sm:px-10 sm:py-12">
            <h2 id="steps-heading" className="font-display text-3xl tracking-tight sm:text-4xl">What Jeeves can do for you</h2>
            <ol className="mt-7 grid gap-6 md:grid-cols-3 md:gap-9">
              {capabilities.map(({icon: Icon, title, detail}, index) => <li key={title} className="border-t border-white/25 pt-4">
                <div className="flex items-center justify-between text-[#c1d9bc]"><span className="font-mono text-sm">0{index + 1}</span><Icon size={19} strokeWidth={1.6} aria-hidden /></div>
                <h3 className="mt-3 font-display text-2xl">{title}</h3>
                <p className="mt-2 max-w-md text-sm leading-6 text-[#d4e2d8]">{detail}</p>
              </li>)}
            </ol>
          </div>
        </section>
      </main>
      <footer className="mx-auto flex max-w-7xl flex-wrap justify-between gap-3 px-5 py-6 text-xs leading-5 text-[#52635b] sm:px-10">
        <span className="inline-flex items-center gap-2"><LockKeyhole size={14} aria-hidden /> Your policy stays in your private workspace.</span>
        <span>Your insurer makes the final coverage and payment decision.</span>
      </footer>
    </div>
  );
}
