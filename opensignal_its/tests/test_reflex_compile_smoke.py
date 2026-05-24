import os
import subprocess
import sys
import unittest
from pathlib import Path


class ReflexCompileSmokeTests(unittest.TestCase):
    def test_reflex_compile_dry_succeeds(self):
        repo_root = Path(__file__).resolve().parents[2]
        env = os.environ.copy()
        env.setdefault("OPENSIGNAL_ENV", "dev")

        completed = subprocess.run(
            [sys.executable, "-m", "reflex", "compile", "--dry", "--no-rich"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )

        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            self.fail(f"Reflex compile smoke failed with exit code {completed.returncode}.\n{output}")

        self.assertIn("App compiled successfully", output)


if __name__ == "__main__":
    unittest.main()