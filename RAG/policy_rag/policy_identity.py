"""
policy_identity.py
==================
Reads identifying facts printed in the policy (policy number, form, insured)
and checks them against what the parent module sent (Decision D2).

The parent's values are the source of truth for WHO the user is; the PDF is
the source of truth for WHICH policy the file is. If the two policy numbers
disagree we refuse to ingest, so one user's identity can never be attached to
another person's policy.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from .errors import PolicyMismatchError
from .pdf_parser import Element, full_text
from .tracing import trace_log, traced

POLICY_NO_PATTERN = re.compile(r"\b[A-Z]{2,5}-HO\d-[A-Z]{2}-\d{5,7}\b")   # e.g. MCM-HO3-CA-100231
FORM_PATTERN = re.compile(r"\bHO-\d\b")


@dataclass
class PolicyIdentity:
    policy_number: Optional[str]
    form: Optional[str]
    insured_name: Optional[str]


def _declarations_value(elements: List[Element], label: str) -> Optional[str]:
    """Return the 'Details' cell of a Declarations table row whose 'Item' cell equals label."""
    for e in elements:
        if e.kind != "table":
            continue
        for row in e.rows[1:]:
            if len(row) >= 3 and row[1].strip().lower() == label.lower():
                return row[2].strip()
    return None


@traced
def read_identity(elements: List[Element]) -> PolicyIdentity:
    """Extract policy number, form and insured name from the parsed document."""
    text = full_text(elements)
    pn = _declarations_value(elements, "Policy Number")
    if not pn:
        match = POLICY_NO_PATTERN.search(text)
        pn = match.group(0) if match else None
    form_cell = _declarations_value(elements, "Policy Form") or text
    form = FORM_PATTERN.search(form_cell)
    identity = PolicyIdentity(policy_number=pn, form=form.group(0) if form else None,
                              insured_name=_declarations_value(elements, "Named Insured"))
    trace_log("identity", identity)
    return identity


@traced
def verify_policy_number(expected: str, identity: PolicyIdentity, file_name: str) -> None:
    """Raise PolicyMismatchError when the PDF does not belong to the expected policy."""
    found = identity.policy_number
    trace_log("expected", expected)
    trace_log("found_in_pdf", found)
    if not found or found.strip().upper() != expected.strip().upper():
        raise PolicyMismatchError(
            f"File '{file_name}' contains policy number '{found}', but the request was for '{expected}'.")
