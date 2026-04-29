import tempfile
import unittest
from pathlib import Path
from subprocess import run

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "replicator" / "scripts"))

import replicator  # noqa: E402


class ReplicatorTests(unittest.TestCase):
    def test_version_flag_reports_v0_2_0(self):
        script = Path(__file__).resolve().parents[1] / "replicator" / "scripts" / "replicator.py"
        result = run([sys.executable, str(script), "--version"], capture_output=True, text=True, check=True)

        self.assertEqual(result.stdout.strip(), "replicator 0.2.0")

    def test_secret_paths_are_not_portable(self):
        path = Path("/tmp/.claude/session-token.json")
        artifact_type = replicator.infer_artifact_type(path, replicator.PROVIDERS["claude"])
        classification, reason, target_notes, contains_secret = replicator.classify(path, artifact_type)

        self.assertEqual(artifact_type, "credential_reference")
        self.assertEqual(classification, "not_portable")
        self.assertTrue(contains_secret)
        self.assertIn("manually", target_notes)
        self.assertIn("credentials", reason)

    def test_mcp_configs_are_portable_with_edits(self):
        path = Path("/tmp/.codex/mcp/settings.json")
        artifact_type = replicator.infer_artifact_type(path, replicator.PROVIDERS["codex"])
        classification, _, target_notes, contains_secret = replicator.classify(path, artifact_type)

        self.assertEqual(artifact_type, "mcp_config")
        self.assertEqual(classification, "portable_with_edits")
        self.assertFalse(contains_secret)
        self.assertIn("verify", target_notes.lower())

    def test_report_itemizes_credentials_not_moved(self):
        artifact = replicator.Artifact(
            provider="claude",
            path="/tmp/.claude/oauth.json",
            artifact_type="credential_reference",
            classification="not_portable",
            reason="Path appears to contain credentials.",
            target_notes="Recreate this credential manually.",
            contains_secret_reference=True,
        )
        with tempfile.TemporaryDirectory() as temp:
            report_path = replicator.write_report(Path(temp), [artifact])
            report = report_path.read_text(encoding="utf-8")

        self.assertIn("No credentials", report)
        self.assertIn("Credential/manual auth items not moved: 1", report)
        self.assertIn("By Classification", report)
        self.assertIn("Recreate this credential manually", report)

    def test_fixture_inventory_covers_all_initial_providers_safely(self):
        root = Path(__file__).resolve().parent / "fixtures" / "home"
        options = replicator.ScanOptions(root_override=root)
        artifacts = []
        for provider in ("claude", "codex", "openclaw", "qwen", "kimi"):
            artifacts.extend(replicator.inventory_provider(replicator.PROVIDERS[provider], options))

        summary = replicator.summarize_artifacts(artifacts)

        self.assertEqual(set(summary["by_provider"]), {"claude", "codex", "openclaw", "qwen", "kimi"})
        self.assertGreaterEqual(summary["by_classification"].get("portable_with_edits", 0), 3)
        self.assertGreaterEqual(summary["credential_reference_count"], 1)
        self.assertFalse(any("ignored.tmp" in artifact.path for artifact in artifacts))

    def test_max_depth_limits_nested_artifacts(self):
        root = Path(__file__).resolve().parent / "fixtures" / "home"
        options = replicator.ScanOptions(root_override=root, max_depth=1)
        artifacts = replicator.inventory_provider(replicator.PROVIDERS["claude"], options)

        self.assertFalse(any("SKILL.md" in artifact.path for artifact in artifacts))

    def test_bundle_includes_summary_and_version(self):
        artifact = replicator.Artifact(
            provider="codex",
            path="/tmp/.codex/skills/demo/SKILL.md",
            artifact_type="skill_or_prompt",
            classification="portable_with_edits",
            reason="Skill/prompt instructions can usually be translated.",
            target_notes="Review instructions.",
            contains_secret_reference=False,
        )
        with tempfile.TemporaryDirectory() as temp:
            bundle_path = replicator.write_bundle(Path(temp), [artifact])
            bundle = __import__("json").loads(bundle_path.read_text(encoding="utf-8"))

        self.assertEqual(bundle["replicator_version"], "0.2.0")
        self.assertEqual(bundle["summary"]["by_classification"], {"portable_with_edits": 1})


if __name__ == "__main__":
    unittest.main()
