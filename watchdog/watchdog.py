#!/usr/bin/env python3
"""
Aleph-One Self-Healing Watchdog Engine
========================================
Monitors the FastAPI backend health endpoint. On 3 consecutive failures it:
  1. Collects docker logs + source file contents
  2. Calls Claude API (claude-opus-4-7, adaptive thinking) to diagnose and fix
  3. Pushes the corrected file to GitHub → triggers CD pipeline redeploy

Security:   All secrets loaded from .env.watchdog — nothing hardcoded.
Stability:  15-minute cooldown between heal attempts; loop-safe.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import anthropic
import requests
from dotenv import load_dotenv
from github import Github, GithubException

# ── Environment ───────────────────────────────────────────────────────────────
_ENV_FILE = Path(__file__).parent / ".env.watchdog"
load_dotenv(_ENV_FILE)

HEALTH_URL          = os.environ.get("HEALTH_URL",           "http://localhost:8001/health")
CHECK_INTERVAL      = int(os.environ.get("CHECK_INTERVAL_SECONDS", "60"))
FAILURE_THRESHOLD   = int(os.environ.get("FAILURE_THRESHOLD",       "3"))
COOLDOWN_MINUTES    = int(os.environ.get("COOLDOWN_MINUTES",        "15"))
HEALTH_TIMEOUT      = int(os.environ.get("HEALTH_TIMEOUT_SECONDS",  "10"))
LOG_TAIL_LINES      = int(os.environ.get("LOG_TAIL_LINES",          "150"))

DOCKER_COMPOSE_FILE = os.environ.get("DOCKER_COMPOSE_FILE",
                                     "/opt/aleph-one/docker-compose.prod.yml")
DOCKER_SERVICE_NAME = os.environ.get("DOCKER_SERVICE_NAME", "aleph-api")
DEPLOY_PATH         = os.environ.get("DEPLOY_PATH",         "/opt/aleph-one")

ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL        = os.environ.get("CLAUDE_MODEL",       "claude-opus-4-7")

GITHUB_TOKEN        = os.environ.get("GITHUB_TOKEN",  "")
GITHUB_REPO         = os.environ.get("GITHUB_REPO",   "")
GITHUB_BRANCH       = os.environ.get("GITHUB_BRANCH", "main")

_TARGET_FILES_RAW   = os.environ.get(
    "TARGET_SOURCE_FILES",
    "src/main.py,src/database.py,src/engines.py",
)
TARGET_FILES: list[str] = [f.strip() for f in _TARGET_FILES_RAW.split(",") if f.strip()]

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_FILE = Path(__file__).parent / "watchdog.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("watchdog")

# ── Prompt caching: static system prompt ──────────────────────────────────────
# This never changes per request, so we mark it for caching to reduce API cost.
_SYSTEM_PROMPT_TEXT = """\
You are an autonomous infrastructure self-healing agent for a production FastAPI \
Python application called Aleph-One. Your sole purpose is to analyze error logs and \
broken source code, then produce a corrected version of the file that is causing the \
failure.

You will receive:
1. Docker container error logs (last N lines)
2. The current source code of one or more Python files that could be the cause

Your task:
- Analyze the logs carefully to identify the root cause of the failure
- Determine which SINGLE file is responsible and should be patched
- Return ONLY a valid JSON object — no prose, no markdown fences, no explanation

Required JSON format (output nothing else):
{
  "analysis": "<one-line summary of root cause>",
  "target_file": "<relative path of file to fix, e.g. src/main.py>",
  "fixed_code": "<complete, runnable source code of the corrected file>"
}

Rules:
- fixed_code must be the COMPLETE file — never a partial snippet or diff
- Do not wrap the JSON in markdown code blocks
- Only fix bugs that are clearly evidenced by the logs
- Do not refactor, rename, or add features beyond the minimal fix
- If you cannot determine a safe fix, set target_file and fixed_code to null
"""

_SYSTEM_PROMPT_BLOCK = {
    "type": "text",
    "text": _SYSTEM_PROMPT_TEXT,
    "cache_control": {"type": "ephemeral"},  # cached — never changes per request
}

# ── State ─────────────────────────────────────────────────────────────────────
_consecutive_failures: int = 0
_last_heal_attempt: Optional[datetime] = None


def _in_cooldown() -> bool:
    if _last_heal_attempt is None:
        return False
    elapsed = datetime.utcnow() - _last_heal_attempt
    return elapsed < timedelta(minutes=COOLDOWN_MINUTES)


def _cooldown_remaining_minutes() -> int:
    if _last_heal_attempt is None:
        return 0
    elapsed = datetime.utcnow() - _last_heal_attempt
    remaining = timedelta(minutes=COOLDOWN_MINUTES) - elapsed
    return max(0, int(remaining.total_seconds() / 60))


# ── 1. Health Check ───────────────────────────────────────────────────────────
def check_health() -> bool:
    """Returns True when the service responds HTTP 200."""
    try:
        resp = requests.get(HEALTH_URL, timeout=HEALTH_TIMEOUT)
        if resp.status_code == 200:
            return True
        log.warning("Health check HTTP %d from %s", resp.status_code, HEALTH_URL)
        return False
    except requests.exceptions.ConnectionError:
        log.warning("Health check: connection refused (%s)", HEALTH_URL)
        return False
    except requests.exceptions.Timeout:
        log.warning("Health check: timeout after %ds", HEALTH_TIMEOUT)
        return False
    except requests.exceptions.RequestException as exc:
        log.warning("Health check error: %s", exc)
        return False


# ── 2. Context Extraction ─────────────────────────────────────────────────────
def collect_docker_logs() -> str:
    """Pull the last N log lines from the docker service."""
    try:
        result = subprocess.run(
            [
                "docker", "compose",
                "-f", DOCKER_COMPOSE_FILE,
                "logs", "--tail", str(LOG_TAIL_LINES),
                DOCKER_SERVICE_NAME,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        return output if output else "[no log output]"
    except FileNotFoundError:
        return "[docker not found on this host]"
    except subprocess.TimeoutExpired:
        return "[docker logs timed out]"
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to collect docker logs: %s", exc)
        return f"[log collection error: {exc}]"


def read_source_files() -> dict[str, str]:
    """Read each target source file from the local deploy path."""
    sources: dict[str, str] = {}
    for rel_path in TARGET_FILES:
        abs_path = Path(DEPLOY_PATH) / rel_path
        try:
            sources[rel_path] = abs_path.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("Cannot read %s: %s", abs_path, exc)
            sources[rel_path] = f"[file unreadable: {exc}]"
    return sources


# ── 3. Claude Diagnosis ───────────────────────────────────────────────────────
def _strip_code_fences(text: str) -> str:
    """Remove optional ```json ... ``` wrapping that a model might add."""
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\n?```\s*$", "", text.strip())
    return text.strip()


def call_claude(docker_logs: str, source_files: dict[str, str]) -> Optional[dict]:
    """
    Stream a diagnosis from Claude using adaptive thinking + prompt caching.
    Returns the parsed JSON dict on success, None on any failure.
    """
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY is not set — skipping Claude diagnosis")
        return None

    # Build the user message (volatile — not cached)
    sources_block = "\n\n".join(
        f"### {path}\n```python\n{code}\n```"
        for path, code in source_files.items()
    )
    user_content = (
        f"## Docker Error Logs (last {LOG_TAIL_LINES} lines)\n"
        f"```\n{docker_logs}\n```\n\n"
        f"## Current Source Files\n{sources_block}"
    )

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Stream the response so large source files don't hit timeouts.
        # get_final_message() waits for the full response automatically.
        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=16384,
            thinking={"type": "adaptive"},          # best reasoning for root-cause analysis
            system=[_SYSTEM_PROMPT_BLOCK],          # cached static block
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            final = stream.get_final_message()

        # Extract text from the response (thinking blocks are separate)
        raw = ""
        for block in final.content:
            if block.type == "text":
                raw = block.text
                break

        if not raw:
            log.error("Claude returned no text content")
            return None

        log.info(
            "Claude response: %d chars | cache_read=%s cache_write=%s",
            len(raw),
            getattr(final.usage, "cache_read_input_tokens", "n/a"),
            getattr(final.usage, "cache_creation_input_tokens", "n/a"),
        )

        clean = _strip_code_fences(raw)
        result = json.loads(clean)

        analysis = result.get("analysis", "—")
        log.info("Claude analysis: %s", analysis)
        return result

    except json.JSONDecodeError as exc:
        log.error("Claude returned invalid JSON: %s | raw snippet: %.300s", exc, raw)
        return None
    except anthropic.AuthenticationError:
        log.error("Claude API: invalid API key")
        return None
    except anthropic.RateLimitError as exc:
        retry_after = int(getattr(exc.response, "headers", {}).get("retry-after", "60"))
        log.error("Claude API: rate limited — retry after %ds", retry_after)
        return None
    except anthropic.APIStatusError as exc:
        log.error("Claude API error %d: %s", exc.status_code, exc.message)
        return None
    except anthropic.APIConnectionError as exc:
        log.error("Claude API connection error: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected Claude error: %s", exc)
        return None


# ── 4. GitHub Push ────────────────────────────────────────────────────────────
def push_fix_to_github(target_file: str, fixed_code: str, analysis: str) -> bool:
    """
    Commit the patched file to GitHub on GITHUB_BRANCH.
    Returns True on success; the CD pipeline will pick up the change automatically.
    """
    if not GITHUB_TOKEN:
        log.error("GITHUB_TOKEN not set — cannot push fix")
        return False
    if not GITHUB_REPO:
        log.error("GITHUB_REPO not set — cannot push fix")
        return False

    try:
        gh   = Github(GITHUB_TOKEN)
        repo = gh.get_repo(GITHUB_REPO)

        # Fetch current file to get its SHA (required by GitHub API for updates)
        try:
            contents = repo.get_contents(target_file, ref=GITHUB_BRANCH)
        except GithubException as exc:
            log.error("GitHub: could not fetch %s (branch=%s): %s", target_file, GITHUB_BRANCH, exc)
            return False

        commit_message = (
            "[Self-Healing] fix: auto-resolved server infrastructure error\n\n"
            f"Root cause: {analysis}\n"
            f"File:       {target_file}\n"
            f"Triggered:  {datetime.utcnow().isoformat()}Z\n"
            f"Branch:     {GITHUB_BRANCH}"
        )

        repo.update_file(
            path=target_file,
            message=commit_message,
            content=fixed_code,
            sha=contents.sha,
            branch=GITHUB_BRANCH,
        )
        log.info("GitHub: pushed fix to %s @ %s", target_file, GITHUB_BRANCH)
        return True

    except GithubException as exc:
        log.error("GitHub push failed: %s", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected GitHub error: %s", exc)
        return False


# ── Heal Sequence ─────────────────────────────────────────────────────────────
def run_heal_sequence() -> None:
    global _last_heal_attempt

    log.warning("=" * 60)
    log.warning("  HEAL SEQUENCE TRIGGERED — %s consecutive failures", FAILURE_THRESHOLD)
    log.warning("=" * 60)

    # Record attempt time FIRST so cooldown is enforced even on partial failures
    _last_heal_attempt = datetime.utcnow()

    # Step 1 — collect context
    log.info("[1/4] Collecting docker logs from '%s'…", DOCKER_SERVICE_NAME)
    docker_logs = collect_docker_logs()

    log.info("[2/4] Reading source files: %s", TARGET_FILES)
    source_files = read_source_files()

    # Step 2 — diagnose with Claude
    log.info("[3/4] Calling Claude (%s) for root-cause analysis…", CLAUDE_MODEL)
    result = call_claude(docker_logs, source_files)

    if result is None:
        log.error("Heal sequence aborted: Claude returned no result")
        return

    target_file = result.get("target_file")
    fixed_code  = result.get("fixed_code")
    analysis    = result.get("analysis", "unknown")

    if not target_file or not fixed_code:
        log.warning("Claude could not determine a safe fix — no commit will be made")
        return

    if target_file not in TARGET_FILES:
        log.warning(
            "Claude suggested '%s' which is not in TARGET_SOURCE_FILES — skipping push",
            target_file,
        )
        return

    # Step 3 — push to GitHub
    log.info("[4/4] Pushing fix for '%s' to GitHub (branch: %s)…", target_file, GITHUB_BRANCH)
    success = push_fix_to_github(target_file, fixed_code, analysis)

    if success:
        log.info("=" * 60)
        log.info("  HEAL SEQUENCE COMPLETE")
        log.info("  CD pipeline will rebuild and redeploy automatically.")
        log.info("  Next check in %d minutes (cooldown).", COOLDOWN_MINUTES)
        log.info("=" * 60)
    else:
        log.error("Heal sequence FAILED at GitHub push stage")


# ── Main Loop ─────────────────────────────────────────────────────────────────
def main() -> None:
    global _consecutive_failures

    log.info(
        "Aleph-One Watchdog starting | url=%s | interval=%ds | threshold=%d | cooldown=%dm",
        HEALTH_URL, CHECK_INTERVAL, FAILURE_THRESHOLD, COOLDOWN_MINUTES,
    )
    log.info("Target files: %s", TARGET_FILES)
    log.info("GitHub repo:  %s  branch: %s", GITHUB_REPO, GITHUB_BRANCH)

    while True:
        healthy = check_health()

        if healthy:
            if _consecutive_failures > 0:
                log.info("Service recovered after %d failure(s) ✓", _consecutive_failures)
            _consecutive_failures = 0
        else:
            _consecutive_failures += 1
            log.warning(
                "Failure %d/%d | url=%s",
                _consecutive_failures, FAILURE_THRESHOLD, HEALTH_URL,
            )

            if _consecutive_failures >= FAILURE_THRESHOLD:
                if _in_cooldown():
                    log.info(
                        "Cooldown active — %d min remaining before next heal attempt",
                        _cooldown_remaining_minutes(),
                    )
                else:
                    run_heal_sequence()
                    _consecutive_failures = 0  # reset so we don't immediately re-trigger

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
