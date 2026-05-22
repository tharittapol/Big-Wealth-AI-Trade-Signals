"""Wrapper around Claude Code CLI for headless AI calls.

Uses `claude -p` non-interactive mode so the system can call Claude
without the Anthropic Python SDK or separate API credentials.
Requires the `claude` CLI to be installed and authenticated.

Auth strategy: OAuth session (Pro/Max plan) stored in ~/.claude/.credentials.json.
Locally: CLI uses the user's existing OAuth session.
Cloud Run: entrypoint.sh writes credentials from CLAUDE_CREDENTIALS secret before startup.
ANTHROPIC_API_KEY is stripped from subprocess env so OAuth always takes priority.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import structlog

logger = structlog.get_logger()


def run_claude(
    prompt: str,
    system_prompt: str = "",
    model: str = "sonnet",
    timeout: int = 120,
    enable_web_search: bool = False,
) -> str:
    """
    Call Claude via Claude Code CLI in headless mode.

    Args:
        prompt: User message / task description.
        system_prompt: Optional system prompt to override defaults.
        model: Model alias — "sonnet", "opus", or "haiku".
        timeout: Seconds before subprocess is killed.
        enable_web_search: When True, passes --allowedTools WebSearch to the CLI.
            Automatically extends timeout to at least 300s for web search + thinking.

    Returns:
        The text response from Claude (result field of JSON output).

    Raises:
        RuntimeError: If the CLI is not found, exits non-zero, or returns an error.
    """
    if not shutil.which("claude"):
        raise RuntimeError(
            "Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
        )

    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", model,
        "--dangerously-skip-permissions",
    ]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    if enable_web_search:
        cmd += ["--allowedTools", "WebSearch"]

    effective_timeout = max(timeout, 300) if enable_web_search else timeout

    # Strip ANTHROPIC_API_KEY so Claude CLI always uses OAuth session (Pro/Max plan).
    # Cloud Run: credentials written to ~/.claude/.credentials.json by entrypoint.sh.
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=effective_timeout,
        env=env,
        stdin=subprocess.DEVNULL,  # Prevent the 3-second stdin-wait warning
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"Claude CLI exited {proc.returncode}: "
            f"stderr={proc.stderr.strip()!r} stdout={proc.stdout[:300]!r}"
        )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude CLI returned non-JSON output: {proc.stdout[:200]}") from e

    if data.get("is_error"):
        raise RuntimeError(f"Claude CLI returned error response: {data}")

    logger.info(
        "Claude CLI call complete",
        model=model,
        web_search=enable_web_search,
        cost_usd=data.get("total_cost_usd"),
        input_tokens=data.get("usage", {}).get("input_tokens"),
        output_tokens=data.get("usage", {}).get("output_tokens"),
    )
    return data.get("result", "")
