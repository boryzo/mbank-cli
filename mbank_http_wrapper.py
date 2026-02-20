#!/usr/bin/env python3
"""Simple HTTP wrapper for mbank-cli.py.

Endpoints:
- GET/POST /accounts -> runs: mbank-cli.py list
- GET/POST /history  -> runs: mbank-cli.py history --all

Security:
- API key required (header X-API-Key, query ?api_key=..., or POST body api_key)
- IP allow/deny filtering
"""

from __future__ import annotations

from collections import deque
import ipaddress
import hmac
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request

app = Flask(__name__)

SCRIPT_PATH = Path(os.environ.get("MBANK_WRAPPER_SCRIPT", Path(__file__).with_name("mbank-cli.py")))
PYTHON_BIN = os.environ.get("MBANK_WRAPPER_PYTHON", sys.executable)
WORKDIR = Path(os.environ.get("MBANK_WRAPPER_CWD", SCRIPT_PATH.parent))
API_KEY = os.environ.get("MBANK_WRAPPER_API_KEY", "")
TIMEOUT_SEC = int(os.environ.get("MBANK_WRAPPER_TIMEOUT", "180"))
TRUST_XFF = os.environ.get("MBANK_WRAPPER_TRUST_XFF", "0") == "1"
RATE_LIMIT_COUNT = int(os.environ.get("MBANK_WRAPPER_RATE_LIMIT_COUNT", "2"))
RATE_LIMIT_WINDOW_SEC = int(os.environ.get("MBANK_WRAPPER_RATE_LIMIT_WINDOW_SEC", "10"))

ALLOW_IPS_RAW = os.environ.get("MBANK_WRAPPER_ALLOW_IPS", "").strip()
DENY_IPS_RAW = os.environ.get("MBANK_WRAPPER_DENY_IPS", "").strip()

# Prevent concurrent runs that could fight over session/cookies.
_command_lock = threading.Lock()
_rate_limit_lock = threading.Lock()
_rate_limit_hits: dict[str, deque[float]] = {}


def _parse_networks(value: str) -> list[ipaddress._BaseNetwork]:
    out: list[ipaddress._BaseNetwork] = []
    if not value:
        return out
    for item in value.split(","):
        token = item.strip()
        if not token:
            continue
        if "/" not in token:
            token = f"{token}/32" if ":" not in token else f"{token}/128"
        out.append(ipaddress.ip_network(token, strict=False))
    return out


ALLOW_NETWORKS = _parse_networks(ALLOW_IPS_RAW)
DENY_NETWORKS = _parse_networks(DENY_IPS_RAW)


def _client_ip() -> str:
    if TRUST_XFF:
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",", 1)[0].strip()
    return (request.remote_addr or "").strip()


def _ip_allowed(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False

    for net in DENY_NETWORKS:
        if ip in net:
            return False

    if ALLOW_NETWORKS:
        return any(ip in net for net in ALLOW_NETWORKS)

    return True


def _extract_api_key() -> str:
    return (
        request.headers.get("X-API-Key")
        or request.args.get("api_key")
        or request.form.get("api_key")
        or ((request.get_json(silent=True) or {}).get("api_key") if request.is_json else None)
        or ""
    )


def _rate_limit_ok(client_key: str) -> bool:
    if RATE_LIMIT_COUNT <= 0 or RATE_LIMIT_WINDOW_SEC <= 0:
        return True

    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SEC
    with _rate_limit_lock:
        hits = _rate_limit_hits.setdefault(client_key, deque())
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= RATE_LIMIT_COUNT:
            return False
        hits.append(now)
        return True


def _auth_check() -> tuple[bool, Response | None, int]:
    if not API_KEY:
        return False, jsonify({"error": "Server misconfigured: MBANK_WRAPPER_API_KEY is empty"}), 500

    ip_text = _client_ip()
    if not _ip_allowed(ip_text):
        return False, jsonify({"error": "Forbidden IP", "ip": ip_text}), 403

    if not _rate_limit_ok(ip_text):
        resp = jsonify({"error": f"Too many requests: max {RATE_LIMIT_COUNT} per {RATE_LIMIT_WINDOW_SEC}s"})
        resp.headers["Retry-After"] = str(RATE_LIMIT_WINDOW_SEC)
        return False, resp, 429

    supplied = _extract_api_key()
    if not hmac.compare_digest(supplied, API_KEY):
        return False, jsonify({"error": "Unauthorized"}), 401

    return True, None, 200


def _run_cli(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [PYTHON_BIN, str(SCRIPT_PATH), *args],
        cwd=str(WORKDIR),
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SEC,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _run_fixed_command(args: list[str]):
    ok, err, code = _auth_check()
    if not ok:
        return err, code

    if not _command_lock.acquire(blocking=False):
        return jsonify({"error": "Another command is running. Try again in a few seconds."}), 429

    try:
        try:
            exit_code, stdout, stderr = _run_cli(args)
        except subprocess.TimeoutExpired:
            return jsonify({"error": f"Command timeout after {TIMEOUT_SEC}s"}), 504

        if exit_code == 0:
            resp = Response(stdout, status=200, mimetype="text/plain")
            resp.headers["X-Exit-Code"] = "0"
            return resp

        # Keep exact CLI errors visible when command fails.
        body = stderr if stderr else stdout
        resp = Response(body, status=502, mimetype="text/plain")
        resp.headers["X-Exit-Code"] = str(exit_code)
        return resp
    finally:
        _command_lock.release()


@app.route("/accounts", methods=["GET", "POST"])
def accounts():
    return _run_fixed_command(["list"])


@app.route("/history", methods=["GET", "POST"])
def history_all():
    return _run_fixed_command(["history", "--all"])


if __name__ == "__main__":
    host = os.environ.get("MBANK_WRAPPER_HOST", "127.0.0.1")
    port = int(os.environ.get("MBANK_WRAPPER_PORT", "8787"))
    app.run(host=host, port=port)
