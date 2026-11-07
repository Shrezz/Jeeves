"""One private stdin/stdout request from Express; no HTTP port, credentials, or paid calls."""
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from uuid import UUID

from filelock import FileLock

from .local_index import LocalPolicyIndex


def main():
    request = json.load(sys.stdin)
    owner, policy = request["owner"], UUID(request["policy"])
    directory = Path(os.environ["LOCAL_RAG_DATA_DIR"])
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Uploads, dashboard searches, and graph workers share one embedded Chroma writer.
    with FileLock(directory / "worker.lock", timeout=45), redirect_stdout(sys.stderr):
        index = LocalPolicyIndex(directory)
        if request["operation"] == "index":
            result = {"count": index.index(owner, policy, Path(request["pdf"]))}
        elif request["operation"] == "search":
            result = {"passages": index.search(owner, policy, request["question"], for_chat=request.get("forChat", False))}
        else:
            raise ValueError("Unknown operation")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
