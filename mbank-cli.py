#!/usr/bin/env python3
# Python port of the original mbank-cli by Jakub Wilk.
# Original project: https://github.com/jwilk/mbank-cli

import argparse
import getpass
import gzip
import http.cookiejar
import json
import locale
import os
import re
import ssl
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

opt_verbose = False
opt_debug_dir = None
opt_debug_interactive = False

ua = None
global_config = None

mbank_host = None
root_url = None
base_url = None

opt_config = None
opt_cookie_jar = None

browser_user_agent = 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128'
browser_name = 'Firefox'
browser_version = '128'
# Static value copied from Perl original.
browser_dfp = 'eJyFkT1MFEEUx/dm/NhsUJcj4PmZDYUxJOgFDSEkhg89UDmQ4AfEZpzdnbubcXdnM7MHh9XaGSs7LCwsKYkVJYUFhSaUlMTExMpYUFyns3u35AiiL9ndt//fe/PmvWf0Gl1lGtQbVmNkGA3fzsOnczMFLX9NbxrmPiw0DWsfXm8axX04mi96OHClg0MyGArqY7F68YQBSNA/pX/eBXmdNEKPOjQqAAsM6DIk+CURspgb0UqasvuxOR/rS99+ty334sOB63/9Uh4buDOudcUqckv7v8VHlCFj/t6U9YySFSKGuu/WBPeJ1SH1pBKt+53ihVnqCC55JbJKbvVw/CKxZ2hk2XXqRYM0SNioNv56be3TmYendM3UCtoCnLs5kb6e543Ts/wV9TyczxxbY30Tc9PlEqKBjHDgEBdhIfCqZGZp6QmyPRK4yKeBjxvsUqI43OMC2fVKhQhUw14FVTyOI3YuganbSmJnU0HgKnJJGNVYX/Iva9hVeRFpRHVBkMddpqf6wvQku5x4GXK4HwoiJeUBssPIOZ6KqqJXO2lFjUNVwQGVPBI8pA7re1R6jIhHfBJEqleXNFCdBhHrTfSKzZFQd1Y5Pg19HLJCIicDcbFwVQOCLuOILhPJuhNyUChtvXBEQh4NCBatqhnpGNaVv+tZ2vkELxOhIlrbQNxmxFGVFkuT0+XDO2ifmJHWXNQas+OxTIZ3LCaKHp8sbync/0+MpKjarKcVk646wyzfFgVead9WZprHZbLFIAkVD9aBvgH0TaBvAX0bFHaAtgticw+YP9TnF9jLNYEew9h8A/V30HwP9Y8wBuswtwFzmzC3Bce2YWztqOdt7uT3n3Dzxh8LG3RL'

country_to_language = {'cz': 'cs', 'pl': 'pl', 'sk': 'sk'}
known_countries = sorted(country_to_language.keys())

header_xhr = {'X-Requested-With': 'XMLHttpRequest'}
header_accept_json = {'Accept': 'application/json, text/javascript, */*; q=0.01'}

account_number_re = re.compile(r'''\d{2}(?:[ ]\d{4}){6}|CZ\d{2}(?:[ ]\d{4}){5}|SK\d{2}(?:[ ]\d{4}){5}|(?:\d{1,6}-)?\d{2,10}/\d{4}''', re.VERBOSE)
uuid_re = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


def write_log(msg):
    if not opt_debug_dir:
        return
    path = os.path.join(opt_debug_dir, 'log')
    with open(path, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def debug(msg):
    msg = f'* {msg}'
    write_log(msg)
    if opt_verbose:
        print(msg, file=sys.stderr)


def warning(msg):
    if msg is None:
        return
    write_log(msg)
    print(f'mbank-cli: {msg}', file=sys.stderr)


def user_error(msg):
    warning(msg)
    sys.exit(1)


def server_error(msg=None):
    if msg:
        warning(msg)
    sys.exit(2)


def scraping_error(msg):
    write_log(f'Scraping error: {msg}')
    traceback.print_stack()
    print(f'Scraping error: {msg}', file=sys.stderr)
    sys.exit(3)


def internal_error(msg):
    write_log(f'Internal error: {msg}')
    traceback.print_stack()
    print(f'Internal error: {msg}', file=sys.stderr)
    sys.exit(255)


def os_error(msg):
    write_log(msg)
    traceback.print_stack()
    print(msg, file=sys.stderr)
    sys.exit(4)


def first_defined(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


def unicode_display(s):
    if s is None:
        return ''
    return str(s)


def quote(x):
    if isinstance(x, re.Pattern):
        p = x.pattern.replace('/', r'\/')
        return f'/{p}/'
    return json.dumps(x, ensure_ascii=True)


def match(text, pattern, context=None):
    if isinstance(pattern, str):
        pattern = re.compile(re.escape(pattern))
    if not isinstance(pattern, re.Pattern):
        internal_error('match(): invalid pattern')
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        text = str(text)
    if not isinstance(text, str):
        scraping_error(f'{context}: {quote(text)} is not a string')
    if not pattern.fullmatch(text):
        scraping_error(f'{context}: {quote(text)} does not match {quote(pattern)}')
    return text


def no_match(text, context=None):
    return match(text, re.compile(r'(?!)'), context=context)


def check_type(obj, template, context=None):
    expected = type(template)
    if type(obj) is not expected:
        if expected is dict:
            scraping_error(f'{context}: not an object')
        if expected is list:
            scraping_error(f'{context}: not an array')
        internal_error('check_type(): unknown template type')
    return obj


def parse_uuid(s):
    if not isinstance(s, str):
        return None
    return s if uuid_re.fullmatch(s) else None


def match_uuid(s, context=None):
    v = parse_uuid(s)
    if v:
        return v
    return no_match(s, context=context)


def timestamp_to_date(ts, time_must_be=None):
    if not ts:
        return None
    m = re.match(r'^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}(?:\.\d+)?)(?:[+-]\d{2}:\d{2})?$', str(ts))
    if not m:
        return None
    d, t = m.groups()
    if time_must_be == 0 and not re.fullmatch(r'[0:.]+', t):
        return None
    try:
        if datetime.strptime(d, '%Y-%m-%d').strftime('%Y-%m-%d') != d:
            return None
    except Exception:
        return None
    return d


def format_account_number(number):
    if number is None:
        return ''
    return str(number).replace('PL', '', 1).replace(' ', '')


def format_money(number, currency):
    if number is None:
        return ''
    if currency is None:
        return ''
    currency = str(currency).strip()
    if not re.fullmatch(r'[A-Z]{3}', currency):
        return ''
    txt = str(number).replace('\xa0', ' ').replace(' ', '').replace(',', '.')
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', txt):
        return ''
    try:
        return f'{float(txt):.2f} {currency}'
    except Exception:
        return ''


def get_tz_country_guess():
    try:
        loc = locale.getlocale()[0] or ''
    except Exception:
        return None
    if '_' not in loc:
        return None
    cc = loc.split('_', 1)[1].lower()
    return cc if cc in country_to_language else None


def expand_tilde(path):
    return os.path.expanduser(path) if path.startswith('~') else path


def unexpand_tilde(path):
    home = os.path.expanduser('~')
    return '~' + path[len(home):] if path.startswith(home) else path


def xdg_config_home():
    return os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')


def xdg_data_home():
    return os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')


def makedirs(path):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        os_error(f'{path}: {e}')


def read_config(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return _read_config(fh, path)
    except OSError as e:
        os_error(f'{path}: {e}')


def _read_config(fh, path):
    cfg = {'__path__': path}
    for line in fh:
        line = line.rstrip('\n')
        if re.fullmatch(r'(?:#.*)?\s*', line):
            continue
        m = re.match(r'^\s*([\w-]+)\s+(.*\S)\s*$', line)
        if not m:
            config_error(f'syntax error: {line}', config=path)
        k, v = m.groups()
        k = k.lower()
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        cfg[k] = v
    return cfg


def get_config_var(name, default=None):
    return global_config.get(name, default)


def config_error(msg, config=None):
    cfg = config if config is not None else global_config
    if isinstance(cfg, dict):
        path = cfg.get('__path__', 'config')
    else:
        path = cfg
    user_error(f'{path}: {msg}')


def _decode_http_content(raw, headers):
    enc = headers.get('Content-Encoding', '')
    if enc == 'gzip':
        raw = gzip.decompress(raw)
    elif enc == 'deflate':
        import zlib
        raw = zlib.decompress(raw)
    return raw.decode('utf-8', errors='replace').replace('\r', '')


def http_init(cookie_jar_path, ca_path=None):
    global ua
    for k in list(os.environ.keys()):
        if k.startswith('HTTPS_'):
            del os.environ[k]

    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if ca_path:
        ctx.load_verify_locations(cafile=ca_path)

    if cookie_jar_path and cookie_jar_path != '/dev/null':
        cj = http.cookiejar.MozillaCookieJar(cookie_jar_path)
        try:
            cj.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
    else:
        cj = http.cookiejar.CookieJar()

    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPCookieProcessor(cj),
    )
    opener.addheaders = [
        ('User-Agent', browser_user_agent),
        ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
        ('Accept-Encoding', 'gzip, deflate'),
        ('Accept-Language', 'en-US,en;q=0.5'),
    ]
    opener.cookie_jar = cj
    ua = opener


def download(request, ignore_errors=None):
    if ignore_errors is None:
        ignore_errors = []

    method = request.get_method()
    url = request.full_url
    debug(f'{method} {url}')

    if opt_debug_interactive:
        ok = input(f'Proceed {method} {url}? [y] ') or 'y'
        if ok != 'y':
            user_error('aborted by user')

    try:
        resp = ua.open(request, timeout=60)
        content = _decode_http_content(resp.read(), resp.headers)
        return {'response': resp, 'content': content, 'url': resp.geturl()}
    except urllib.error.HTTPError as e:
        if e.code in ignore_errors:
            try:
                content = _decode_http_content(e.read(), e.headers)
            except Exception:
                content = ''
            return {'response': e, 'content': content, 'url': url}
        msg = f'HTTP error {e.code} on <{method} {url}>'
        write_log(msg)
        traceback.print_stack()
        print(msg, file=sys.stderr)
        server_error()


def simple_download(request):
    try:
        return ua.open(request, timeout=60)
    except urllib.error.HTTPError as e:
        msg = f'HTTP error {e.code} on <{request.get_method()} {request.full_url}>'
        write_log(msg)
        traceback.print_stack()
        print(msg, file=sys.stderr)
        server_error()


def decode_json(text, context=None, type_template=None):
    if type_template is None:
        type_template = {}
    try:
        obj = json.loads(text)
    except Exception as e:
        scraping_error(f'{context}: {e}')
    return check_type(obj, type_template, context=context)


def initialize():
    global global_config, mbank_host, root_url, base_url

    if not os.path.exists(opt_config):
        user_error(
            f'missing configuration file: {opt_config}\n'
            'Run "mbank-cli configure" or create the configuration file manually.'
        )

    global_config = read_config(opt_config)

    cookie_jar_path = opt_cookie_jar or get_config_var('cookiejar')
    if not cookie_jar_path:
        config_error('missing cookiejar')
    cookie_jar_path = expand_tilde(cookie_jar_path)
    debug(f'cookiejar = {cookie_jar_path}')

    ca_path = get_config_var('cafile')
    if ca_path:
        ca_path = expand_tilde(ca_path)
        if not os.path.isfile(ca_path):
            os_error(f'{ca_path}: file not found')

    country = (get_config_var('country') or '').lower()
    if not country:
        config_error('missing country')
    lang = country_to_language.get(country)
    if not lang:
        user_error(f"unknown country {country.upper()}, not in {', '.join(known_countries).upper()}")

    mbank_host = f'online.mbank.{country}'
    root_url = f'https://{mbank_host}'
    base_url = f'https://{mbank_host}/{lang}'

    http_init(cookie_jar_path=cookie_jar_path, ca_path=ca_path)


def parse_args():
    global opt_verbose, opt_debug_dir, opt_debug_interactive, opt_config, opt_cookie_jar

    parser = argparse.ArgumentParser(prog='mbank-cli', add_help=False)
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--debug', metavar='DIR')
    parser.add_argument('--debug-interactive', action='store_true')
    parser.add_argument('--config', metavar='FILE')
    parser.add_argument('--cookie-jar', metavar='FILE')
    parser.add_argument('-h', '--help', action='store_true')
    parser.add_argument('--version', action='store_true')
    parser.add_argument('command', nargs='?')
    parser.add_argument('args', nargs='*')

    try:
        args = parser.parse_args()
    except SystemExit:
        user_error('Invalid arguments')

    if args.help:
        print('''Usage: mbank-cli [OPTIONS] COMMAND [ARGS...]\n\nOptions:\n  --verbose\n  --debug DIR\n  --debug-interactive\n  --config FILE\n  --cookie-jar FILE\n  -h, --help\n  --version\n\nCommands:\n  list\n  logout\n  register-device\n  activate-profile\n  configure''')
        sys.exit(0)

    if args.version:
        print('mbank-cli python-port')
        sys.exit(0)

    opt_verbose = args.verbose
    opt_debug_interactive = args.debug_interactive
    opt_config = args.config or os.path.join(xdg_config_home(), 'mbank-cli', 'config')
    opt_cookie_jar = args.cookie_jar

    if args.debug:
        if args.debug.startswith('-'):
            user_error(f'suspicious directory name for --debug: {args.debug}')
        makedirs(args.debug)
        opt_debug_dir = args.debug

    return (args.command or 'list'), args.args


def extract_js_object_assignment(content, var_name):
    pos = content.find(var_name)
    if pos < 0:
        return None
    eq = content.find('=', pos + len(var_name))
    if eq < 0:
        return None
    start = content.find('{', eq + 1)
    if start < 0:
        return None

    depth = 0
    in_str = False
    quote_ch = ''
    esc = False
    for i in range(start, len(content)):
        ch = content[i]
        if in_str:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == quote_ch:
                in_str = False
            continue
        if ch in ('"', "'"):
            in_str = True
            quote_ch = ch
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return content[start:i + 1]
    return None


def extract_login_profiles(page_content):
    profiles = {'personal': [], 'business': []}

    for m in re.finditer(r'<script\b[^>]*>(.*?)</script>', page_content, re.IGNORECASE | re.DOTALL):
        payload = extract_js_object_assignment(m.group(1), 'Ebre.Venezia.ProfileData')
        if not payload:
            continue
        data = decode_json(payload, context='login.profiles.json')
        for key, value in data.items():
            if key == 'iProfiles':
                key = 'personal'
            elif key == 'fProfiles':
                key = 'business'
            else:
                no_match(key, context='login.profiles.key')

            if not isinstance(value, dict):
                scraping_error(f'login.profiles.{key}: not an object')
            arr = value.get('profiles', [])
            if not isinstance(arr, list):
                scraping_error(f'login.profiles.{key}.profiles: not an array')

            n = 0
            for p in arr:
                if not isinstance(p, dict):
                    scraping_error(f'login.profiles.{key}.profile: not an object')
                code = match(p.get('profileCode', ''), re.compile(r'.+'), context='login.profiles.profile-code')
                profiles[key].append(code)
                n += 1
                name = match(p.get('firmName', ''), re.compile(r'.+'), context='login.profiles.company-name') if key == 'business' else f'{key}/{code}'
                profiles.setdefault(name, []).append(code)
            if n > 1:
                profiles.pop(key, None)
        break

    return profiles


def clear_temp_cookies():
    debug('clearing temporary cookies')
    if ua and hasattr(ua, 'cookie_jar'):
        ua.cookie_jar.clear_session_cookies()


def get_cookie(name):
    if not ua or not hasattr(ua, 'cookie_jar'):
        return None
    out = None
    for c in ua.cookie_jar:
        if c.name != name:
            continue
        if (c.domain or '').lstrip('.') == mbank_host:
            out = c
    return out


def unexpire_cookie(name, context=None):
    c = get_cookie(name)
    if c is None:
        scraping_error(f'{context or "cookie"}: cookie {name} missing')
    if c.expires is None or c.discard:
        c.expires = int(1e10)
        c.discard = False


def get_tabid():
    c = get_cookie('mBank_tabId')
    if c is None:
        scraping_error('login.tabid')
    return match_uuid(c.value, context='login.tabid')


def ask_sms_password(date, n, try_num):
    if try_num == 0:
        return None
    if try_num > 1:
        print(f'(try #{try_num})', file=sys.stderr)
    return input(f'SMS password from {date} (operation #{n}): ')


def do_2fa(device_to_add=None):
    hdr = {
        'Origin': root_url,
        'Referer': f'{root_url}/connect/Login',
        'Content-Type': 'application/json; charset=UTF-8',
    }

    dfp = get_config_var('dfp') or browser_dfp
    req = urllib.request.Request(
        f'{root_url}/signin/connect/api/sca',
        data=json.dumps({'dfp': dfp}).encode('utf-8'),
        headers=hdr,
        method='POST',
    )
    doc = download(req)
    unexpire_cookie('mBank8', context='login.sca.cookie')

    data = decode_json(doc['content'], context='login.sca')
    sca_status = match(data.get('imsStatus', ''), re.compile(r'(Is|Not)Trusted|Suspicious'), context='login.sca.status')
    limit_exceeded = data.get('maximumNumberOfDevicesExceeded')
    if not isinstance(limit_exceeded, bool):
        no_match(limit_exceeded, context='login.sca.limit')

    if sca_status == 'IsTrusted':
        if device_to_add:
            user_error('device already registered')
        return match_uuid(data.get('token', ''), context='login.sca.token')

    mod_data = {
        'authorizationAction': 1,
        'browserName': browser_name,
        'browserVersion': browser_version,
        'deviceName': f'Komputer Linux {browser_name}',
        'osName': 'Linux',
        'dfp': dfp,
    }

    if device_to_add:
        if sca_status != 'NotTrusted':
            user_error('device already registered')
        if limit_exceeded:
            user_error('too many registered devices')
        while True:
            req = urllib.request.Request(
                f'{root_url}/signin/connect/api/sca/uniqueDevice',
                data=json.dumps({'deviceName': device_to_add}).encode('utf-8'),
                headers=hdr,
                method='POST',
            )
            uniq = decode_json(download(req)['content'], context='login.sca.unique-dev')
            if uniq.get('isUnique'):
                break
            print('Device name has been rejected. Try another one.', file=sys.stderr)
            new_name = input('Device name: ').strip()
            if len(new_name) > 1:
                device_to_add = new_name
        mod_data['authorizationAction'] = 2
        mod_data['deviceName'] = device_to_add

    req = urllib.request.Request(
        f'{root_url}/signin/connect/api/mediator/initialize',
        data=json.dumps({'moduleData': mod_data, 'moduleId': 'IB20'}).encode('utf-8'),
        headers=hdr,
        method='POST',
    )
    init = decode_json(download(req)['content'], context='login.2fa.init')
    auth = init.get('authorizationData', {})

    mode = match(auth.get('authorizationType', ''), re.compile(r'\w+'), context='login.2fa.init.auth-type')
    auth_id = match_uuid(auth.get('authorizationId', ''), context='login.2fa.init.auth-id')
    auth_date_raw = auth.get('authorizationDate', '')
    auth_date = timestamp_to_date(auth_date_raw)
    if auth_date is None:
        scraping_error(f'login.2fa.init.operation-date: {auth_date_raw}')
    auth_no = match(auth.get('authorizationNumber', ''), re.compile(r'\d+'), context='login.2fa.init.operation-no')

    if mode == 'MA':
        print(f'Waiting for confirmation of operation no {auth_no} from {auth_date} in the mobile app...', file=sys.stderr)
        while True:
            req = urllib.request.Request(
                f'{root_url}/signin/connect/api/mediator/status',
                data=json.dumps({'authorizationId': auth_id}).encode('utf-8'),
                headers=hdr,
                method='POST',
            )
            doc = download(req)
            if doc['response'].status == 204:
                status = '_'
                data = {}
            else:
                data = decode_json(doc['content'], context='login.2fa.status')
                status = data.get('authorizationStatus', '')
            debug(f'2FA mobile auth: {status}')
            if status == '_':
                time.sleep(1)
            elif status == 'Authorized':
                return match_uuid((data.get('postResult') or {}).get('token', ''), context='login.2fa.status.token')
            elif status == 'Canceled':
                user_error('login failed: rejected mobile authentication request')
            elif status == 'TimeOut':
                user_error('login failed: mobile authentication request timed out')
            else:
                scraping_error(f'login.2fa.status.status: {status}')

    if mode == 'SMS':
        i = 1
        while True:
            sms_password = ask_sms_password(auth_date, auth_no, i)
            req = urllib.request.Request(
                f'{root_url}/signin/connect/api/mediator/authorize',
                data=json.dumps({
                    'authorizationCode': sms_password,
                    'authorizationId': auth_id,
                    'authorizationType': mode,
                }).encode('utf-8'),
                headers=hdr,
                method='POST',
            )
            data = decode_json(download(req, ignore_errors=[422])['content'], context='login.2fa.exec')
            token = (data.get('postResult') or {}).get('token')
            if token:
                return match_uuid(token, context='login.2fa.exec.token')
            if (data.get('type') or '') == 'AuthApi-SMS014':
                print('Incorrect SMS password', file=sys.stderr)
                i += 1
                continue
            no_match(data.get('type'), context='login.2fa.exec.error')

    no_match(mode, context='login.2fa.init.auth-mode')


def do_login(probe=False, register_device=None):
    req = urllib.request.Request(base_url)
    doc = download(req)

    if '/Login' in doc['url']:
        if probe:
            debug('not logged in')
            return None

        clear_temp_cookies()
        debug('logging in...')

        lang_m = re.search(r'/(\w\w)$', base_url)
        lang = lang_m.group(1) if lang_m else 'pl'

        m = re.search(
            rf"'/signin/connect/authorize\?ui_locales={lang}&(request_uri=urn%3aietf%3aparams%3aoauth%3arequest_uri%3a[0-9A-F]+&client_id=Ib)'",
            doc['content'],
        )
        if not m:
            scraping_error('login.return-url')

        return_url = m.group(1).replace('%3a', '%3A')
        return_url = f'/signin/connect/authorize/callback?{return_url}&suppressed_prompt=login'

        login = get_config_var('login')
        if not login:
            config_error('missing login')

        password = get_config_var('password')
        if not password:
            pm = get_config_var('passwordmanager')
            if pm:
                import subprocess
                try:
                    r = subprocess.run(['sh', '-c', pm], capture_output=True, text=True, check=True)
                    password = (r.stdout or '').split('\n')[0]
                except Exception:
                    os_error('password manager failed')
            elif sys.stdin.isatty():
                password = term_readpasswd('Password: ')
            else:
                config_error('missing password')

        if not password:
            user_error('login failed: empty password')

        if get_config_var('smsinbox'):
            ask_sms_password('2006-07-30', 1, 0)

        hdr = {'Origin': root_url, 'Referer': f'{root_url}/connect/Login', 'Content-Type': 'application/json; charset=UTF-8'}

        req = urllib.request.Request(
            f'{root_url}/signin/connect/api/users/prelogin',
            data=json.dumps({'language': lang, 'login': login, 'password': password, 'returnUrl': return_url}).encode('utf-8'),
            headers=hdr,
            method='POST',
        )
        data = decode_json(download(req, ignore_errors=[422])['content'], context='login.prelogin.json')
        if data.get('type') != 'PreLoginResponse':
            user_error(f"login failed: {data.get('detail', '')}")

        token = do_2fa(register_device)

        req = urllib.request.Request(
            f'{root_url}/signin/connect/api/users/finallogin',
            data=json.dumps({'language': lang.capitalize(), 'returnUrl': return_url, 'token': token}).encode('utf-8'),
            headers=hdr,
            method='POST',
        )
        final = decode_json(download(req)['content'], context='login.final')
        return_url = match(final.get('returnUrl', ''), re.compile(r'/.+'), context='login.final.return-url')

        doc = download(urllib.request.Request(f'{root_url}{return_url}'))
        doc = download(urllib.request.Request(base_url))

    tabid = get_tabid()
    content = doc['content']

    if re.search(r'<header\b[^>]*class=["\'][^"\']*\btech-break\b', content, re.IGNORECASE):
        server_error('service is temporarily unavailable')

    csrf_token = None
    for m in re.finditer(r'<meta\b[^>]*>', content, re.IGNORECASE):
        tag = m.group(0)
        name_m = re.search(r'name=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if not name_m or name_m.group(1) != '__AjaxRequestVerificationToken':
            continue
        c_m = re.search(r'content=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if c_m:
            csrf_token = c_m.group(1)
            break

    if not csrf_token or len(csrf_token) < 20:
        scraping_error('login.csrf-token: invalid token')

    profiles = extract_login_profiles(content)

    debug('logged in')
    headers = {'Referer': doc['url'], 'X-Tab-Id': tabid, 'X-Request-Verification-Token': csrf_token, **header_xhr}
    return {'headers': headers, 'csrf_token': csrf_token, 'profiles': profiles, 'url': doc['url']}


def normalize_mbank_account(raw):
    if not isinstance(raw, dict):
        scraping_error('list.mbank.account: not an object')
    name = match(raw.get('ProductName', ''), re.compile(r'.+'), context='list.product-name')
    subtitle = raw.get('SubTitle', '')
    if subtitle:
        name += f' - {subtitle}'
    number = format_account_number(match(raw.get('AccountNumber', ''), account_number_re, context='list.account-number'))
    return {
        'name': name,
        'number': number,
        'balance': raw.get('Balance'),
        'available': raw.get('AvailableBalance'),
        'currency': first_defined(raw.get('Currency'), ''),
        'source': 'mbank',
    }


def normalize_external_account(raw):
    if not isinstance(raw, dict):
        return None
    name = first_defined(raw.get('name'), raw.get('productName'), raw.get('ProductName'), raw.get('externalAccountName'), raw.get('accountTypeName'))
    number = first_defined(raw.get('number'), raw.get('accountNumber'), raw.get('iban'), raw.get('Iban'))
    if not name or not number:
        return None
    source = first_defined(raw.get('bankName'), raw.get('providerName'), raw.get('provider'), 'external')
    currency = first_defined(raw.get('currency'), raw.get('Currency'), '')
    currency = '' if currency is None else str(currency)
    if currency and not re.fullmatch(r'[A-Z]{3}', currency):
        currency = ''
    return {
        'name': str(name),
        'number': format_account_number(str(number)),
        'balance': first_defined(raw.get('balance'), raw.get('Balance')),
        'available': first_defined(raw.get('availableBalance'), raw.get('AvailableBalance')),
        'currency': currency,
        'source': str(source) if source else 'external',
    }


def parse_offline_accounts(text):
    try:
        data = json.loads(text)
    except Exception:
        return []

    if isinstance(data, list):
        account_list = data
    elif isinstance(data, dict):
        account_list = first_defined(data.get('payload'), data.get('accounts'), data.get('Accounts'), [])
    else:
        return []

    if not isinstance(account_list, list):
        return []

    out = []
    for raw in account_list:
        n = normalize_external_account(raw)
        if n is not None:
            out.append(n)
    return out


def fetch_offline_accounts(login_info):
    url = f'{root_url}/api/AccountsAggregation/Accounts/accounts/Offline'
    headers = {**login_info['headers'], **header_accept_json}

    try:
        req = urllib.request.Request(url, data=json.dumps({}).encode('utf-8'), headers=headers, method='POST')
        doc = download(req, ignore_errors=[404, 405])
        if doc['response'].status in (404, 405):
            doc = download(urllib.request.Request(url, headers=headers), ignore_errors=[404, 405])
            if doc['response'].status in (404, 405):
                return []
        if 200 <= doc['response'].status < 300:
            return parse_offline_accounts(doc['content'])
    except Exception:
        pass
    return []


def do_list(login=None, quiet=False):
    if not login:
        user_error('Not logged in')

    headers = {**login['headers'], **header_accept_json, 'Content-Type': 'application/json; charset=UTF-8'}
    req = urllib.request.Request(
        f'{base_url}/MyDesktop/Desktop/GetAccountsList',
        data=json.dumps({}).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    json_data = decode_json(download(req)['content'], context='list.json')
    accounts = check_type(json_data.get('accountDetailsList'), [], context='list.accounts')

    result = []
    for raw in accounts:
        a = normalize_mbank_account(raw)
        result.append({'name': a['name'], 'number': a['number'], 'source': a['source']})
        if not quiet:
            print(f"{unicode_display(a['name'])};{a['number']};{format_money(a.get('balance'), a.get('currency'))};{format_money(a.get('available'), a.get('currency'))};{a['source']}")

    for a in fetch_offline_accounts(login):
        result.append({'name': a['name'], 'number': a['number'], 'source': a['source']})
        if not quiet:
            print(f"{unicode_display(a['name'])};{a['number']};{format_money(a.get('balance'), a.get('currency'))};{format_money(a.get('available'), a.get('currency'))};{unicode_display(a['source'])}")

    return result


def do_lazy_logout(login=None):
    if not login:
        internal_error('do_lazy_logout(): missing login')

    headers = {**login['headers'], **header_accept_json, 'Content-Type': 'application/json'}
    req = urllib.request.Request(f'{base_url}/LoginMain/Account/LazyLogout', data=b'', headers=headers, method='POST')
    data = decode_json(download(req)['content'], context='logout.json')
    if not data.get('lazy'):
        scraping_error('logout.lazy')


def do_logout(maybe=False):
    login = do_login(probe=True)
    if not login:
        clear_temp_cookies()
        if maybe:
            return
        user_error('logout: the user was not logged in')

    debug('logging out...')
    do_lazy_logout(login=login)
    req = urllib.request.Request(f'{base_url}/LoginMain/Account/Logout', headers={'Referer': login['url']}, method='GET')
    simple_download(req)
    debug('successful logout')
    clear_temp_cookies()


def cookiejar_sanity_check_for_register_device():
    if not ua or not hasattr(ua, 'cookie_jar'):
        user_error('missing cookie jar')

    cj = ua.cookie_jar
    path = getattr(cj, 'filename', None) or '/dev/null'
    if path == '/dev/null':
        user_error('/dev/null: unwritable cookie file')
    if not hasattr(cj, 'save'):
        user_error(f'{path}: unwritable cookie file')

    test_uuid = f'test-{int(time.time())}'
    c = http.cookiejar.Cookie(
        version=0, name='UUID', value=test_uuid,
        port=None, port_specified=False,
        domain='mbank-cli.test', domain_specified=True, domain_initial_dot=False,
        path='/cookie-jar', path_specified=True,
        secure=False, expires=int(time.time()) + 60, discard=False,
        comment=None, comment_url=None, rest={}, rfc2109=False,
    )
    cj.set_cookie(c)
    try:
        cj.save(ignore_discard=True, ignore_expires=True)
    except OSError as e:
        os_error(f'{path}: {e}')
    try:
        cj.clear(domain='mbank-cli.test', path='/cookie-jar', name='UUID')
    except Exception:
        pass
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
    except OSError as e:
        os_error(f'{path}: {e}')
    if test_uuid not in content:
        user_error(f'{path}: unwritable cookie file')


def make_config_line(key, value):
    if re.fullmatch(r'[/\w.~-]+', value):
        return f'{key} {value}\n'
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'{key} "{escaped}"\n'


def cmd_list(**kwargs):
    login = kwargs.get('login')
    if not login:
        user_error('list: login required')
    do_list(login=login, quiet=False)


def cmd_logout(**kwargs):
    do_logout()


def cmd_register_device(**kwargs):
    args = kwargs.get('args') or []
    if len(args) > 1:
        user_error('register-device: too many arguments')
    name = args[0] if args else 'CLI'
    cookiejar_sanity_check_for_register_device()
    do_logout(maybe=True)
    do_login(register_device=name)


def cmd_activate_profile(**kwargs):
    login_info = kwargs.get('login')
    args = kwargs.get('args') or []

    if len(args) < 1:
        user_error('activate-profile: no profile selected')
    if len(args) > 1:
        user_error('activate-profile: too many arguments')

    name = args[0]
    profiles = login_info.get('profiles') or {}

    def sortkey(key):
        key = re.sub(r'^personal(?:/?|$)', '\x00', key)
        return '\x01' if key == 'business' else key

    if name not in profiles:
        names = ', or '.join(f'"{n}"' for n in sorted(profiles.keys(), key=sortkey))
        user_error(f'activate-profile: invalid profile name (should be {unicode_display(names)})')

    codes = profiles[name]
    if len(codes) == 0:
        user_error(f'activate-profile: {name} profile not available')
    if len(codes) > 1:
        internal_error('activate-profile: ambiguous profile name')

    code = 'I' if codes[0] == 'T' else codes[0]
    debug(f'activating profile {code}...')

    headers = {**login_info['headers'], 'Accept': '*/*', 'Content-Type': 'application/x-www-form-urlencoded'}
    req = urllib.request.Request(
        f'{base_url}/LoginMain/Account/JsonActivateProfile',
        data=urllib.parse.urlencode({'profileCode': code}).encode('utf-8'),
        headers=headers,
        method='POST',
    )
    download(req)
    do_lazy_logout(login=login_info)


def cmd_configure(**kwargs):
    config_path = kwargs.get('config_path')
    cookie_jar_path = kwargs.get('cookie_jar_path')

    if config_path and os.path.exists(config_path):
        overwrite = ''
        while overwrite not in ('y', 'Y', 'n', 'N'):
            overwrite = input(f'{unexpand_tilde(config_path)} already exists. Overwrite (y/n)? ') or ''
        if overwrite in ('n', 'N'):
            user_error('Configuration cancelled')

    guessed = get_tz_country_guess() or ''
    cc = ''
    while cc not in country_to_language:
        choices = ', or '.join(c.upper() for c in known_countries)
        cc = (input(f'Country ({choices}): ') or guessed.upper()).lower()

    login = ''
    while not login:
        login = input('Login: ')

    password = ''
    while not password:
        password = term_readpasswd('Password: ')

    sanitized = re.sub(r'\W', '_', login)
    default_cookie = cookie_jar_path or f"{unexpand_tilde(xdg_data_home())}/mbank-cli/{sanitized}.cookies"

    cookie_jar_path = ''
    while len(cookie_jar_path) <= 1:
        cookie_jar_path = input(f'Session cookie store [{default_cookie}]: ') or default_cookie

    cookie_dir = os.path.dirname(expand_tilde(cookie_jar_path))
    if cookie_dir and not os.path.exists(cookie_dir):
        makedirs(cookie_dir)
        print(f'Created directory for session cookie store: {unexpand_tilde(cookie_dir)}')

    cfg_dir = os.path.dirname(config_path)
    if cfg_dir:
        makedirs(cfg_dir)

    cfg_new = f'{config_path}.new'
    try:
        with open(cfg_new, 'w', encoding='utf-8') as fh:
            fh.write(make_config_line('CookieJar', cookie_jar_path))
            fh.write(make_config_line('Country', cc.upper()))
            fh.write(make_config_line('Login', login))
            fh.write(make_config_line('Password', password))
    except OSError as e:
        os_error(f'{cfg_new}: {e}')

    if os.path.exists(config_path):
        try:
            os.rename(config_path, f'{config_path}.bak')
            print(f'Backup copy: {unexpand_tilde(config_path)}.bak')
        except OSError:
            pass

    try:
        os.rename(cfg_new, config_path)
        print(f'Created configuration file: {unexpand_tilde(config_path)}')
    except OSError as e:
        os_error(f'{config_path}: {e}')


def term_readpasswd(prompt='Password: '):
    return getpass.getpass(prompt)


def main():
    command_name, args = parse_args()
    debug(f'selected command: {command_name}')

    commands = {
        'list': {'login': True},
        'logout': {'login': False},
        'register-device': {'login': False, 'args': True},
        'activate-profile': {'login': True, 'args': True},
        'configure': {'login': False, 'config': False},
    }

    command_info = commands.get(command_name)
    if command_info is None:
        user_error(f'{command_name}: invalid command')

    fn_name = f"cmd_{command_name.replace('-', '_')}"
    command_func = globals().get(fn_name)
    if not command_func:
        user_error(f'{command_name}: invalid command')

    cmd_options = {}
    if command_info.get('config', True):
        initialize()
    else:
        cmd_options['config_path'] = opt_config
        cmd_options['cookie_jar_path'] = opt_cookie_jar

    if command_info.get('args'):
        cmd_options['args'] = args

    if command_info.get('login', True):
        cmd_options['login'] = do_login()

    command_func(**cmd_options)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nInterrupted', file=sys.stderr)
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f'\nUnexpected error: {type(e).__name__}: {e}', file=sys.stderr)
        if opt_verbose or opt_debug_dir:
            print('\nFull traceback:', file=sys.stderr)
            traceback.print_exc()
        else:
            print('Run with --verbose for full traceback', file=sys.stderr)
        sys.exit(255)
    finally:
        if ua and hasattr(ua, 'cookie_jar'):
            try:
                if hasattr(ua.cookie_jar, 'save'):
                    ua.cookie_jar.save(ignore_discard=True, ignore_expires=True)
            except Exception:
                pass
