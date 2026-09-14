"""Run and reliably clean up a stack owned by this CI process."""

import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    stack = subprocess.Popen(
        [sys.executable, "scripts/run_stack.py", "--no-ui"], cwd=ROOT
    )
    try:
        subprocess.run(
            [sys.executable, "scripts/verify_stack.py"], cwd=ROOT, check=True
        )
        subprocess.run(
            [sys.executable, "scripts/verify_recovery.py"], cwd=ROOT, check=True
        )
    finally:
        stack.send_signal(signal.SIGINT)
        try:
            stack.wait(timeout=45)
        except subprocess.TimeoutExpired:
            stack.kill()
            stack.wait()


if __name__ == "__main__":
    main()
