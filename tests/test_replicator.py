import tempfile
import unittest
import importlib.util
from pathlib import Path
from subprocess import run

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from replicator import adapters, drafts, schema  # noqa: E402


def load_cli_module():
    script = REPO_ROOT / "replicator" / "scripts" / "replicator.py"
    spec = importlib.util.spec_from_file_location("replicator_cli", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


replicator_cli = load_cli_module()


class ReplicatorTests(unittest.TestCase):
    def test_version_flag_reports_v0_6_0(self):
        script = Path(__file__).resolve().parents[1] / "replicator" / "scripts" / "replicator.py"
        result = run([sys.executable, str(script), "--version"], capture_output=True, text=True, check=True)

        self.assertEqual(result.stdout.strip(), "replicator 0.6.0")

    def test_secret_paths_are_not_portable(self):
        path = Path("/tmp/.claude/session-token.json")
        artifact_type = adapters.infer_artifact_type(path, adapters.PROVIDERS["claude"])
        classification, reason, target_notes, contains_secret = adapters.classify(path, artifact_type)

        self.assertEqual(artifact_type, "credential_reference")
        self.assertEqual(classification, "not_portable")
        self.assertTrue(contains_secret)
        self.assertIn("manually", target_notes)
        self.assertIn("credentials", reason)

    def test_mcp_configs_are_portable_with_edits(self):
        path = Path("/tmp/.codex/mcp/settings.json")
        artifact_type = adapters.infer_artifact_type(path, adapters.PROVIDERS["codex"])
        classification, _, target_notes, contains_secret = adapters.classify(path, artifact_type)

        self.assertEqual(artifact_type, "mcp_config")
        self.assertEqual(classification, "portable_with_edits")
        self.assertFalse(contains_secret)
        self.assertIn("verify", target_notes.lower())

    def test_skill_named_mcp_builder_is_still_a_skill(self):
        path = Path("/tmp/.claude/skills/mcp-builder/SKILL.md")
        artifact_type = adapters.infer_artifact_type(path, adapters.PROVIDERS["claude"])

        self.assertEqual(artifact_type, "skill_or_prompt")

    def test_report_itemizes_credentials_not_moved(self):
        artifact = replicator_cli.Artifact(
            provider="claude",
            path="/tmp/.claude/oauth.json",
            artifact_type="credential_reference",
            classification="not_portable",
            reason="Path appears to contain credentials.",
            target_notes="Recreate this credential manually.",
            contains_secret_reference=True,
        )
        with tempfile.TemporaryDirectory() as temp:
            report_path = replicator_cli.write_report(Path(temp), [artifact])
            report = report_path.read_text(encoding="utf-8")

        self.assertIn("No credentials", report)
        self.assertIn("Credential/manual auth items not moved: 1", report)
        self.assertIn("Stable artifact IDs: enabled", report)
        self.assertIn("Artifact ID:", report)
        self.assertIn("By Classification", report)
        self.assertIn("Recreate this credential manually", report)

    def test_fixture_inventory_covers_all_initial_providers_safely(self):
        root = Path(__file__).resolve().parent / "fixtures" / "home"
        options = replicator_cli.ScanOptions(root_override=root)
        artifacts = []
        for provider in ("claude", "codex", "openclaw", "qwen", "kimi"):
            artifacts.extend(replicator_cli.inventory_provider(adapters.PROVIDERS[provider], options))

        summary = replicator_cli.summarize_artifacts(artifacts)

        self.assertEqual(set(summary["by_provider"]), {"claude", "codex", "openclaw", "qwen", "kimi"})
        self.assertGreaterEqual(summary["by_classification"].get("portable_with_edits", 0), 3)
        self.assertGreaterEqual(summary["credential_reference_count"], 1)
        self.assertFalse(any("ignored.tmp" in artifact.path for artifact in artifacts))

    def test_max_depth_limits_nested_artifacts(self):
        root = Path(__file__).resolve().parent / "fixtures" / "home"
        options = replicator_cli.ScanOptions(root_override=root, max_depth=1)
        artifacts = replicator_cli.inventory_provider(adapters.PROVIDERS["claude"], options)

        self.assertFalse(any("SKILL.md" in artifact.path for artifact in artifacts))

    def test_bundle_includes_v1_schema_summary_and_version(self):
        artifact = replicator_cli.Artifact(
            provider="codex",
            path="/tmp/.codex/skills/demo/SKILL.md",
            artifact_type="skill_or_prompt",
            classification="portable_with_edits",
            reason="Skill/prompt instructions can usually be translated.",
            target_notes="Review instructions.",
            contains_secret_reference=False,
        )
        with tempfile.TemporaryDirectory() as temp:
            bundle_path = replicator_cli.write_bundle(Path(temp), [artifact])
            bundle = __import__("json").loads(bundle_path.read_text(encoding="utf-8"))

        self.assertEqual(bundle["schema"], "replicator.resonance_bundle.v1")
        self.assertEqual(bundle["schema_version"], "1.0.0")
        self.assertEqual(bundle["replicator_version"], "0.6.0")
        self.assertIn("source_metadata", bundle)
        self.assertEqual(bundle["artifacts"][0]["artifact_id"], schema.stable_artifact_id("codex", "/tmp/.codex/skills/demo/SKILL.md", "skill_or_prompt"))
        self.assertEqual(bundle["artifacts"][0]["checksum_status"], "missing")
        self.assertEqual(bundle["summary"]["by_classification"], {"portable_with_edits": 1})

    def test_bundle_skips_secret_checksums_and_itemizes_secret_records(self):
        artifact = replicator_cli.Artifact(
            provider="claude",
            path="/tmp/.claude/oauth.json",
            artifact_type="credential_reference",
            classification="not_portable",
            reason="Path appears to contain credentials.",
            target_notes="Recreate manually.",
            contains_secret_reference=True,
        )
        with tempfile.TemporaryDirectory() as temp:
            bundle_path = replicator_cli.write_bundle(Path(temp), [artifact])
            bundle = __import__("json").loads(bundle_path.read_text(encoding="utf-8"))

        self.assertEqual(bundle["artifacts"][0]["checksum_sha256"], None)
        self.assertEqual(bundle["artifacts"][0]["checksum_status"], "skipped_secret")
        self.assertEqual(len(bundle["skipped_secrets"]), 1)
        self.assertEqual(bundle["skipped_secrets"][0]["artifact_id"], bundle["artifacts"][0]["artifact_id"])

    def test_bundle_checksums_non_secret_files(self):
        with tempfile.TemporaryDirectory() as temp:
            file_path = Path(temp) / "SKILL.md"
            file_path.write_text("# Demo\n", encoding="utf-8")
            artifact = replicator_cli.Artifact(
                provider="claude",
                path=str(file_path),
                artifact_type="skill_or_prompt",
                classification="portable_with_edits",
                reason="Skill/prompt instructions can usually be translated.",
                target_notes="Review instructions.",
                contains_secret_reference=False,
            )
            bundle_path = replicator_cli.write_bundle(Path(temp) / "out", [artifact])
            bundle = __import__("json").loads(bundle_path.read_text(encoding="utf-8"))

        self.assertEqual(bundle["artifacts"][0]["checksum_status"], "ok")
        self.assertEqual(len(bundle["artifacts"][0]["checksum_sha256"]), 64)

    def test_generate_codex_draft_from_fixture_claude_skill(self):
        root = Path(__file__).resolve().parent / "fixtures" / "home"
        options = replicator_cli.ScanOptions(root_override=root)
        artifacts = replicator_cli.inventory_provider(adapters.PROVIDERS["claude"], options)

        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            bundle_path = replicator_cli.write_bundle(temp_path / "bundle", artifacts, options)
            results = drafts.generate_codex_drafts(bundle_path, temp_path / "drafts")
            draft_skill = temp_path / "drafts" / "codex" / "skills" / "review" / "SKILL.md"
            draft_notes = temp_path / "drafts" / "codex" / "skills" / "review" / "MIGRATION_NOTES.md"
            manifest = __import__("json").loads(
                (temp_path / "drafts" / "codex" / "manifest.json").read_text(encoding="utf-8")
            )
            notes_text = draft_notes.read_text(encoding="utf-8")

            self.assertTrue(draft_skill.is_file())
            self.assertTrue(draft_notes.is_file())
            self.assertEqual(sum(1 for result in results if result.status == "generated"), 1)
            self.assertGreaterEqual(manifest["skipped_count"], 1)
            self.assertEqual(manifest["generated_count"], 1)
            self.assertIn("Artifact ID:", notes_text)
            self.assertNotIn("oauth.json", notes_text.lower())

    def test_generate_claude_draft_from_fixture_codex_skill(self):
        root = Path(__file__).resolve().parent / "fixtures" / "home"
        options = replicator_cli.ScanOptions(root_override=root)
        artifacts = replicator_cli.inventory_provider(adapters.PROVIDERS["codex"], options)

        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            bundle_path = replicator_cli.write_bundle(temp_path / "bundle", artifacts, options)
            results = drafts.generate_claude_drafts(bundle_path, temp_path / "drafts")
            draft_skill = temp_path / "drafts" / "claude" / "skills" / "portability" / "SKILL.md"
            draft_notes = temp_path / "drafts" / "claude" / "skills" / "portability" / "MIGRATION_NOTES.md"
            manifest = __import__("json").loads(
                (temp_path / "drafts" / "claude" / "manifest.json").read_text(encoding="utf-8")
            )
            notes_text = draft_notes.read_text(encoding="utf-8")

            self.assertTrue(draft_skill.is_file())
            self.assertTrue(draft_notes.is_file())
            self.assertEqual(sum(1 for result in results if result.status == "generated"), 1)
            self.assertEqual(manifest["source_provider"], "codex")
            self.assertEqual(manifest["target_provider"], "claude")
            self.assertEqual(manifest["generated_count"], 1)
            self.assertIn("Target provider: `claude`", notes_text)

    def test_generate_command_writes_manifest(self):
        root = Path(__file__).resolve().parent / "fixtures" / "home"
        script = Path(__file__).resolve().parents[1] / "replicator" / "scripts" / "replicator.py"
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            inventory_output = temp_path / "inventory"
            draft_output = temp_path / "drafts"
            run(
                [
                    sys.executable,
                    str(script),
                    "inventory",
                    "--providers",
                    "claude",
                    "--root",
                    str(root),
                    "--output",
                    str(inventory_output),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            result = run(
                [
                    sys.executable,
                    str(script),
                    "generate",
                    "--from-bundle",
                    str(inventory_output / "bundles" / "resonance-bundle.json"),
                    "--to",
                    "codex",
                    "--output",
                    str(draft_output),
                ],
                capture_output=True,
                text=True,
                check=True,
            )

        self.assertIn("Generated drafts: 1", result.stdout)
        self.assertIn("Skipped artifacts:", result.stdout)

    def test_generate_command_supports_claude_target(self):
        root = Path(__file__).resolve().parent / "fixtures" / "home"
        script = Path(__file__).resolve().parents[1] / "replicator" / "scripts" / "replicator.py"
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            inventory_output = temp_path / "inventory"
            draft_output = temp_path / "drafts"
            run(
                [
                    sys.executable,
                    str(script),
                    "inventory",
                    "--providers",
                    "codex",
                    "--root",
                    str(root),
                    "--output",
                    str(inventory_output),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            result = run(
                [
                    sys.executable,
                    str(script),
                    "generate",
                    "--from-bundle",
                    str(inventory_output / "bundles" / "resonance-bundle.json"),
                    "--to",
                    "claude",
                    "--output",
                    str(draft_output),
                ],
                capture_output=True,
                text=True,
                check=True,
            )

        self.assertIn("Wrote claude draft manifest:", result.stdout)
        self.assertIn("Generated drafts: 1", result.stdout)


if __name__ == "__main__":
    unittest.main()
