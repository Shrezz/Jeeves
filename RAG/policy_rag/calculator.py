"""
calculator.py
=============
Deterministic payment arithmetic (Decision D7).

LLMs are good at deciding WHICH rule applies but unreliable at arithmetic.
The model reports the inputs (loss value, deductible, limits) per payment
line; this module applies the policy rule and compares the result with the
model's own figure.

Rule per line:  payable = min( max(0, loss_value - deductible), special_limit, coverage_limit )
Total        :  sum of lines
"""
from typing import Optional, Tuple

from .contracts import CoverageAnswer, PaymentLine
from .tracing import trace_log, traced

TOLERANCE = 1.0      # dollars; differences below this count as a match


def line_amount(line: PaymentLine) -> float:
    amount = max(0.0, line.loss_value - (line.deductible or 0.0))
    for cap in (line.special_limit, line.coverage_limit):
        if cap is not None:
            amount = min(amount, cap)
    return round(amount, 2)


@traced
def compute_amount(answer: CoverageAnswer) -> Tuple[Optional[float], str]:
    """Return (amount_payable, amount_check)."""
    if answer.covered in ("N/A", "Not addressed"):
        trace_log("amount_payable", None)
        return None, "n/a"
    if answer.covered == "No" or not answer.payment_lines:
        amount = 0.0
    else:
        amount = round(sum(line_amount(l) for l in answer.payment_lines), 2)

    if answer.llm_amount is None:
        check = "n/a"
    else:
        check = "match" if abs(answer.llm_amount - amount) < TOLERANCE else "mismatch"
    trace_log("lines", [{**l.model_dump(), "line_payable": line_amount(l)} for l in answer.payment_lines])
    trace_log("amount_payable", amount)
    trace_log("llm_amount", answer.llm_amount)
    trace_log("amount_check", check)
    return amount, check
