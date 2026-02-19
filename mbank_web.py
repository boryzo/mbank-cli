#!/usr/bin/env python3
"""Flask web API for mbank-cli with /balances and /history endpoints."""
import functools, logging, os, sys, importlib.util, secrets
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, request
sys.path.insert(0, os.path.dirname(__file__))
spec = importlib.util.spec_from_file_location("mbank", os.path.join(os.path.dirname(__file__), "mbank-cli.py"))
mbank = importlib.util.module_from_spec(spec); spec.loader.exec_module(mbank)
app = Flask(__name__)
handler = RotatingFileHandler('mbank_web.log', maxBytes=1_000_000, backupCount=5)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
app.logger.addHandler(handler); app.logger.setLevel(logging.INFO)

def check_access(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        allowed = [ip.strip() for ip in (mbank.cfg_get('allowed_ips') or '').split(',') if ip.strip()]
        if allowed and request.remote_addr not in allowed:
            app.logger.warning(f"Forbidden IP: {request.remote_addr}"); return jsonify(error="Forbidden"), 403
        key, exp = request.headers.get('X-API-Key') or request.args.get('api_key') or '', mbank.cfg_get('apikey') or ''
        if not exp or not secrets.compare_digest(key, exp):
            app.logger.warning(f"Unauthorized: {request.path}"); return jsonify(error="Unauthorized"), 401
        return f(*args, **kwargs)
    return wrapper

@app.route('/balances')
@check_access
def balances():
    app.logger.info(f"REQ /balances {request.remote_addr}"); result = mbank.do_list(mbank.do_login())
    app.logger.info(f"RES /balances {len(result)} accounts"); return jsonify(balances=result)
@app.route('/history')
@check_access
def history():
    app.logger.info(f"REQ /history {request.remote_addr} {dict(request.args)}")
    r = mbank.do_history(mbank.do_login(), request.args.get('from'), request.args.get('to'), include_all=request.args.get('all')=='true')
    app.logger.info(f"RES /history {len(r)} rows"); return jsonify(history=r)

if __name__ == '__main__':
    mbank.opt_config = os.environ.get('MBANK_CONFIG') or os.path.join(mbank.xdg_config_home(), 'mbank-cli', 'config')
    mbank.initialize(); app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), threaded=False)
