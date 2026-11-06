"""
policy_rag: RAG over home insurance policy PDFs.

Parent modules should import from policy_rag.api only. See the contract at
the top of api.py and the design decisions in DECISIONS_v1.md.
"""
from .api import *  # noqa: F401,F403
from .api import __all__  # noqa: F401
