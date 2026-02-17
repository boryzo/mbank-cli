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
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

opt_verbose = False
opt_debug_dir = None
opt_config = None
opt_cookie_jar = None

ua = None
global_config = {}

mbank_host = ''
root_url = ''
base_url = ''

DEFAULT_BROWSER_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128'
DEFAULT_BROWSER_NAME = 'Firefox'
DEFAULT_BROWSER_VERSION = '128'
# Static value copied from Perl original.
DEFAULT_BROWSER_DFP = 'eJyFkT1MFEEUx/dm/NhsUJcj4PmZDYUxJOgFDSEkhg89UDmQ4AfEZpzdnbubcXdnM7MHh9XaGSs7LCwsKYkVJYUFhSaUlMTExMpYUFyns3u35AiiL9ndt//fe/PmvWf0Gl1lGtQbVmNkGA3fzsOnczMFLX9NbxrmPiw0DWsfXm8axX04mi96OHClg0MyGArqY7F68YQBSNA/pX/eBXmdNEKPOjQqAAsM6DIk+CURspgb0UqasvuxOR/rS99+ty334sOB63/9Uh4buDOudcUqckv7v8VHlCFj/t6U9YySFSKGuu/WBPeJ1SH1pBKt+53ihVnqCC55JbJKbvVw/CKxZ2hk2XXqRYM0SNioNv56be3TmYendM3UCtoCnLs5kb6e543Ts/wV9TyczxxbY30Tc9PlEqKBjHDgEBdhIfCqZGZp6QmyPRK4yKeBjxvsUqI43OMC2fVKhQhUw14FVTyOI3YuganbSmJnU0HgKnJJGNVYX/Iva9hVeRFpRHVBkMddpqf6wvQku5x4GXK4HwoiJeUBssPIOZ6KqqJXO2lFjUNVwQGVPBI8pA7re1R6jIhHfBJEqleXNFCdBhHrTfSKzZFQd1Y5Pg19HLJCIicDcbFwVQOCLuOILhPJuhNyUChtvXBEQh4NCBatqhnpGNaVv+tZ2vkELxOhIlrbQNxmxFGVFkuT0+XDO2ifmJHWXNQas+OxTIZ3LCaKHp8sbync/0+MpKjarKcVk646wyzfFgVead9WZprHZbLFIAkVD9aBvgH0TaBvAX0bFHaAtgticw+YP9TnF9jLNYEew9h8A/V30HwP9Y8wBuswtwFzmzC3Bce2YWztqOdt7uT3n3Dzxh8LG3RL'

browser_user_agent = DEFAULT_BROWSER_USER_AGENT
browser_name = DEFAULT_BROWSER_NAME
browser_version = DEFAULT_BROWSER_VERSION
browser_dfp = DEFAULT_BROWSER_DFP

country_to_language = {'cz': 'cs', 'pl': 'pl', 'sk': 'sk'}
known_countries = sorted(country_to_language.keys())

header_xhr = {'X-Requested-With': 'XMLHttpRequest'}
header_accept_json = {'Accept': 'application/json, text/javascript, */*; q=0.01'}
uuid_re = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')

external_bank_source_map = {
    '05855557-d3ee-46c9-98e1-375c10e1af12': 'Bank Millennium',
    '8bd46568-f90e-445a-bec8-5fef7dc90569': 'Alior Bank',
    'b5165570-f6f1-11e8-8eb2-f2801f1b9fd1': 'Bank Pekao SA',
    '555dd77f-7424-4bf7-8869-5576e47793b9': 'Santander Bank Polska',
    'a32d692c-397e-4307-9da8-8367fc3f9237': 'Santander Bank Polska',
    '0789b9be-67d1-468d-9c98-93eb9a058630': 'VeloBank',
}


def debug(msg):
    if not opt_verbose:
        return
    line = f'* {msg}'
    write_log(line)
    print(line, file=sys.stderr)


def warning(msg):
    if msg is None:
        return
    write_log(msg)
    print(f'mbank-cli: {msg}', file=sys.stderr)


def fail(msg, code=1):
    warning(msg)
    sys.exit(code)


def write_log(msg):
    if not opt_debug_dir:
        return
    path = os.path.join(opt_debug_dir, 'log')
    try:
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(str(msg) + '\n')
    except OSError:
        pass


def log_http(request, response=None, content=None, error=None):
    if not opt_debug_dir:
        return
    lines = [f'HTTP {request.get_method()} {request.full_url}']
    for k, v in sorted(dict(request.header_items()).items()):
        lines.append(f'> {k}: {v}')
    data = getattr(request, 'data', None)
    if data:
        try:
            body = data.decode('utf-8', errors='replace')
        except Exception:
            body = repr(data)
        lines.append('>')
        lines.append(body)
    if response is not None:
        lines.append(f'< STATUS {getattr(response, "status", "?")}')
        try:
            headers = dict(response.headers.items())
        except Exception:
            headers = {}
        for k, v in sorted(headers.items()):
            lines.append(f'< {k}: {v}')
    if error is not None:
        lines.append(f'< ERROR {error}')
    if content is not None:
        lines.append('<')
        lines.append(content)
    lines.append('-' * 80)
    write_log('\n'.join(lines))


def server_fail(msg=None):
    if msg:
        warning(msg)
    sys.exit(2)


def pick(*values):
    for v in values:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == '':
            continue
        return v
    return None


def expand_tilde(path):
    return os.path.expanduser(path) if path and path.startswith('~') else path


def unexpand_tilde(path):
    home = os.path.expanduser('~')
    if path.startswith(home):
        return '~' + path[len(home):]
    return path


def xdg_config_home():
    return os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')


def xdg_data_home():
    return os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')


def makedirs(path):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        fail(f'{path}: {e}', code=4)


def read_config(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            lines = fh.readlines()
    except OSError as e:
        fail(f'{path}: {e}', code=4)

    cfg = {'__path__': path}
    for line in lines:
        line = line.rstrip('\n')
        if re.fullmatch(r'(?:#.*)?\s*', line):
            continue
        m = re.match(r'^\s*([\w-]+)\s+(.*\S)\s*$', line)
        if not m:
            fail(f'{path}: syntax error: {line}')
        k, v = m.groups()
        k = k.lower()
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        cfg[k] = v
    return cfg


def cfg_get(name, default=None):
    return global_config.get(name, default)


def apply_browser_identity():
    global browser_user_agent, browser_name, browser_version, browser_dfp

    browser_user_agent = pick(
        os.environ.get('MBANK_CLI_USER_AGENT'),
        cfg_get('browseruseragent'),
        cfg_get('useragent'),
        DEFAULT_BROWSER_USER_AGENT,
    )
    browser_name = pick(
        os.environ.get('MBANK_CLI_BROWSER_NAME'),
        cfg_get('browsername'),
        DEFAULT_BROWSER_NAME,
    )
    browser_version = pick(
        os.environ.get('MBANK_CLI_BROWSER_VERSION'),
        cfg_get('browserversion'),
        DEFAULT_BROWSER_VERSION,
    )
    browser_dfp = pick(
        os.environ.get('MBANK_CLI_DFP'),
        cfg_get('dfp'),
        DEFAULT_BROWSER_DFP,
    )

    debug(f'browser.user_agent = {browser_user_agent}')
    debug(f'browser.name = {browser_name}')
    debug(f'browser.version = {browser_version}')


def decode_http_content(raw, headers):
    encoding = headers.get('Content-Encoding', '')
    if encoding == 'gzip':
        raw = gzip.decompress(raw)
    elif encoding == 'deflate':
        import zlib
        raw = zlib.decompress(raw)
    return raw.decode('utf-8', errors='replace').replace('\r', '')


def http_init(cookie_jar_path, ca_path=None):
    global ua

    for key in list(os.environ.keys()):
        if key.startswith('HTTPS_'):
            del os.environ[key]

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


def download(request, ignore_errors=()):
    method = request.get_method()
    url = request.full_url
    debug(f'{method} {url}')

    try:
        response = ua.open(request, timeout=60)
        content = decode_http_content(response.read(), response.headers)
        log_http(request, response=response, content=content)
        return {
            'status': response.status,
            'url': response.geturl(),
            'headers': response.headers,
            'content': content,
            'response': response,
        }
    except urllib.error.HTTPError as e:
        if e.code in ignore_errors:
            try:
                content = decode_http_content(e.read(), e.headers)
            except Exception:
                content = ''
            log_http(request, response=e, content=content)
            return {
                'status': e.code,
                'url': url,
                'headers': e.headers,
                'content': content,
                'response': e,
            }
        log_http(request, response=e, error=f'HTTPError {e.code}')
        server_fail(f'HTTP error {e.code} on <{method} {url}>')
    except urllib.error.URLError as e:
        reason = getattr(e, 'reason', e)
        log_http(request, error=f'URLError {reason}')
        server_fail(f'HTTP error on <{method} {url}>: {reason}')


def decode_json(text, context):
    try:
        return json.loads(text)
    except Exception as e:
        fail(f'{context}: invalid JSON ({e})', code=3)


def parse_args():
    global opt_verbose, opt_debug_dir, opt_config, opt_cookie_jar

    parser = argparse.ArgumentParser(prog='mbank-cli')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--debug', metavar='DIR')
    parser.add_argument('--config', metavar='FILE')
    parser.add_argument('--cookie-jar', metavar='FILE')
    parser.add_argument('--version', action='version', version='mbank-cli python-port')

    sub = parser.add_subparsers(dest='command')
    sub.add_parser('list', help='List accounts')
    p = sub.add_parser('history', help='Account history')
    p.add_argument('--from', dest='start_date')
    p.add_argument('--to', dest='end_date')
    p.add_argument('--with-id', action='store_true', help='Deprecated: IDs are always included')
    p.add_argument('--all', action='store_true', help='Include external (aggregated) accounts')
    sub.add_parser('logout', help='Logout')
    p = sub.add_parser('register-device', help='Register device')
    p.add_argument('name', nargs='?', default='CLI')
    p = sub.add_parser('activate-profile', help='Activate profile')
    p.add_argument('profile')
    sub.add_parser('configure', help='Configure mbank-cli')

    args = parser.parse_args()
    if args.command is None:
        args.command = 'list'

    opt_verbose = args.verbose
    opt_config = args.config or os.path.join(xdg_config_home(), 'mbank-cli', 'config')
    opt_cookie_jar = args.cookie_jar
    if args.debug:
        if args.debug.startswith('-'):
            fail(f'suspicious directory name for --debug: {args.debug}')
        makedirs(args.debug)
        opt_debug_dir = args.debug

    return args


def initialize():
    global global_config, mbank_host, root_url, base_url

    if not os.path.exists(opt_config):
        fail(
            f'missing configuration file: {opt_config}\n'
            'Run "mbank-cli configure" or create the configuration file manually.'
        )

    global_config = read_config(opt_config)

    cookie_jar_path = opt_cookie_jar or cfg_get('cookiejar')
    if not cookie_jar_path:
        fail(f'{opt_config}: missing cookiejar')
    cookie_jar_path = expand_tilde(cookie_jar_path)

    ca_path = cfg_get('cafile')
    if ca_path:
        ca_path = expand_tilde(ca_path)
        if not os.path.isfile(ca_path):
            fail(f'{ca_path}: file not found', code=4)

    country = (cfg_get('country') or '').lower()
    if not country:
        fail(f'{opt_config}: missing country')

    lang = country_to_language.get(country)
    if not lang:
        fail(f"unknown country {country.upper()}, not in {', '.join(known_countries).upper()}")

    mbank_host = f'online.mbank.{country}'
    root_url = f'https://{mbank_host}'
    base_url = f'https://{mbank_host}/{lang}'

    apply_browser_identity()
    http_init(cookie_jar_path=cookie_jar_path, ca_path=ca_path)


def clear_temp_cookies():
    if ua and hasattr(ua, 'cookie_jar'):
        ua.cookie_jar.clear_session_cookies()


def get_cookie(name):
    if not ua or not hasattr(ua, 'cookie_jar'):
        return None
    for c in ua.cookie_jar:
        if c.name != name:
            continue
        if (c.domain or '').lstrip('.') == mbank_host:
            return c
    return None


def unexpire_cookie(name, context):
    c = get_cookie(name)
    if c is None:
        fail(f'{context}: missing cookie {name}', code=3)
    if c.expires is None or c.discard:
        c.expires = int(1e10)
        c.discard = False


def match_uuid(value, context):
    value = str(value or '')
    if not uuid_re.fullmatch(value):
        fail(f'{context}: invalid UUID: {value}', code=3)
    return value


def normalize_external_source_name(value):
    text = str(value or '').strip()
    if not text:
        return 'external'
    return external_bank_source_map.get(text.lower(), text)


def get_tabid():
    c = get_cookie('mBank_tabId')
    if c is None:
        fail('login: mBank_tabId cookie missing', code=3)
    return match_uuid(c.value, 'login.tabid')


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
    in_string = False
    quote_char = ''
    escaped = False

    for i in range(start, len(content)):
        ch = content[i]

        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == quote_char:
                in_string = False
            continue

        if ch in ('"', "'"):
            in_string = True
            quote_char = ch
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

    scripts = re.finditer(r'<script\b[^>]*>(.*?)</script>', page_content, re.IGNORECASE | re.DOTALL)
    for m in scripts:
        payload = extract_js_object_assignment(m.group(1), 'Ebre.Venezia.ProfileData')
        if not payload:
            continue

        data = decode_json(payload, 'login.profiles')

        for src_key, logical_name in (('iProfiles', 'personal'), ('fProfiles', 'business')):
            block = data.get(src_key, {})
            if not isinstance(block, dict):
                continue
            arr = block.get('profiles', [])
            if not isinstance(arr, list):
                continue

            for profile in arr:
                if not isinstance(profile, dict):
                    continue
                code = str(profile.get('profileCode', '')).strip()
                if not code:
                    continue

                profiles[logical_name].append(code)
                if logical_name == 'business':
                    label = str(profile.get('firmName', '')).strip() or f'business/{code}'
                    profiles.setdefault(label, []).append(code)

        if len(profiles.get('personal', [])) > 1:
            profiles.pop('personal', None)
        if len(profiles.get('business', [])) > 1:
            profiles.pop('business', None)
        break

    return profiles


def extract_csrf_token(html):
    for m in re.finditer(r'<meta\b[^>]*>', html, re.IGNORECASE):
        tag = m.group(0)
        attrs = {k.lower(): v for k, v in re.findall(r'([A-Za-z_:][-A-Za-z0-9_:.]*)=["\']([^"\']*)["\']', tag)}
        if attrs.get('name') == '__AjaxRequestVerificationToken':
            return attrs.get('content')
    return None


def timestamp_to_date(ts):
    m = re.match(r'^(\d{4}-\d{2}-\d{2})T', str(ts or ''))
    return m.group(1) if m else ''


def parse_ymd_date_or_fail(value, context):
    text = str(value or '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        fail(f'{context}: invalid date {text!r}')
    return text


def local_midnight_to_utc(date_text):
    dt = datetime.fromisoformat(f'{date_text}T00:00:00').astimezone(timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')


def http_date_to_local_ymd(date_header):
    if not date_header:
        return datetime.now().date().isoformat()
    try:
        dt = parsedate_to_datetime(date_header)
        return dt.astimezone().date().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


def shift_ymd(date_text, days):
    return (datetime.fromisoformat(date_text).date() + timedelta(days=days)).isoformat()


def sanitize_field(value):
    text = '' if value is None else str(value)
    text = text.replace('\r', ' ').replace('\n', ' ').strip()
    return text.replace(';', ',')


def ask_sms_password(date, operation_no, try_num):
    if try_num > 1:
        print(f'(try #{try_num})', file=sys.stderr)
    return input(f'SMS password from {date} (operation #{operation_no}): ')


def post_json(url, payload, headers=None, ignore_errors=()):
    hdr = {} if headers is None else dict(headers)
    hdr['Content-Type'] = 'application/json; charset=UTF-8'
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=hdr,
        method='POST',
    )
    return download(req, ignore_errors=ignore_errors)


def get_main_accounts(login_info, context='list.json'):
    headers = {
        **login_info['headers'],
        **header_accept_json,
        'Content-Type': 'application/json; charset=UTF-8',
    }
    req = urllib.request.Request(
        f'{base_url}/MyDesktop/Desktop/GetAccountsList',
        data=b'{}',
        headers=headers,
        method='POST',
    )
    doc = download(req)
    data = decode_json(doc['content'], context)
    raw_accounts = data.get('accountDetailsList')
    if not isinstance(raw_accounts, list):
        fail('list: accountDetailsList missing', code=3)
    out = []
    for raw in raw_accounts:
        acc = normalize_mbank_account(raw)
        if acc:
            out.append(acc)
    return out


def build_history_query(product_id, start_date, end_date, compact=False, null_amount=False):
    if compact:
        params = {
            'productIds': product_id,
            'dateFrom': local_midnight_to_utc(start_date),
            'dateTo': local_midnight_to_utc(end_date),
            'sortingOrder': 'ByDate',
        }
    else:
        amount_empty = 'null' if null_amount else ''
        params = {
            'productIds': product_id,
            'amountFrom': amount_empty,
            'amountTo': amount_empty,
            'useAbsoluteSearch': 'false',
            'currency': '',
            'categories': '',
            'operationTypes': '',
            'searchText': '',
            'dateFrom': local_midnight_to_utc(start_date),
            'dateTo': local_midnight_to_utc(end_date),
            'standingOrderId': '',
            'showDebitTransactionTypes': 'false',
            'showCreditTransactionTypes': 'false',
            'showIrrelevantTransactions': 'true',
            'showSavingsAndInvestments': 'true',
            'saveShowIrrelevantTransactions': 'false',
            'saveShowSavingsAndInvestments': 'false',
            'selectedSuggestionId': '',
            'selectedSuggestionType': '',
            'showUncategorizedTransactions': 'false',
            'debitCardNumber': '',
            'counterpartyAccountNumbers': '',
            'sortingOrder': 'ByDate',
        }
    return urllib.parse.urlencode(params)


def get_external_accounts_for_history(login_info):
    headers = {
        **login_info['headers'],
        **header_xhr,
        **header_accept_json,
    }
    urls = (
        f'{root_url}/api/AccountsAggregation/Accounts?showUnProccessedAccounts=false',
        f'{root_url}/api/AccountsAggregation/Accounts?showUnProcessedAccounts=false',
    )
    accounts_doc = None
    for url in urls:
        doc = download(urllib.request.Request(url, headers=headers, method='GET'), ignore_errors=(404, 405))
        if doc['status'] in (404, 405):
            continue
        accounts_doc = doc
        break
    if accounts_doc is None or not (200 <= accounts_doc['status'] < 300):
        return []

    data = decode_json(accounts_doc['content'], 'history.external.accounts')
    payload = data.get('payload')
    if not isinstance(payload, list):
        return []

    out = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        account_id = str(item.get('accountId', '')).strip()
        if not uuid_re.fullmatch(account_id):
            continue
        account_no = normalize_account_number(item.get('accountNumber'))
        if not account_no:
            continue
        bank = item.get('bank')
        bank_name = bank.get('name') if isinstance(bank, dict) else None
        source = normalize_external_source_name(pick(bank_name, item.get('bankId'), 'external'))
        out.append(
            {
                'account_id': account_id,
                'account_number': account_no,
                'source': source,
                'account_name': sanitize_field(pick(item.get('externalAccountName'), item.get('accountName'), '')),
            }
        )
    return out


def get_external_history_rows(login_info, start_date, end_date, with_id=False):
    headers = {
        **login_info['headers'],
        **header_xhr,
        **header_accept_json,
    }
    rows = []
    for account in get_external_accounts_for_history(login_info):
        account_id = account['account_id']
        account_no = account['account_number']
        source = account['source']
        account_name = account['account_name']

        status_url = f'{root_url}/api/AccountsAggregation/Transactions/Status/{account_id}'
        download(urllib.request.Request(status_url, headers=headers, method='GET'), ignore_errors=(400, 404, 405, 422))

        query = urllib.parse.urlencode(
            {
                'transactionStatuses': 'DONE',
                'amountMin': '',
                'amountMax': '',
                'transactionDateFrom': local_midnight_to_utc(start_date),
                'transactionDateTo': local_midnight_to_utc(end_date),
                'category': 'UNDEFINED',
                'text': '',
                'counterPartyAccountNumbers': '',
            }
        )
        list_url = f'{root_url}/api/AccountsAggregation/Transactions/OfflineList/{account_id}?{query}'
        doc = download(urllib.request.Request(list_url, headers=headers, method='GET'), ignore_errors=(400, 404, 405, 422))
        if not (200 <= doc['status'] < 300):
            continue

        data = decode_json(doc['content'], f'history.external.offline-list.{account_id}')
        payload = data.get('payload')
        txs = payload.get('transactions') if isinstance(payload, dict) else None
        if not isinstance(txs, list):
            continue

        for tx in txs:
            if not isinstance(tx, dict):
                continue
            if str(tx.get('transactionStatus', '')).upper() != 'DONE':
                continue
            op_id = sanitize_field(tx.get('id', ''))
            tx_date = sanitize_field(
                pick(
                    tx.get('bookingDate'),
                    timestamp_to_date(tx.get('bookingDate')),
                    tx.get('tradeDate'),
                    timestamp_to_date(tx.get('tradeDate')),
                    '',
                )
            )
            op_type = sanitize_field(pick(tx.get('transactionCategory'), tx.get('transactionStatus'), 'EXTERNAL'))
            amount = format_money(tx.get('amount'), tx.get('currency'))
            balance = format_money(tx.get('postTransactionBalance'), tx.get('currency')) if tx.get('postTransactionBalance') is not None else ''
            description = sanitize_field(tx.get('description', ''))
            comment = sanitize_field(pick(tx.get('bankName'), source, account_name, 'external'))

            row = [tx_date, account_no, op_id, op_type, amount, balance, description, comment]
            rows.append(';'.join(row))
    return rows


def do_history(login_info, start_date=None, end_date=None, with_id=False, include_all=False):
    headers = {
        **header_xhr,
        'X-Tab-Id': login_info['headers'].get('X-Tab-Id', ''),
        'Referer': f'{root_url}/history',
        'Accept': '*/*',
    }

    mode_doc = download(urllib.request.Request(f'{base_url}/Pfm/HistoryApi/GetHistoryModeInfo?shouldOverWriteFilters=true', headers=headers))
    mode = decode_json(mode_doc['content'], 'history.mode-info')
    min_date = timestamp_to_date(mode.get('pfmStartDate'))
    if not min_date:
        fail('history.mode-info: missing pfmStartDate', code=3)
    max_date = http_date_to_local_ymd(mode_doc['headers'].get('Date') if hasattr(mode_doc['headers'], 'get') else '')

    if start_date is None and end_date is None:
        end_date = max_date
        start_date = shift_ymd(end_date, -60)
        warning('history: default range is last 60 days; use --from/--to for full history')
    else:
        if start_date is None:
            end_date = parse_ymd_date_or_fail(end_date, 'history.to')
            start_date = shift_ymd(end_date, -60)
        else:
            start_date = parse_ymd_date_or_fail(start_date, 'history.from')
        if end_date is None:
            end_date = max_date
        else:
            end_date = parse_ymd_date_or_fail(end_date, 'history.to')

    if start_date < min_date:
        start_date = min_date
    if end_date > max_date:
        end_date = max_date
    if start_date > end_date:
        fail('history: start date is after end date')

    pfm_doc = download(urllib.request.Request(f'{base_url}/Pfm/HistoryApi/GetPfmInitialData?shouldOverWriteFilters=true', headers=headers))
    pfm = decode_json(pfm_doc['content'], 'history.pfm-data')
    products = pfm.get('pfmProducts')
    if not isinstance(products, list):
        fail('history.pfm-data: missing pfmProducts', code=3)

    product_map = {}
    for p in products:
        if not isinstance(p, dict):
            continue
        contract = normalize_account_number(p.get('contractNumber'))
        pid = str(p.get('id', '')).strip()
        if contract and pid:
            product_map[contract] = pid

    visible_account_numbers = {a['number'] for a in get_main_accounts(login_info, context='history.accounts')}
    account_numbers = [n for n in sorted(product_map.keys()) if n in visible_account_numbers]
    if not account_numbers:
        account_numbers = sorted(product_map.keys())

    for account_no in account_numbers:
        query_variants = (
            build_history_query(product_map[account_no], start_date, end_date, compact=False, null_amount=False),
            build_history_query(product_map[account_no], start_date, end_date, compact=False, null_amount=True),
            build_history_query(product_map[account_no], start_date, end_date, compact=True),
        )
        ops_doc = None
        for query in query_variants:
            first_url = f'{base_url}/Pfm/HistoryApi/GetOperationsPfm?{query}'
            doc = download(urllib.request.Request(first_url, headers=headers), ignore_errors=(519,))
            if doc['status'] == 519:
                continue
            ops_doc = doc
            break
        if ops_doc is None:
            warning(f'history: skipping account {account_no} (HTTP 519)')
            continue

        while True:
            ops_data = decode_json(ops_doc['content'], 'history.ops')
            txs = ops_data.get('transactions')
            if not isinstance(txs, list):
                fail('history.ops: missing transactions', code=3)
            for tx in txs:
                if not isinstance(tx, dict):
                    continue
                op_id = sanitize_field(tx.get('operationNumber', ''))
                op_type = sanitize_field(tx.get('operationType', ''))
                tx_date = sanitize_field(timestamp_to_date(tx.get('transactionDate')) or tx.get('transactionDate', ''))
                amount = format_money(tx.get('amount'), tx.get('currency'))
                balance = format_money(tx.get('balance'), tx.get('currency')) if tx.get('balance') is not None else ''
                description = sanitize_field(tx.get('description', ''))
                comment = sanitize_field(tx.get('comment', ''))
                row = [tx_date, account_no, op_id, op_type, amount, balance, description, comment]
                print(';'.join(row))
            next_url = ops_data.get('nextPageUrl')
            if not next_url:
                break
            if not str(next_url).startswith('Pfm/HistoryApi/GetOperationsPfm?'):
                break
            paged_url = f'{base_url}/{next_url}'
            ops_doc = download(urllib.request.Request(paged_url, headers=headers), ignore_errors=(519,))
            if ops_doc['status'] == 519:
                warning(f'history: paging failed for account {account_no} (HTTP 519)')
                break

    if include_all:
        for row in get_external_history_rows(login_info, start_date, end_date, with_id=with_id):
            print(row)


def do_2fa(register_device=None):
    headers = {'Origin': root_url, 'Referer': f'{root_url}/connect/Login'}
    dfp = browser_dfp

    sca_doc = post_json(f'{root_url}/signin/connect/api/sca', {'dfp': dfp}, headers=headers)
    unexpire_cookie('mBank8', 'login.sca.cookie')

    sca = decode_json(sca_doc['content'], 'login.sca')
    sca_status = str(sca.get('imsStatus', ''))
    is_limit_exceeded = bool(sca.get('maximumNumberOfDevicesExceeded'))

    if sca_status == 'IsTrusted' and not register_device:
        return match_uuid(sca.get('token'), 'login.sca.token')

    module_data = {
        'authorizationAction': 1,
        'browserName': browser_name,
        'browserVersion': browser_version,
        'deviceName': f'Komputer Linux {browser_name}',
        'osName': 'Linux',
        'dfp': dfp,
    }

    if register_device:
        if sca_status != 'NotTrusted':
            fail('device already registered')
        if is_limit_exceeded:
            fail('too many registered devices')

        while True:
            uniq_doc = post_json(
                f'{root_url}/signin/connect/api/sca/uniqueDevice',
                {'deviceName': register_device},
                headers=headers,
            )
            uniq = decode_json(uniq_doc['content'], 'login.sca.unique-device')
            if uniq.get('isUnique'):
                break
            print('Device name has been rejected. Try another one.', file=sys.stderr)
            register_device = input('Device name: ').strip()
            if len(register_device) < 2:
                register_device = 'CLI'

        module_data['authorizationAction'] = 2
        module_data['deviceName'] = register_device

    init_doc = post_json(
        f'{root_url}/signin/connect/api/mediator/initialize',
        {'moduleData': module_data, 'moduleId': 'IB20'},
        headers=headers,
    )
    init = decode_json(init_doc['content'], 'login.2fa.initialize')
    auth = init.get('authorizationData', {})

    mode = str(auth.get('authorizationType', ''))
    auth_id = match_uuid(auth.get('authorizationId'), 'login.2fa.authorization-id')
    auth_date = timestamp_to_date(auth.get('authorizationDate'))
    operation_no = str(auth.get('authorizationNumber', '')).strip()

    if not auth_date or not operation_no:
        fail('login.2fa: missing authorization date/number', code=3)

    if mode == 'MA':
        print(
            f'Waiting for confirmation of operation no {operation_no} from {auth_date} in the mobile app...',
            file=sys.stderr,
        )

        while True:
            status_doc = post_json(
                f'{root_url}/signin/connect/api/mediator/status',
                {'authorizationId': auth_id},
                headers=headers,
            )

            if status_doc['status'] == 204:
                time.sleep(1)
                continue

            status_data = decode_json(status_doc['content'], 'login.2fa.status')
            status = str(status_data.get('authorizationStatus', ''))
            debug(f'2FA mobile auth: {status}')

            if status == 'Authorized':
                token = pick(
                    (status_data.get('postResult') or {}).get('token'),
                    status_data.get('token'),
                )
                return match_uuid(token, 'login.2fa.status.token')
            if status == 'Canceled':
                fail('login failed: rejected mobile authentication request')
            if status == 'TimeOut':
                fail('login failed: mobile authentication request timed out')

            time.sleep(1)

    if mode == 'SMS':
        try_num = 1
        while True:
            sms_password = ask_sms_password(auth_date, operation_no, try_num)
            auth_doc = post_json(
                f'{root_url}/signin/connect/api/mediator/authorize',
                {
                    'authorizationCode': sms_password,
                    'authorizationId': auth_id,
                    'authorizationType': mode,
                },
                headers=headers,
                ignore_errors=(422,),
            )
            auth_data = decode_json(auth_doc['content'], 'login.2fa.authorize')
            token = (auth_data.get('postResult') or {}).get('token')
            if token:
                return match_uuid(token, 'login.2fa.sms.token')
            if (auth_data.get('type') or '') == 'AuthApi-SMS014':
                print('Incorrect SMS password', file=sys.stderr)
                try_num += 1
                continue
            fail(f"login failed: {auth_data.get('detail', auth_data.get('type', 'SMS error'))}")

    fail(f'unsupported 2FA mode: {mode}', code=3)


def get_password_from_config():
    password = cfg_get('password')
    if password:
        return password

    password_manager = cfg_get('passwordmanager')
    if password_manager:
        try:
            result = subprocess.run(['sh', '-c', password_manager], capture_output=True, text=True, check=True)
            return (result.stdout or '').split('\n')[0].strip()
        except Exception as e:
            fail(f'password manager failed: {e}', code=4)

    if sys.stdin.isatty():
        return getpass.getpass('Password: ')

    fail(f'{opt_config}: missing password')


def do_login(probe=False, register_device=None):
    doc = download(urllib.request.Request(base_url))

    if '/Login' in doc['url']:
        if probe:
            return None

        clear_temp_cookies()
        debug('logging in...')

        lang = base_url.rstrip('/').split('/')[-1]
        pattern = (
            rf"'/signin/connect/authorize\?ui_locales={lang}&"
            r"(request_uri=urn%3aietf%3aparams%3aoauth%3arequest_uri%3a[0-9A-F]+&client_id=Ib)'"
        )
        m = re.search(pattern, doc['content'])
        if not m:
            fail('login: cannot find return URL', code=3)

        return_url = m.group(1).replace('%3a', '%3A')
        return_url = f'/signin/connect/authorize/callback?{return_url}&suppressed_prompt=login'

        login_name = cfg_get('login')
        if not login_name:
            fail(f'{opt_config}: missing login')

        password = get_password_from_config()
        if not password:
            fail('login failed: empty password')

        if cfg_get('smsinbox'):
            ask_sms_password('2006-07-30', 1, 1)

        headers = {'Origin': root_url, 'Referer': f'{root_url}/connect/Login'}
        prelogin_doc = post_json(
            f'{root_url}/signin/connect/api/users/prelogin',
            {
                'language': lang,
                'login': login_name,
                'password': password,
                'returnUrl': return_url,
            },
            headers=headers,
            ignore_errors=(422,),
        )
        prelogin = decode_json(prelogin_doc['content'], 'login.prelogin')
        if prelogin.get('type') != 'PreLoginResponse':
            fail(f"login failed: {prelogin.get('detail', prelogin.get('title', 'unknown error'))}")

        token = do_2fa(register_device)

        final_doc = post_json(
            f'{root_url}/signin/connect/api/users/finallogin',
            {
                'language': lang.capitalize(),
                'returnUrl': return_url,
                'token': token,
            },
            headers=headers,
        )
        final = decode_json(final_doc['content'], 'login.final')
        redirect = str(final.get('returnUrl', ''))
        if not redirect.startswith('/'):
            fail('login.final: invalid returnUrl', code=3)

        download(urllib.request.Request(f'{root_url}{redirect}'))
        doc = download(urllib.request.Request(base_url))

    tabid = get_tabid()
    csrf_token = extract_csrf_token(doc['content'])
    if not csrf_token or len(csrf_token) < 20:
        fail('login: invalid CSRF token', code=3)

    if re.search(r'<header\b[^>]*class=["\'][^"\']*\btech-break\b', doc['content'], re.IGNORECASE):
        server_fail('service is temporarily unavailable')

    return {
        'url': doc['url'],
        'csrf_token': csrf_token,
        'profiles': extract_login_profiles(doc['content']),
        'headers': {
            'Referer': doc['url'],
            'X-Tab-Id': tabid,
            'X-Request-Verification-Token': csrf_token,
            **header_xhr,
        },
    }


def normalize_account_number(number):
    if number is None:
        return ''
    value = str(number).strip().replace(' ', '')
    if value.startswith('PL'):
        value = value[2:]
    return value


def parse_amount_with_currency(value):
    if isinstance(value, dict):
        amount = pick(value.get('amount'), value.get('Amount'), value.get('value'), value.get('Value'))
        currency = pick(value.get('currency'), value.get('Currency'), value.get('currencyCode'))
        return amount, currency
    return value, None


def normalize_number(value):
    if value is None:
        return None
    text = str(value).replace('\xa0', '').replace(' ', '').replace(',', '.').strip()
    if not re.fullmatch(r'[-+]?\d+(?:\.\d+)?', text):
        return None
    return text


def format_money(value, currency):
    if value is None:
        return ''

    amount = normalize_number(value)
    if amount is None:
        return ''

    currency = str(currency or '').strip().upper()
    if not re.fullmatch(r'[A-Z]{3}', currency):
        return ''

    try:
        return f'{float(amount):.2f} {currency}'
    except Exception:
        return ''


def normalize_mbank_account(raw):
    if not isinstance(raw, dict):
        return None

    product = str(raw.get('ProductName', '')).strip()
    if not product:
        return None

    subtitle = str(raw.get('SubTitle', '')).strip()
    name = product if not subtitle else f'{product} - {subtitle}'

    number = normalize_account_number(raw.get('AccountNumber'))
    if not number:
        return None

    balance, balance_currency = parse_amount_with_currency(raw.get('Balance'))
    available, available_currency = parse_amount_with_currency(raw.get('AvailableBalance'))
    currency = pick(raw.get('Currency'), balance_currency, available_currency)

    return {
        'name': name,
        'number': number,
        'balance': balance,
        'available': available,
        'currency': currency,
        'source': 'mbank',
    }


def normalize_external_account(raw):
    if not isinstance(raw, dict):
        return None

    name = pick(
        raw.get('name'),
        raw.get('accountNameClient'),
        raw.get('accountName'),
        raw.get('productName'),
        raw.get('ProductName'),
        raw.get('externalAccountName'),
        raw.get('accountTypeName'),
    )
    number = pick(raw.get('number'), raw.get('accountNumber'), raw.get('iban'), raw.get('Iban'))

    if not name or not number:
        return None

    balance = pick(raw.get('balance'), raw.get('Balance'), raw.get('bookingBalance'))
    available = pick(raw.get('availableBalance'), raw.get('AvailableBalance'), raw.get('available'), balance)

    balance_value, balance_currency = parse_amount_with_currency(balance)
    available_value, available_currency = parse_amount_with_currency(available)
    currency = pick(raw.get('currency'), raw.get('Currency'), balance_currency, available_currency)

    source = pick(
        raw.get('bankName'),
        raw.get('providerName'),
        raw.get('provider'),
        raw.get('institutionName'),
        raw.get('bankId'),
        'external',
    )

    return {
        'name': str(name),
        'number': normalize_account_number(number),
        'balance': balance_value,
        'available': available_value,
        'currency': str(currency or '').upper(),
        'source': normalize_external_source_name(source),
    }


def iter_dict_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dict_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dict_nodes(child)


def fetch_offline_accounts(login_info):
    url = f'{root_url}/api/AccountsAggregation/Accounts/accounts/Offline'
    headers = {**login_info['headers'], **header_accept_json}

    docs = []
    try:
        docs.append(post_json(url, {}, headers=headers, ignore_errors=(404, 405)))
    except Exception:
        pass

    if not docs or docs[-1]['status'] in (404, 405):
        get_req = urllib.request.Request(url, headers=headers, method='GET')
        docs.append(download(get_req, ignore_errors=(404, 405)))

    doc = docs[-1]
    if not (200 <= doc['status'] < 300):
        return []

    data = decode_json(doc['content'], 'list.external')

    out = []
    seen = set()
    for node in iter_dict_nodes(data):
        acc = normalize_external_account(node)
        if not acc:
            continue
        key = (acc['number'], acc['name'], acc['source'])
        if key in seen:
            continue
        seen.add(key)
        out.append(acc)
    return out


def current_timestamp_iso():
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def print_account_row(account):
    ts = current_timestamp_iso()
    print(
        f"{ts};{account['name']};{account['number']};"
        f"{format_money(account.get('balance'), account.get('currency'))};"
        f"{format_money(account.get('available'), account.get('currency'))};"
        f"{account.get('source', '')}"
    )


def do_list(login_info):
    main_accounts = get_main_accounts(login_info, context='list.json')
    result = []
    for account in main_accounts:
        result.append({'name': account['name'], 'number': account['number'], 'source': account['source']})
        print_account_row(account)

    for account in fetch_offline_accounts(login_info):
        result.append({'name': account['name'], 'number': account['number'], 'source': account['source']})
        print_account_row(account)

    return result


def do_lazy_logout(login_info):
    req = urllib.request.Request(
        f'{base_url}/LoginMain/Account/LazyLogout',
        data=b'',
        headers={
            **login_info['headers'],
            **header_accept_json,
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    doc = download(req)
    data = decode_json(doc['content'], 'logout.lazy')
    if not data.get('lazy'):
        fail('logout: LazyLogout returned false', code=3)


def do_logout(maybe=False):
    login_info = do_login(probe=True)
    if not login_info:
        clear_temp_cookies()
        if maybe:
            return
        fail('logout: the user was not logged in')

    do_lazy_logout(login_info)
    req = urllib.request.Request(
        f'{base_url}/LoginMain/Account/Logout',
        headers={'Referer': login_info['url']},
        method='GET',
    )
    download(req)
    clear_temp_cookies()


def cookiejar_sanity_check_for_register_device():
    if not ua or not hasattr(ua, 'cookie_jar'):
        fail('missing cookie jar')

    cookie_jar = ua.cookie_jar
    path = getattr(cookie_jar, 'filename', None) or '/dev/null'

    if path == '/dev/null':
        fail('/dev/null: unwritable cookie file')
    if not hasattr(cookie_jar, 'save'):
        fail(f'{path}: unwritable cookie file')
    try:
        cookie_jar.save(ignore_discard=True, ignore_expires=True)
    except OSError as e:
        fail(f'{path}: {e}', code=4)


def sort_profile_key(name):
    name = re.sub(r'^personal(?:/?|$)', '\x00', name)
    return '\x01' if name == 'business' else name


def do_activate_profile(login_info, name):
    profiles = login_info.get('profiles') or {}
    if name not in profiles:
        choices = ', or '.join(f'"{p}"' for p in sorted(profiles.keys(), key=sort_profile_key))
        fail(f'activate-profile: invalid profile name (should be {choices})')

    codes = profiles[name]
    if len(codes) == 0:
        fail(f'activate-profile: {name} profile not available')
    if len(codes) > 1:
        fail('activate-profile: ambiguous profile name', code=3)

    code = 'I' if codes[0] == 'T' else codes[0]

    req = urllib.request.Request(
        f'{base_url}/LoginMain/Account/JsonActivateProfile',
        data=urllib.parse.urlencode({'profileCode': code}).encode('utf-8'),
        headers={
            **login_info['headers'],
            'Accept': '*/*',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        method='POST',
    )
    download(req)
    do_lazy_logout(login_info)


def get_tz_country_guess():
    try:
        loc = locale.getlocale()[0] or ''
    except Exception:
        return None
    if '_' not in loc:
        return None
    cc = loc.split('_', 1)[1].lower()
    return cc if cc in country_to_language else None


def make_config_line(key, value):
    value = str(value)
    if re.fullmatch(r'[/\w.~-]+', value):
        return f'{key} {value}\n'
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'{key} "{escaped}"\n'


def cmd_configure(config_path, cookie_jar_path):
    if config_path and os.path.exists(config_path):
        overwrite = ''
        while overwrite not in ('y', 'Y', 'n', 'N'):
            overwrite = input(f'{unexpand_tilde(config_path)} already exists. Overwrite (y/n)? ') or ''
        if overwrite in ('n', 'N'):
            fail('Configuration cancelled')

    guessed_country = (get_tz_country_guess() or '').upper()
    country = ''
    while country.lower() not in country_to_language:
        options = ', or '.join(c.upper() for c in known_countries)
        country = (input(f'Country ({options}): ') or guessed_country).upper()

    login_name = ''
    while not login_name:
        login_name = input('Login: ').strip()

    password = ''
    while not password:
        password = getpass.getpass('Password: ')

    safe_login = re.sub(r'\W', '_', login_name)
    default_cookie_jar = cookie_jar_path or f"{unexpand_tilde(xdg_data_home())}/mbank-cli/{safe_login}.cookies"

    cookie_store = ''
    while len(cookie_store.strip()) <= 1:
        cookie_store = input(f'Session cookie store [{default_cookie_jar}]: ') or default_cookie_jar

    cookie_dir = os.path.dirname(expand_tilde(cookie_store))
    if cookie_dir and not os.path.exists(cookie_dir):
        makedirs(cookie_dir)
        print(f'Created directory for session cookie store: {unexpand_tilde(cookie_dir)}')

    config_dir = os.path.dirname(config_path)
    if config_dir:
        makedirs(config_dir)

    tmp_path = f'{config_path}.new'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as fh:
            fh.write(make_config_line('CookieJar', cookie_store))
            fh.write(make_config_line('Country', country.upper()))
            fh.write(make_config_line('Login', login_name))
            fh.write(make_config_line('Password', password))
    except OSError as e:
        fail(f'{tmp_path}: {e}', code=4)

    if os.path.exists(config_path):
        try:
            os.rename(config_path, f'{config_path}.bak')
            print(f'Backup copy: {unexpand_tilde(config_path)}.bak')
        except OSError:
            pass

    try:
        os.rename(tmp_path, config_path)
    except OSError as e:
        fail(f'{config_path}: {e}', code=4)

    print(f'Created configuration file: {unexpand_tilde(config_path)}')


def save_cookie_jar():
    if ua and hasattr(ua, 'cookie_jar') and hasattr(ua.cookie_jar, 'save'):
        try:
            ua.cookie_jar.save(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass


def main():
    args = parse_args()

    if args.command == 'configure':
        cmd_configure(opt_config, opt_cookie_jar)
        return

    initialize()

    if args.command == 'list':
        login_info = do_login()
        do_list(login_info)
        return

    if args.command == 'history':
        login_info = do_login()
        do_history(
            login_info,
            start_date=args.start_date,
            end_date=args.end_date,
            with_id=args.with_id,
            include_all=args.all,
        )
        return

    if args.command == 'logout':
        do_logout(maybe=False)
        return

    if args.command == 'register-device':
        cookiejar_sanity_check_for_register_device()
        do_logout(maybe=True)
        do_login(register_device=args.name)
        return

    if args.command == 'activate-profile':
        login_info = do_login()
        do_activate_profile(login_info, args.profile)
        return

    fail(f'{args.command}: invalid command')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nInterrupted', file=sys.stderr)
        sys.exit(1)
    finally:
        save_cookie_jar()
