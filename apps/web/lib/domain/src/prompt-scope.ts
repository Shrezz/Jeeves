/** Model-free, conservative check; aligned with the Python agent's prompt_scope.py. */
export const OUT_OF_SCOPE_MESSAGE = "This question does not appear relevant to insurance claims, policies, or damage. Please ask about your claim or insurance coverage.";

const OFF_TOPIC = /\b(?:weather forecast|weather (?:today|tomorrow|this week|right now)|(?:how(?:'s| is)|what(?:'s| is)) the weather|forecast the weather|(?:what|how|tell|give|check|show|find)\b.{0,40}\bweather|(?:tell|share|write) (?:me |us )?(?:a )?joke|write (?:me )?(?:a |an )?(?:poem|song|story|code)|(?:recipe|sports|football|soccer|cricket|movies?|stock price|horoscope|capital of|solve (?:this |a )?math))\b/;
const IN_SCOPE = /\b(?:insur(?:ance|er|ers|ed)|claim(?:s|ant)?|polic(?:y|ies)|cover(?:age|ed)?|deductible|premium|adjuster|exclusion|endorsement|reimburse(?:ment)?|liabilit(?:y|ies)|payout|settlement|declaration|loss|damage(?:d|s)?|repair(?:s|ed|ing)?|replac(?:e|ement)|incident|accident|storm|wind|windstorm|windblown|windborne|flood|fire|hail|roof|window|pipe|leak|theft|stolen|broken|breakage|receipt|invoice|estimate|expense|cost|paid|payment|evidence|attachment|photograph|photo|pictures?|document|status|submit(?:ted|ting)?|fixed|homeowner|contractor|property|dwelling)\b/;
const FOLLOWUP = /^(?:yes|no|unknown|not sure|none|n\/?a|pending|complete|completed|not (?:yet|applicable|completed)|i (?:don't|do not) know|\$?\d[\d,.]*(?: dollars?)?)[.!?\s]*$/;

export function promptInScope(text: string, options: { followup?: boolean } = {}): boolean {
  const normalized = text.normalize("NFKC").toLowerCase().replaceAll("\u2019", "'").trim();
  if (!normalized || OFF_TOPIC.test(normalized)) return false;
  return IN_SCOPE.test(normalized) || (!!options.followup && FOLLOWUP.test(normalized));
}

export function includePromptInHistory(text: string, reply: string | null | undefined): boolean {
  return reply !== OUT_OF_SCOPE_MESSAGE && (!text || promptInScope(text, { followup: true }));
}
