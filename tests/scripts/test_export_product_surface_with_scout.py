"""Tests for the Scout-to-product-surface export script."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_product_surface_with_scout.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_product_surface_with_scout", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_export_product_surface_with_scout_writes_normalized_rows(tmp_path) -> None:
    module = _load_module()
    output = tmp_path / "constructor-product-rows.json"
    scout_response = {
        "success": True,
        "url": "https://constructor.com/changelog",
        "metadata": {"crawled_at": "2026-07-10T19:00:00+00:00"},
        "data": {
            "changes": [
                {
                    "capability": "AI Shopping Agent",
                    "change_type": "release",
                    "summary": "Constructor released AI Shopping Agent.",
                }
            ]
        },
    }
    command = [sys.executable, "-c", f"import json; print({json.dumps(json.dumps(scout_response))})"]

    code = module.main([
        "--tenant-id",
        "1",
        "--company-id",
        "20",
        "--company-name",
        "Constructor",
        "--company-role",
        "competitor",
        "--surface-family",
        "changelog",
        "--url",
        "https://constructor.com/changelog",
        "--scout-command-json",
        json.dumps(command),
        "--output",
        str(output),
    ])

    rows = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert rows[0]["company_name"] == "Constructor"
    assert rows[0]["method"] == "scout_changelog"
    assert rows[0]["capability"] == "AI Shopping Agent"


def test_export_product_surface_with_scout_filters_cookie_consent_noise(tmp_path) -> None:
    module = _load_module()
    output = tmp_path / "athos-product-rows.json"
    scout_response = {
        "success": True,
        "url": "https://athoscommerce.com/platform",
        "metadata": {"crawled_at": "2026-07-28T09:20:20+00:00"},
        "data": {
            "changes": [
                {
                    "capability": "Cookie Consent Management",
                    "change_type": "docs_update",
                    "summary": "The platform includes features for managing user consent regarding cookies.",
                    "excerpt": "Accept Deny View preferences Save preferences",
                },
                {
                    "capability": "Policy Document Integration",
                    "change_type": "docs_update",
                    "summary": "The platform integrates links to relevant legal and privacy policy documents.",
                    "excerpt": "Cookie Policy Privacy Policy",
                },
                {
                    "capability": "Personalized Merchandising Rules",
                    "change_type": "docs_update",
                    "summary": "Athos documents merchandising controls for personalized product experiences.",
                    "excerpt": "Create targeted merchandising rules for product discovery experiences.",
                },
            ]
        },
    }
    command = [sys.executable, "-c", f"import json; print({json.dumps(json.dumps(scout_response))})"]

    code = module.main([
        "--tenant-id",
        "1",
        "--company-id",
        "7",
        "--company-name",
        "Athos Commerce",
        "--company-role",
        "competitor",
        "--surface-family",
        "product_page",
        "--url",
        "https://athoscommerce.com/platform",
        "--scout-command-json",
        json.dumps(command),
        "--output",
        str(output),
    ])

    rows = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert [row["capability"] for row in rows] == ["Personalized Merchandising Rules"]


def test_build_scout_extract_command_contains_schema_instruction_and_url() -> None:
    module = _load_module()
    target = module.ProductSurfaceTarget(
        tenant_id=1,
        company_id=30,
        company_name="Elastic",
        company_role="competitor",
        surface_family="docs",
        url="https://www.elastic.co/guide/",
    )

    command = module.build_scout_extract_command(
        target,
        scout_bin="scout",
        provider="gemini/gemini-2.5-flash",
        use_js=True,
    )

    assert command[:2] == ["scout", "extract"]
    assert "https://www.elastic.co/guide/" in command
    assert "--js" in command
    assert "--schema" in command
    schema = json.loads(command[command.index("--schema") + 1])
    assert schema["properties"]["changes"]["type"] == "array"
    assert "--instruction" in command
    assert "Elastic" in command[command.index("--instruction") + 1]
    assert "GitHub release" in command[command.index("--instruction") + 1]
    assert "bug fixes" in command[command.index("--instruction") + 1]


def test_build_scout_extract_command_focuses_on_requested_capability() -> None:
    module = _load_module()
    target = module.ProductSurfaceTarget(
        tenant_id=1,
        company_id=30,
        company_name="Coveo",
        company_role="competitor",
        surface_family="docs",
        url="https://docs.coveo.com/",
    )

    command = module.build_scout_extract_command(
        target,
        scout_bin="scout",
        provider="gemini/gemini-2.5-flash",
        use_js=False,
        focus_capability="Channel Assistant",
    )

    instruction = command[command.index("--instruction") + 1]
    assert "Focus first on product proof for Channel Assistant." in instruction
    assert "If the page has no proof for Channel Assistant" in instruction


def test_argus_extraction_prompt_names_release_notes_and_static_product_proof() -> None:
    module = _load_module()
    target = module.ProductSurfaceTarget(
        tenant_id=1,
        company_id=35,
        company_name="Meilisearch",
        company_role="competitor",
        surface_family="changelog",
        url="https://github.com/meilisearch/meilisearch/releases",
    )

    prompt = module._argus_extraction_prompt("## v1.49.0\n### Bug Fixes\nHybrid search fixes.", target)

    assert "GitHub release pages" in prompt
    assert "bug fixes" in prompt
    assert "static product, docs, pricing, or integration page" in prompt
    assert "Extract up to 12" in prompt


def test_argus_extraction_prompt_focuses_on_requested_capability() -> None:
    module = _load_module()
    target = module.ProductSurfaceTarget(
        tenant_id=1,
        company_id=35,
        company_name="Coveo",
        company_role="competitor",
        surface_family="docs",
        url="https://docs.coveo.com/",
    )

    prompt = module._argus_extraction_prompt(
        "Channel assistant docs mention merchandising conversations.",
        target,
        focus_capability="Channel Assistant",
    )

    assert "Focus first on product proof for Channel Assistant." in prompt
    assert "If the page has no proof for Channel Assistant" in prompt


def test_export_falls_back_to_argus_extraction_when_scout_llm_is_disabled(monkeypatch, tmp_path) -> None:
    module = _load_module()
    output = tmp_path / "constructor-product-rows.json"
    calls = []

    def fake_run_command(command, timeout_seconds):
        calls.append(command)
        if command[1] == "extract":
            return {
                "success": False,
                "url": "https://constructor.com/changelog",
                "metadata": {"crawled_at": "2026-07-10T19:00:00+00:00"},
                "error": "No LLM API key configured and no css_schema provided.",
            }
        return {
            "success": True,
            "url": "https://constructor.com/changelog",
            "clean_markdown": "# Changelog\n\nAI Shopping Agent released.",
            "metadata": {"crawled_at": "2026-07-10T19:00:00+00:00"},
        }

    def fake_extract_with_argus(markdown, target, *, provider, model_id, captured_at):
        assert markdown == "# Changelog\n\nAI Shopping Agent released."
        assert target.company_name == "Constructor"
        assert captured_at == "2026-07-10T19:00:00+00:00"
        return {
            "success": True,
            "url": target.url,
            "metadata": {"crawled_at": captured_at},
            "data": {
                "changes": [
                    {
                        "capability": "AI Shopping Agent",
                        "change_type": "release",
                        "summary": "Constructor released AI Shopping Agent.",
                    }
                ]
            },
        }

    monkeypatch.setattr(module, "_run_command", fake_run_command)
    monkeypatch.setattr(module, "extract_product_changes_with_argus", fake_extract_with_argus)

    code = module.main([
        "--tenant-id",
        "1",
        "--company-id",
        "20",
        "--company-name",
        "Constructor",
        "--company-role",
        "competitor",
        "--surface-family",
        "changelog",
        "--url",
        "https://constructor.com/changelog",
        "--scout-bin",
        "scout",
        "--provider",
        "gemini/gemini-2.5-flash",
        "--output",
        str(output),
    ])

    rows = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert [call[1] for call in calls] == ["extract", "scrape"]
    assert rows[0]["company_name"] == "Constructor"
    assert rows[0]["capability"] == "AI Shopping Agent"


def test_export_falls_back_to_argus_extraction_when_scout_returns_empty_changes(
    monkeypatch,
    tmp_path,
) -> None:
    module = _load_module()
    output = tmp_path / "meilisearch-product-rows.json"
    calls = []

    def fake_run_command(command, timeout_seconds):
        calls.append(command)
        if command[1] == "extract":
            return {
                "success": True,
                "url": "https://github.com/meilisearch/meilisearch/releases",
                "metadata": {"crawled_at": "2026-07-10T19:00:00+00:00"},
                "data": {"changes": []},
            }
        return {
            "success": True,
            "url": "https://github.com/meilisearch/meilisearch/releases",
            "clean_markdown": "# Releases\n\nHybrid search ranking options released.",
            "metadata": {"crawled_at": "2026-07-10T19:00:00+00:00"},
        }

    def fake_extract_with_argus(markdown, target, *, provider, model_id, captured_at):
        assert "Hybrid search ranking" in markdown
        assert target.company_name == "Meilisearch"
        return {
            "success": True,
            "url": target.url,
            "metadata": {"crawled_at": captured_at},
            "data": {
                "changes": [
                    {
                        "capability": "Hybrid search ranking",
                        "change_type": "release",
                        "summary": "Meilisearch released hybrid search ranking options.",
                    }
                ]
            },
        }

    monkeypatch.setattr(module, "_run_command", fake_run_command)
    monkeypatch.setattr(module, "extract_product_changes_with_argus", fake_extract_with_argus)

    code = module.main([
        "--tenant-id",
        "1",
        "--company-id",
        "35",
        "--company-name",
        "Meilisearch",
        "--company-role",
        "competitor",
        "--surface-family",
        "changelog",
        "--url",
        "https://github.com/meilisearch/meilisearch/releases",
        "--scout-bin",
        "scout",
        "--provider",
        "gemini/gemini-2.5-flash",
        "--output",
        str(output),
    ])

    rows = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert [call[1] for call in calls] == ["extract", "scrape"]
    assert rows[0]["company_name"] == "Meilisearch"
    assert rows[0]["capability"] == "Hybrid search ranking"


def test_github_release_fallback_converts_release_body_to_product_rows(monkeypatch) -> None:
    module = _load_module()
    target = module.ProductSurfaceTarget(
        tenant_id=1,
        company_id=40,
        company_name="Typesense",
        company_role="competitor",
        surface_family="changelog",
        url="https://github.com/typesense/typesense/releases",
    )
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "tag_name": "v30.2",
                        "name": "Version 30.2",
                        "html_url": "https://github.com/typesense/typesense/releases/tag/v30.2",
                        "published_at": "2026-04-19T16:00:00Z",
                        "body": "### Bug Fixes\n* Fixed incorrect handling of numeric != filters.\n",
                    }
                ]
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, dict(request.header_items()), timeout))
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    rows = module.github_release_rows(target, timeout_seconds=12)

    assert calls[0][0] == "https://api.github.com/repos/typesense/typesense/releases?per_page=5"
    assert calls[0][2] == 12
    assert rows == [
        {
            "company_id": 40,
            "company_name": "Typesense",
            "company_role": "competitor",
            "capability": "incorrect handling of numeric != filters.",
            "change_type": "release",
            "summary": "Typesense v30.2: Fixed incorrect handling of numeric != filters.",
            "source_url": "https://github.com/typesense/typesense/releases/tag/v30.2",
            "captured_at": "2026-04-19T16:00:00Z",
            "excerpt": "Fixed incorrect handling of numeric != filters.",
            "method": "scout_changelog",
            "surface_family": "changelog",
        }
    ]


def test_github_release_fallback_fails_closed_on_non_github_or_fetch_error(monkeypatch) -> None:
    module = _load_module()
    target = module.ProductSurfaceTarget(
        tenant_id=1,
        company_id=99,
        company_name="Example",
        company_role="competitor",
        surface_family="changelog",
        url="https://example.com/releases",
    )

    def fake_urlopen(request, timeout):
        raise AssertionError("non-GitHub URL should not be fetched")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    assert module.github_release_rows(target, timeout_seconds=3) == []

    target.url = "https://github.com/example/project/releases"
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda request, timeout: (_ for _ in ()).throw(URLError("offline")))

    assert module.github_release_rows(target, timeout_seconds=3) == []


def test_github_release_fallback_cleans_pr_suffixes_and_skips_internal_maintenance(
    monkeypatch,
) -> None:
    module = _load_module()
    target = module.ProductSurfaceTarget(
        tenant_id=1,
        company_id=35,
        company_name="Meilisearch",
        company_role="competitor",
        surface_family="changelog",
        url="https://github.com/meilisearch/meilisearch/releases",
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "tag_name": "v1.49.0",
                        "html_url": "https://github.com/meilisearch/meilisearch/releases/tag/v1.49.0",
                        "published_at": "2026-07-06T08:14:35Z",
                        "body": (
                            "* [v1.49.0] Improve the synonyms storage by @Kerollmops in "
                            "https://github.com/meilisearch/meilisearch/pull/6466\n"
                            "* Split unit tests into separate files by @0xfandom in "
                            "https://github.com/meilisearch/meilisearch/pull/6468\n"
                        ),
                    }
                ]
            ).encode("utf-8")

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda request, timeout: FakeResponse())

    rows = module.github_release_rows(target, timeout_seconds=12)

    assert len(rows) == 1
    assert rows[0]["capability"] == "the synonyms storage"
    assert rows[0]["excerpt"] == "Improve the synonyms storage"
    assert "[v1.49.0]" not in rows[0]["summary"]
    assert "github.com" not in rows[0]["summary"]


def test_export_uses_github_release_fallback_after_scout_and_argus_return_empty(
    monkeypatch,
    tmp_path,
) -> None:
    module = _load_module()
    output = tmp_path / "typesense-product-rows.json"

    def fake_run_command(command, timeout_seconds):
        if command[1] == "extract":
            return {
                "success": True,
                "url": "https://github.com/typesense/typesense/releases",
                "metadata": {"crawled_at": "2026-07-10T19:00:00+00:00"},
                "data": {"changes": []},
            }
        return {
            "success": True,
            "url": "https://github.com/typesense/typesense/releases",
            "clean_markdown": "# Releases\n\nVersion 30.2.",
            "metadata": {"crawled_at": "2026-07-10T19:00:00+00:00"},
        }

    def fake_argus_empty(markdown, target, *, provider, model_id, captured_at):
        return {
            "success": True,
            "url": target.url,
            "metadata": {"crawled_at": captured_at},
            "data": {"changes": []},
        }

    def fake_github_rows(target, *, timeout_seconds):
        assert target.company_name == "Typesense"
        return [
            {
                "company_id": 40,
                "company_name": "Typesense",
                "company_role": "competitor",
                "capability": "numeric filter execution",
                "change_type": "release",
                "summary": "Typesense v30.2 fixed numeric filter execution.",
                "source_url": "https://github.com/typesense/typesense/releases/tag/v30.2",
                "captured_at": "2026-04-19T16:00:00Z",
                "excerpt": "Fixed incorrect handling of numeric filters.",
                "method": "scout_changelog",
                "surface_family": "changelog",
            }
        ]

    monkeypatch.setattr(module, "_run_command", fake_run_command)
    monkeypatch.setattr(module, "extract_product_changes_with_argus", fake_argus_empty)
    monkeypatch.setattr(module, "github_release_rows", fake_github_rows)

    code = module.main([
        "--tenant-id",
        "1",
        "--company-id",
        "40",
        "--company-name",
        "Typesense",
        "--company-role",
        "competitor",
        "--surface-family",
        "changelog",
        "--url",
        "https://github.com/typesense/typesense/releases",
        "--scout-bin",
        "scout",
        "--provider",
        "gemini/gemini-2.5-flash",
        "--output",
        str(output),
    ])

    rows = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert rows[0]["company_name"] == "Typesense"
    assert rows[0]["capability"] == "numeric filter execution"


def test_run_command_reports_timeout_without_python_traceback(monkeypatch) -> None:
    module = _load_module()

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["scout", "scrape", "https://example.com"], timeout=3)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    try:
        module._run_command(["scout", "scrape", "https://example.com"], timeout_seconds=3)
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected timeout RuntimeError")

    assert message == "Scout product surface extraction timed out after 3s"
    assert "Traceback" not in message
