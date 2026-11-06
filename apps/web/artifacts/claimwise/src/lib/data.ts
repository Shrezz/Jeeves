export const user = { name: 'Maya Okafor', email: 'maya.okafor@example.test', initials: 'MO' };

export const policy = {
  label: 'Okafor home — HO-3',
  carrier: 'Harborline Mutual (fictional)',
  number: 'HLM-HO3-448120-S',
  term: 'Mar 14, 2024 – Mar 14, 2025',
  deductible: '$1,250',
  dwelling: '$412,000',
  personal: '$206,000',
  lossOfUse: '$82,400',
  waterBackup: '$10,000 endorsement',
};

export const claims = [
  {
    id: 'c1',
    title: 'Kitchen ceiling leak — upstairs supply line',
    status: 'Preparing package',
    tone: 'pending' as const,
    latest: 'Added plumber invoice and two ceiling photos.',
    updated: 'Today, 9:42 AM',
    expenses: '$4,386.40',
  },
  {
    id: 'c2',
    title: 'Basement sump overflow',
    status: 'Gathering evidence',
    tone: 'info' as const,
    latest: 'Asked whether water backup endorsement applies.',
    updated: 'Oct 2, 4:15 PM',
    expenses: '$612.75',
  },
  {
    id: 'c3',
    title: 'Fence panel wind damage',
    status: 'Resolved without filing',
    tone: 'ok' as const,
    latest: 'Repair cost $780.00 was below deductible.',
    updated: 'Aug 19, 11:03 AM',
    expenses: '$780.00',
  },
];

export const expenses = [
  { item: 'Emergency plumber — Delgado Plumbing', amount: '$486.40' },
  { item: 'Drywall removal & drying (3 days)', amount: '$1,940.00' },
  { item: 'Ceiling repaint estimate', amount: '$1,210.00' },
  { item: 'Hotel, 2 nights (loss of use)', amount: '$750.00' },
];

export const evidence = [
  { name: 'ceiling-stain-0930.jpg', kind: 'Photo', note: 'Kitchen ceiling, morning of discovery' },
  { name: 'ceiling-opened-1001.jpg', kind: 'Photo', note: 'After drywall removal' },
  { name: 'delgado-invoice-2291.pdf', kind: 'Invoice', note: 'Supply line replaced, $486.40' },
  { name: 'drying-estimate.pdf', kind: 'Estimate', note: 'Restoration co. quote' },
];
