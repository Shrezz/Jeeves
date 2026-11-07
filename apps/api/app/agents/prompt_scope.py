"""A conservative, model-free scope check for claim assistant inputs.

This is a heuristic, not a semantic security boundary. Keep its behavior aligned
with the web server's prompt-scope.ts using the shared test cases.
"""

import re
import unicodedata

OUT_OF_SCOPE_MESSAGE = (
    "This question does not appear relevant to insurance claims, policies, or damage. "
    "Please ask about your claim or insurance coverage."
)

_OFF_TOPIC = re.compile(
    r"\b(?:weather forecast|weather (?:today|tomorrow|this week|right now)|"
    r"(?:how(?:'s| is)|what(?:'s| is)) the weather|forecast the weather|"
    r"(?:what|how|tell|give|check|show|find)\b.{0,40}\bweather|"
    r"(?:tell|share|write) (?:me |us )?(?:a )?joke|write (?:me )?(?:a |an )?(?:poem|song|story|code)|"
    r"(?:recipe|sports|football|soccer|cricket|movies?|stock price|horoscope|capital of|solve (?:this |a )?math))\b"
)
_IN_SCOPE = re.compile(
    r"\b(?:insur(?:ance|er|ers|ed)|claim(?:s|ant)?|polic(?:y|ies)|cover(?:age|ed)?|"
    r"deductible|premium|adjuster|exclusion|endorsement|reimburse(?:ment)?|"
    r"liabilit(?:y|ies)|payout|settlement|declaration|loss|damage(?:d|s)?|"
    r"repair(?:s|ed|ing)?|replac(?:e|ement)|incident|accident|storm|wind|windstorm|windblown|windborne|"
    r"flood|fire|hail|roof|window|pipe|leak|theft|stolen|broken|breakage|"
    r"receipt|invoice|estimate|expense|cost|paid|payment|evidence|attachment|"
    r"photograph|photo|pictures?|document|status|submit(?:ted|ting)?|fixed|"
    r"homeowner|contractor|property|dwelling)\b"
)
_FOLLOWUP = re.compile(
    r"^(?:yes|no|unknown|not sure|none|n/?a|pending|complete|completed|"
    r"not (?:yet|applicable|completed)|i (?:don't|do not) know|"
    r"\$?\d[\d,.]*(?: dollars?)?)[.!?\s]*$"
)


def in_scope(text: str, *, followup: bool = False) -> bool:
    text = unicodedata.normalize("NFKC", text).lower().replace("\u2019", "'").strip()
    if not text or _OFF_TOPIC.search(text):
        return False
    return bool(_IN_SCOPE.search(text) or (followup and _FOLLOWUP.fullmatch(text)))


def include_in_history(text: str | None, reply: str | None) -> bool:
    return reply != OUT_OF_SCOPE_MESSAGE and (not text or in_scope(text, followup=True))


def scope_guard(state: dict) -> dict:
    request = state["request"]
    message_allowed = in_scope(request.message, followup=bool(request.claim_id)) or (
        request.explicit_route == "file_claim"
        and request.message.strip() == "Preparation requested."
    )
    allowed = message_allowed and (
        not request.web_search_query or in_scope(request.web_search_query)
    )
    if allowed:
        return {"scope_decision": "allowed"}
    return {
        "scope_decision": "out_of_scope",
        "phase": "answer_ready",
        "chat_reply": {"content": OUT_OF_SCOPE_MESSAGE, "sources": []},
    }
