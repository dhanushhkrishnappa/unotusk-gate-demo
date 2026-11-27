#!/usr/bin/env python3
"""
Unotusk CI Decision Gate Runner.
Invoked inside GitHub Actions or local CLI to evaluate candidate commits against
server-side Architectural Decision Records (ADRs) and boundary constraints.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import tempfile
from typing import Any
import urllib.error
import urllib.request


def run_git(args: list[str]) -> str:
    """Executes a git command and returns stripped stdout."""
    res = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        return ""
    return res.stdout.strip()


def resolve_commit_shas() -> tuple[str, str]:
    """
    Resolves base_sha and head_sha from GitHub event payload,
    or falls back to local git history.
    """
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        try:
            with open(event_path, "r", encoding="utf-8") as f:
                event_data = json.load(f)
            pr = event_data.get("pull_request")
            if pr:
                base_sha = pr.get("base", {}).get("sha")
                head_sha = pr.get("head", {}).get("sha")
                if base_sha and head_sha:
                    return base_sha, head_sha
        except Exception as ex:
            print(f"::warning::Could not parse GITHUB_EVENT_PATH: {ex}")

    # Fallback for local testing or push workflows
    head_sha = run_git(["rev-parse", "HEAD"])
    base_sha = run_git(["merge-base", "origin/main", "HEAD"]) or run_git(["rev-parse", "HEAD~1"])

    if not head_sha:
        head_sha = "0000000000000000000000000000000000000000"
    if not base_sha:
        base_sha = head_sha

    return base_sha, head_sha


def get_changed_files(base_sha: str, head_sha: str) -> list[str]:
    """Retrieves modified files between base and head refs."""
    diff_output = run_git(["diff", "--name-only", base_sha, head_sha])
    if not diff_output:
        return []
    return [line.strip() for line in diff_output.splitlines() if line.strip()]


def create_git_bundle(base_sha: str, head_sha: str) -> str | None:
    """Packages commit range into an air-gapped base64-encoded git bundle."""
    with tempfile.TemporaryDirectory(prefix="unotusk_bundle_") as tmpdir:
        bundle_file = os.path.join(tmpdir, "candidate.bundle")
        res = subprocess.run(
            ["git", "bundle", "create", bundle_file, f"{base_sha}..{head_sha}"],
            capture_output=True,
            check=False,
        )
        if res.returncode == 0 and os.path.exists(bundle_file):
            with open(bundle_file, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
    return None


def post_gate_evaluation(
    server_url: str,
    ci_token: str,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Sends HTTP POST to /api/v1/ci/gate/evaluate."""
    endpoint = f"{server_url.rstrip('/')}/api/v1/ci/gate/evaluate"
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Authorization": f"Bearer {ci_token}",
            "Content-Type": "application/json",
            "User-Agent": "Unotusk-CI-Gate/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            status_code = resp.status
            body = resp.read().decode("utf-8")
            return status_code, json.loads(body)
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8", errors="replace")
        try:
            return he.code, json.loads(err_body)
        except Exception:
            return he.code, {"error": err_body or he.reason}
    except Exception as exc:
        return 500, {"error": str(exc)}


def main() -> int:
    print("=" * 70)
    print("🚀 UNOTUSK ARCHITECTURAL DECISION GATE (Track T5)")
    print("=" * 70)

    server_url = os.environ.get("UNOTUSK_SERVER_URL", "").strip()
    ci_token = os.environ.get("UNOTUSK_CI_TOKEN", "").strip()
    project_id = os.environ.get("UNOTUSK_PROJECT_ID", "").strip()
    gate_mode = os.environ.get("UNOTUSK_GATE_MODE", "enforced").strip().lower()
    use_bundle = os.environ.get("UNOTUSK_USE_BUNDLE", "false").strip().lower() == "true"

    if not server_url:
        print("::error::Missing UNOTUSK_SERVER_URL environment variable.")
        return 1
    if not ci_token:
        print("::error::Missing UNOTUSK_CI_TOKEN environment variable.")
        return 1
    if not project_id:
        print("::error::Missing UNOTUSK_PROJECT_ID environment variable.")
        return 1

    base_sha, head_sha = resolve_commit_shas()
    changed_files = get_changed_files(base_sha, head_sha)

    print(f"• Target Server:     {server_url}")
    print(f"• Project ID:        {project_id}")
    print(f"• Enforcement Mode:  {gate_mode}")
    print(f"• Commit Range:      {base_sha[:8]}..{head_sha[:8]}")
    print(f"• Files Modified:    {len(changed_files)} file(s)")

    bundle_b64: str | None = None
    if use_bundle:
        print("• Air-gapped Mode:   Generating candidate git bundle...")
        bundle_b64 = create_git_bundle(base_sha, head_sha)

    payload = {
        "project_id": project_id,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "mode": gate_mode,
        "changed_files_hint": changed_files,
        "bundle_payload_b64": bundle_b64,
    }

    print("\n⏳ Submitting changeset for pre-merge evaluation...")
    status_code, response_data = post_gate_evaluation(server_url, ci_token, payload)

    # 1. Output GitHub Step Summary
    summary_md = response_data.get("summary_markdown", "")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path and summary_md:
        try:
            with open(summary_path, "a", encoding="utf-8") as sf:
                sf.write(summary_md + "\n")
        except Exception as ex:
            print(f"::warning::Failed writing to GITHUB_STEP_SUMMARY: {ex}")

    # 2. Process Result
    if status_code != 200:
        error_msg = response_data.get("message") or response_data.get("error") or f"HTTP {status_code}"
        print(f"\n❌ GATE EVALUATION FAILED (HTTP {status_code}): {error_msg}")
        if gate_mode == "enforced":
            return 1
        return 0

    decision = response_data.get("decision", "UNKNOWN")
    exit_code = response_data.get("exit_code", 0)
    violations = response_data.get("violations", [])
    waived = response_data.get("waived_violations", [])
    expired = response_data.get("expired_exceptions", [])

    print(f"\n📋 Decision:     {decision}")
    print(f"📊 Exit Code:    {exit_code}")
    print(f"🚫 Violations:   {len(violations)}")
    print(f"🛡️  Waived:       {len(waived)}")
    print(f"⏳ Expired:      {len(expired)}")

    if violations:
        print("\n" + "-" * 70)
        print("🚫 ACTIVE ARCHITECTURAL VIOLATIONS:")
        for idx, v in enumerate(violations, start=1):
            sev = v.get("severity", "HIGH")
            title = v.get("title", "Violation")
            fpath = v.get("file_path", "unknown")
            remed = v.get("remediation", "N/A")
            print(f" [{idx}] [{sev}] {title}")
            print(f"     File:        {fpath}")
            print(f"     Remediation: {remed}")
        print("-" * 70)

    if exit_code == 0:
        print("\n✅ GATE PASSED: All architectural boundary checks satisfied.")
    else:
        print("\n❌ GATE BLOCKED: Branch merge prohibited due to architectural violations.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
