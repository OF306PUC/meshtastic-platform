"""The two programs run from a clone, with nothing installed but requirements.txt.

They are executed as a user would, as subprocesses from an UNRELATED working
directory: Python puts the script's own directory first on the import path, so
the packages beside it are found without installation or sys.path tricks.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from meshtastic_platform import registry
from tests.test_registry import field_registry, write_deployment

ROOT = Path(__file__).resolve().parents[1]


def run(*args, deployments=None):
    env = {k: v for k, v in os.environ.items()
           if k not in ("MESH_DEPLOYMENT", "MESH_DEPLOYMENTS_DIR", "PYTHONPATH")}
    if deployments:
        env["MESH_DEPLOYMENTS_DIR"] = deployments
    with tempfile.TemporaryDirectory() as elsewhere:
        return subprocess.run([sys.executable, *args], cwd=elsewhere, env=env,
                              capture_output=True, text=True, timeout=120)


class TestConfigureScript(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        write_deployment(self.tmp.name, field_registry())          # deployment "t"

    def test_every_deployment_in_the_repo_validates(self):
        r = run(str(ROOT / "configure.py"), "validate", "--all", "--quiet")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for name in registry.available():
            self.assertIn(f"✓ {name}", r.stdout)

    def test_no_deployment_no_default(self):
        r = run(str(ROOT / "configure.py"), "show")
        self.assertEqual(r.returncode, 2)
        self.assertIn("no default", r.stdout)

    def test_provision_dry_run_prints_the_plan(self):
        r = run(str(ROOT / "configure.py"), "provision", "-d", "t", "--node", "N3", "--dry-run",
                deployments=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("--set lora.tx_power 22", r.stdout)
        self.assertIn("--set lora.channel_num 45", r.stdout)


class TestReceiverScript(unittest.TestCase):
    def test_help(self):
        r = run(str(ROOT / "receiver.py"), "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--csv", r.stdout)

    def test_recording_requires_an_operator(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_deployment(tmp, field_registry())
            r = run(str(ROOT / "receiver.py"), "--port", "/dev/null", "-d", "t", "--csv", "out",
                    deployments=tmp)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--operator is required", r.stdout)


if __name__ == "__main__":
    unittest.main()
