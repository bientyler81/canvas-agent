"""Command line, mainly for local testing.

    python -m canvas_digest digest                      # build (and send, unless DRY_RUN) the morning digest
    python -m canvas_digest ask "when is the bio lab due?"  # ask the agent a question, print the answer
"""

import sys

from .config import Config
from .jobs import ask, run_digest


def main() -> None:
    cfg = Config.from_env()
    command = sys.argv[1] if len(sys.argv) > 1 else "digest"
    if command == "digest":
        print("----- message -----\n" + run_digest(cfg) + "\n-------------------")
    elif command == "ask" and len(sys.argv) > 2:
        print(ask(cfg, " ".join(sys.argv[2:])))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
