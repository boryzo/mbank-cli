#!/usr/bin/env python3
import functools, logging, os, sys, importlib.util, secrets, time
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, request

# --- load mbank-cli.py as module ---
sys.path.insert(0, os.path.dirname(__file__))
spec = importlib.util.spec_from_file_location("mbank", os.path.join(os.path.dirname(__file__), "mbank-cli.py"))
mbank = importlib.util.module_from_spec(spec); spec.loader.exec_module(mbank)

app = Flask(__name__)

handler = RotatingFileHandler("mbank_web.log", maxBytes=1_000_000, backupCount=5)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# --- tiny in-memory cache ---
def _now() -> float: return time.time()

_session = {"value": None, "exp": 0.0}
_cache = {}  # key -> (exp_ts, value)

SESSION_TTL = int(os.environ.get("MBANK_SESSION_TTL", "600"))   # 10 min
BALANCES_TTL = int(os.environ.get("MBANK_BALANCES_TTL", "30"))  # 30 s
HISTORY_TTL  = int(os.environ.get("MBANK_HISTORY_TTL",  "30"))  # 30 s

def cache_get(key):
    exp, val = _cache.get(key, (0.0, None))
    if exp > _now(): return val
    _cache.pop(key, None)
    return None

def cache_set(key, val, ttl):
    _cache[key] = (_now() + ttl, val)
    return val

def get_session():
    if _session["value"] is not None and _session["exp"] > _now():
        return _session["value"]
    s = mbank.do_login()
    _session["value"] = s
    _session["exp"] = _now() + SESSION_TTL
    return s

def check_access(f):
    @functools.wraps(f)
    def w(*args, **kwargs):
        allowed = [ip.strip() for ip in (mbank.cfg_get("allowed_ips") or "").split(",") if ip.strip()]
        if allowed and request.remote_addr not in allowed:
            return jsonify(error="Forbidden"), 403

        expected = mbank.cfg_get("apikey") or ""
        key = request.headers.get("X-API-Key") or ""
        if not expected or not secrets.compare_digest(key, expected):
            return jsonify(error="Unauthorized"), 401

        return f(*args, **kwargs)
    return w

@app.get("/balances")
@check_access
def balances():
    cached = cache_get("balances")
    if cached is not None:
        return jsonify(balances=cached, cached=True)

    s = get_session()
    res = mbank.do_list(s)
    return jsonify(balances=cache_set("balances", res, BALANCES_TTL), cached=False)

@app.get("/history")
@check_access
def history():
    fr = request.args.get("from")
    to = request.args.get("to")
    all_ = (request.args.get("all") == "true")
    key = f"history:{fr}:{to}:{all_}"

    cached = cache_get(key)
    if cached is not None:
        return jsonify(history=cached, cached=True)

    s = get_session()
    res = mbank.do_history(s, fr, to, include_all=all_)
    return jsonify(history=cache_set(key, res, HISTORY_TTL), cached=False)

if __name__ == "__main__":
    mbank.opt_config = os.environ.get("MBANK_CONFIG") or os.path.join(mbank.xdg_config_home(), "mbank-cli", "config")
    mbank.initialize()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), threaded=False)
