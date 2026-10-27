"""The repository's hard rules, checked by reading the source code.

These tests do not run the code: they read the .py files of the two packages
and the two scripts, line by line, and fail on any line that breaks a rule,
naming the file and line. CI runs them on every push.

1. The application lives only in deployments/*.yaml. The code must work the
   same for any mesh, so no deployment, channel, key variable, node label or
   project name may appear in it. The list of forbidden names is read from
   the deployment files themselves (so a new deployment extends it with no
   edit here), plus the few project names no deployment field carries.
2. The code never depends on, or mentions, the infrastructure of whatever
   consumes its data downstream (broker, database, collector, containers).
3. No sys.path manipulation: the scripts at the repository root import the
   packages beside them.
"""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("meshtastic_platform", "channel_study")
SCRIPTS = ("configure.py", "receiver.py")

# Names of the application that no deployment field carries.
PROJECT_NAMES = ("sasipa", "rapa nui", "rapa-nui", "san joaquin", "san joaquín",
                 "vaitea", "subtel", "cps-rtc")
DOWNSTREAM = ("mqtt", "influx", "telegraf", "paho", "docker")


def sources():
    for pkg in PACKAGES:
        yield from sorted((ROOT / pkg).rglob("*.py"))
    for script in SCRIPTS:
        yield ROOT / script


def application_names() -> set[str]:
    """Every name a deployment file gives to its mesh, lower-cased."""
    names = {n.lower() for n in PROJECT_NAMES}
    for path in (ROOT / "deployments").glob("*.yaml"):
        if path.stem.startswith("_"):              # the template
            continue
        data = yaml.safe_load(path.read_text())
        names.add(data["meta"]["deployment"].lower())
        for ch in data["radio"]["channels"]:
            names.update({ch["name"].lower(), ch["psk_env"].lower()})
        for n in data["nodes"]:
            if n.get("label"):
                names.add(str(n["label"]).lower())
    return names


def words(names) -> re.Pattern:
    """Whole words only: 'node-1' must not match inside 'node-10' or 'my-node-1'."""
    alternatives = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![\w-])(?:{alternatives})(?![\w-])", re.IGNORECASE)


def hits(pattern: re.Pattern) -> list[str]:
    return [f"{p.relative_to(ROOT)}:{i}: {line.strip()}"
            for p in sources()
            for i, line in enumerate(p.read_text().splitlines(), 1)
            if pattern.search(line)]


class TestHardRules(unittest.TestCase):
    def test_the_application_lives_only_in_deployments(self):
        self.assertEqual(hits(words(application_names())), [],
                         "move these names to deployments/*.yaml")

    def test_no_downstream_infrastructure(self):
        self.assertEqual(hits(re.compile("|".join(DOWNSTREAM), re.IGNORECASE)), [])

    def test_no_sys_path_hacks(self):
        files = list(sources()) + sorted((ROOT / "tests").rglob("*.py"))
        found = [str(p.relative_to(ROOT)) for p in files
                 if "sys.path.insert" in p.read_text() and p != Path(__file__).resolve()]
        self.assertEqual(found, [])

    def test_the_word_match_is_exact(self):
        pattern = words({"node-1", "chprimary"})
        self.assertTrue(pattern.search('label = "node-1"'))
        self.assertTrue(pattern.search("name: chPrimary"))
        self.assertFalse(pattern.search("node-10"))
        self.assertFalse(pattern.search("my-node-1"))


if __name__ == "__main__":
    unittest.main()
