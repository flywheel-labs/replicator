import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "replicator" / "scripts"))

import replicator  # noqa: E402


class ReplicatorTests(unittest.TestCase):
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
        self.assertIn("Recreate this credential manually", report)


if __name__ == "__main__":
    unittest.main()

