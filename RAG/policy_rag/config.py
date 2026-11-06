"""
config.py
=========
Single place for every tunable setting. Nothing else in the package should
hard-code paths, model names or retrieval numbers.

Values marked "TUNE" are starting points (see DECISIONS_v1.md). Change them
only after running the evaluation harness (policy_rag/evaluation.py).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = the folder that contains the policy_rag package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load OPENAI_API_KEY (and optional overrides) from <project root>/.env if present.
# Variables already set in the shell take priority over the .env file.
load_dotenv(PROJECT_ROOT / ".env", override=False)

# ---------------------------------------------------------------------------
# Locations (hard-coded for now, per requirement)
# ---------------------------------------------------------------------------
# The front-end (parent module) saves uploaded policy PDFs into this folder
# and then passes only the file name to ingest_policy().
UPLOAD_DIR = Path(os.getenv("POLICY_RAG_UPLOAD_DIR", PROJECT_ROOT / "policy_documents"))

# Chroma persists its data here (survives restarts).
CHROMA_DIR = Path(os.getenv("POLICY_RAG_CHROMA_DIR", PROJECT_ROOT / "chroma_store"))
CHROMA_COLLECTION = "policy_chunks_v2"       # one collection, isolated by metadata filters
CHROMA_DISTANCE = "cosine"                   # distances in logs: 0 = identical, 2 = opposite

# ---------------------------------------------------------------------------
# Models (Decision D1)
# ---------------------------------------------------------------------------
# OPENAI_API_KEY must be set in the environment or in <project root>/.env.
EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-4o-mini"
LLM_TEMPERATURE = 0.0                         # deterministic answers for testing

# ---------------------------------------------------------------------------
# PDF layout assumptions (Decision D3)
# ---------------------------------------------------------------------------
# Font sizes used by the policy template to mark headings.
H1_MIN_SIZE = 20.0       # 21pt section titles, e.g. "Section I - Exclusions"
H2_MIN_SIZE = 15.5       # 16pt coverage / endorsement titles
H3_MIN_SIZE = 12.5       # 13pt sub-headings (bold)
COVER_MIN_SIZE = 25.0    # 30pt cover title: treated as cover page text
# Running header and footer bands (points from top / bottom of page) to strip.
HEADER_BAND_PT = 45
FOOTER_BAND_PT = 50

# ---------------------------------------------------------------------------
# Chunking (Decision D3)
# ---------------------------------------------------------------------------
CHUNK_SIZE_CHARS = 1100       # TUNE: target max characters for prose chunks
CHUNK_OVERLAP_CHARS = 150     # TUNE: overlap applied only when a long section is split

# ---------------------------------------------------------------------------
# Retrieval (Decisions D4, D5, D6)
# ---------------------------------------------------------------------------
TOP_K = 6                     # TUNE: chunks passed to the LLM (excluding pinned declarations)
FETCH_K = 20                  # TUNE: MMR candidate pool
MMR_LAMBDA = 0.6              # 1.0 = pure relevance, 0.0 = pure diversity
HYBRID_ENABLED = False        # Start dense-only; switch on if evaluation shows keyword misses
HYBRID_DENSE_WEIGHT = 0.6     # Reciprocal-rank-fusion weights when hybrid is on
HYBRID_BM25_WEIGHT = 0.4
RRF_K = 60                    # standard RRF constant
PIN_DECLARATIONS = True       # always add the Declarations chunks of the policy (Decision D5)

# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
ANSWER_KEY_PATH = Path(os.getenv("POLICY_RAG_ANSWER_KEY", PROJECT_ROOT / "MCM_RAG_Answer_Key_v1.xlsx"))
EVAL_OUTPUT_DIR = PROJECT_ROOT / "eval_results"
EVAL_USER_ID = "eval-harness"  # user_id used when the harness ingests test policies

# ---------------------------------------------------------------------------
# Trace logging (Decision D14)
# ---------------------------------------------------------------------------
LOG_DIR = Path(os.getenv("POLICY_RAG_LOG_DIR", PROJECT_ROOT / "logs"))
TRACE_ENABLED = os.getenv("POLICY_RAG_TRACE", "1") != "0"   # set POLICY_RAG_TRACE=0 to switch off
TRACE_CHUNK_TEXT_CHARS = None    # None = log full chunk text; or e.g. 300 to truncate
TRACE_FULL_PROMPT = True         # log the exact messages sent to the LLM
