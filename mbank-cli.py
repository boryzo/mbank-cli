#!/usr/bin/env python3

# Copyright © 2006-2025 Jakub Wilk <jwilk@jwilk.net>
# SPDX-License-Identifier: MIT

import sys
import os
import re
import json
import traceback
import argparse
import getpass
import http.cookiejar
import urllib.parse
import urllib.request
import urllib.error
import ssl
import time
import locale
import codecs
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html.parser import HTMLParser
import xml.etree.ElementTree as ET

# ==========================
# logging and error handling
# ==========================

opt_verbose = 0
opt_debug_dir = None
opt_debug_interactive = 0
bugtracker = 'https://github.com/jwilk/mbank-cli/issues'
bugreport_url_tmpl = f"{bugtracker}/%d"
bugreport_request = f"Please file a bug at <{bugtracker}>."

def write_log(message):
    """Write a message to the log file."""
    if opt_debug_dir is None:
        return
    path = os.path.join(opt_debug_dir, 'log')
    try:
        with open(path, 'a', encoding='utf-8') as log:
            print(message, file=log)
    except OSError as e:
        os_error(f"{path}: {e}")

def debug(message):
    """Log a debug message."""
    message = f"* {message}"
    write_log(message)
    if opt_verbose:
        print(message, file=sys.stderr)

def warning(message):
    """Print a warning message."""
    if message is not None:
        write_log(message)
        print(f"mbank-cli: {message}", file=sys.stderr)

def user_error(message):
    """Print user error and exit with code 1."""
    warning(message)
    sys.exit(1)

def server_error(message=None):
    """Print server error and exit with code 2."""
    if message:
        warning(message)
    sys.exit(2)

def http_error(request, response):
    """Handle HTTP errors."""
    message = f'HTTP error {response.status} on <{request.method} {request.full_url}>'
    
    if response.status == 500:
        try:
            extra = response.read().decode('utf-8', errors='replace')
            extra = extra.rstrip('\n')
            extra = re.sub(r'\n+', '\n', extra)
            extra = re.sub(r'^', '| ', extra, flags=re.MULTILINE)
            message += f"\n{extra}\n"
        except:
            pass
    
    write_log(message)
    traceback.print_stack()
    print(message, file=sys.stderr)
    server_error()

def http_decoding_error(request):
    """Handle HTTP decoding errors."""
    message = f'HTTP decoding error on <{request.method} {request.full_url}>'
    write_log(message)
    traceback.print_stack()
    print(message, file=sys.stderr)
    server_error()

def scraping_error(message):
    """Handle web scraping errors."""
    message = f"Scraping error: {message}"
    write_log(message)
    traceback.print_stack()
    print(message, file=sys.stderr)
    print(bugreport_request, file=sys.stderr)
    sys.exit(3)

def normalize_whitespace(s):
    """Normalize whitespace in a string."""
    s = re.sub(r'\s+', ' ', s)
    s = s.strip()
    return s

def quote(x):
    """Quote a value for display."""
    if isinstance(x, re.Pattern):
        pattern = x.pattern
        flags = ''
        if x.flags & re.IGNORECASE:
            flags += 'i'
        if x.flags & re.MULTILINE:
            flags += 'm'
        if x.flags & re.DOTALL:
            flags += 's'
        pattern = pattern.replace('/', r'\/')
        return f"/{pattern}/{flags}"
    else:
        return json.dumps(x, ensure_ascii=True, allow_nan=False)

def match(text, pattern, context=None):
    """Match text against a pattern with context."""
    if isinstance(pattern, str):
        pattern = re.compile(re.escape(pattern))
    
    if not isinstance(pattern, re.Pattern):
        internal_error('match(): invalid argument', 1)
    
    if not isinstance(text, str):
        qtext = quote(text)
        scraping_error(f"{context}: {qtext} is not a string")
    
    if not pattern.fullmatch(text):
        qtext = quote(text)
        qpattern = quote(pattern)
        message = f"{qtext} does not match {qpattern}"
        scraping_error(f"{context}: {message}")
    
    return text

def no_match(text, context=None):
    """Always fail to match (for type checking)."""
    return match(text, re.compile(r'(?!)'), context=context)

def check_type(obj, type_template, context=None):
    """Check that obj is of the expected type."""
    atypes = {
        dict: 'an object',
        list: 'an array',
    }
    expected_type = type(type_template)
    atype = atypes.get(expected_type)
    if atype is None:
        internal_error('check_type(): unknown type', 1)
    
    if type(obj) != expected_type:
        scraping_error(f"{context}: not {atype}")
    
    return obj

def unpack_list(dst, src, context=None):
    """Unpack a list into variables."""
    if not isinstance(dst, list):
        internal_error('unpack_list(): invalid argument', 1)
    
    if not isinstance(src, list):
        scraping_error(f"{context}: not an array")
    
    n = len(dst)
    m = len(src)
    s = '' if n == 1 else 's'
    
    if n != m:
        scraping_error(f"{context}: expected {n} element{s}, got {m}")
    
    for i in range(n):
        var = dst[i]
        val = src[i]
        if var is not None:
            var[0] = val

def os_error(message):
    """Handle OS errors."""
    caller_name = traceback.extract_stack()[-2].name
    if caller_name != 'write_log':
        write_log(message)
    traceback.print_stack()
    print(message, file=sys.stderr)
    sys.exit(4)

def internal_error(message, level=0):
    """Handle internal errors."""
    message = f"Internal error: {message}"
    write_log(message)
    traceback.print_stack()
    print(message, file=sys.stderr)
    print(bugreport_request, file=sys.stderr)
    sys.exit(255)

def known_bug(bugno, message):
    """Report a known bug."""
    url = bugreport_url_tmpl % bugno
    message += f"; see <{url}>"
    warning(message)
    sys.exit(255)

def kwargs(options, **args):
    """Process keyword arguments with validation."""
    caller = traceback.extract_stack()[-2].name
    
    for name, var_info in args.items():
        has_default = False
        value = None
        
        if isinstance(var_info, list):
            if len(var_info) != 2:
                internal_error('kwargs(): invalid argument', 1)
            var, value = var_info
            has_default = True
        else:
            var = var_info
        
        if name in options:
            value = options.pop(name)
        elif not has_default:
            internal_error(f"{caller}(): missing keyword argument: {name}", 1)
        
        var[0] = value
    
    if options:
        names = sorted(options.keys())
        s = 's' if len(names) > 1 else ''
        message = f"{caller}(): invalid keyword argument{s}: {', '.join(names)}"
        internal_error(message, 1)

# ====================
# internationalization
# ====================

_encoding_fallback = {
    0x104: 'A', 0x105: 'a',  # letter A with ogonek
    0x0C1: 'A', 0x0E1: 'a',  # letter A with acute
    0x0C4: 'A', 0x0E4: 'a',  # letter A with diaeresis
    0x106: 'C', 0x107: 'c',  # letter C with acute
    0x10C: 'C', 0x10D: 'c',  # letter C with caron
    0x10E: 'D', 0x10F: 'd',  # letter D with caron
    0x118: 'E', 0x119: 'e',  # letter E with ogonek
    0x0C9: 'E', 0x0E9: 'e',  # letter E with acute
    0x11A: 'E', 0x11B: 'e',  # letter E with caron
    0x0CD: 'I', 0x0ED: 'i',  # letter I with acute
    0x141: 'L', 0x142: 'l',  # letter L with stroke
    0x139: 'L', 0x13A: 'l',  # letter L with acute
    0x13D: 'L', 0x13E: 'l',  # letter L with caron
    0x143: 'N', 0x144: 'n',  # letter N with acute
    0x147: 'N', 0x148: 'n',  # letter N with caron
    0x0D3: 'O', 0x0F3: 'o',  # letter O with acute
    0x0D4: 'O', 0x0F4: 'o',  # letter O with circumflex
    0x154: 'R', 0x155: 'r',  # letter R with acute
    0x158: 'R', 0x159: 'r',  # letter R with caron
    0x15A: 'S', 0x15B: 's',  # letter S with acute
    0x160: 'S', 0x161: 's',  # letter S with caron
    0x164: 'T', 0x165: 't',  # letter T with caron
    0x0DA: 'U', 0x0FA: 'u',  # letter U with acute
    0x16E: 'U', 0x16F: 'u',  # letter U with ring above
    0x0DD: 'Y', 0x0FD: 'y',  # letter Y with acute
    0x179: 'Z', 0x17A: 'z',  # letter Z with acute
    0x17B: 'Z', 0x17C: 'z',  # letter Z with dot above
    0x17D: 'Z', 0x17E: 'z',  # letter Z with caron
}

def _encoding_fallback_fn(u):
    """Get fallback character for encoding."""
    return _encoding_fallback.get(u, f'<U+{u:04X}>')

def bytes_to_unicode(u, encoding=None):
    """Convert bytes to unicode string."""
    if encoding is None:
        encoding = locale.getpreferredencoding(False)
    return u.decode(encoding)

def unicode_to_bytes(s, encoding=None):
    """Convert unicode string to bytes with fallback."""
    if encoding is None:
        encoding = locale.getpreferredencoding(False)
    
    def error_handler(exc):
        if isinstance(exc, UnicodeEncodeError):
            result = []
            for i in range(exc.start, exc.end):
                c = ord(exc.object[i])
                fallback = _encoding_fallback_fn(c)
                result.append(fallback)
            return (''.join(result), exc.end)
        raise exc
    
    codecs.register_error('custom_fallback', error_handler)
    return s.encode(encoding, errors='custom_fallback')

country_to_language = {
    'cz': 'cs',  # Czech Republic => Czech
    'pl': 'pl',  # Poland => Polish
    'sk': 'sk',  # Slovakia => Slovak
}

language_to_country = {v: k for k, v in country_to_language.items()}

locale_aliases = {
    'polish': 'pl',
    'czech': 'cs',
    'slovak': 'sk',
}

tz_to_language = {
    'Europe/Bratislava': 'sk',
    'Europe/Prague': 'cz',
    'Europe/Warsaw': 'pl',
}

known_countries = sorted(country_to_language.keys())

def get_tz():
    """Get the current timezone."""
    tz = os.environ.get('TZ')
    if tz:
        tz = tz.lstrip(':')
        return tz
    
    try:
        tz_link = os.readlink('/etc/localtime')
        tz = re.sub(r'.*/zoneinfo/', '', tz_link)
        return tz
    except:
        pass
    
    try:
        with open('/etc/timezone', 'r') as fh:
            tz = fh.read().strip()
            return tz
    except:
        pass
    
    return None

def guess_country():
    """Guess the country from locale settings."""
    cc = {}
    
    try:
        locales = locale.getlocale()
        locale_str = locales[0] if locales[0] else ''
        
        # Check locale
        if locale_str:
            locale_name = locale_aliases.get(locale_str.lower(), locale_str)
            lang = locale_name.split('_')[0]
            country = language_to_country.get(lang)
            if country:
                cc[country] = True
    except:
        pass
    
    cc_list = list(cc.keys())
    if len(cc_list) == 1:
        return cc_list[0]
    
    if len(cc_list) == 0:
        tz = get_tz()
        country = tz_to_language.get(tz)
        return country
    
    return None

# ====================
# HTTP client identity
# ====================

# Extracted from Tor Browser 14.5.7 (based on Firefox 128 ESR):
browser_user_agent = 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128'
browser_name = 'Firefox'
browser_version = '128'
browser_dfp = 'eJyFkT1MFEEUx/dm/NhsUJcj4PmZDYUxJOgFDSEkhg89UDmQ4AfEZpzdnbubcXdnM7MHh9XaGSs7LCwsKYkVJYUFhSaUlMTExMpYUFyns3u35AiiL9ndt//fe/PmvWf0Gl1lGtQbVmNkGA3fzsOnczMFLX9NbxrmPiw0DWsfXm8axX04mi96OHClg0MyGArqY7F68YQBSNA/pX/eBXmdNEKPOjQqAAsM6DIk+CURspgb0UqasvuxOR/rS99+ty334sOB63/9Uh4buDOudcUqckv7v8VHlCFj/t6U9YySFSKGuu/WBPeJ1SH1pBKt+53ihVnqCC55JbJKbvVw/CKxZ2hk2XXqRYM0SNioNv56be3TmYendM3UCtoCnLs5kb6e543Ts/wV9TyczxxbY30Tc9PlEqKBjHDgEBdhIfCqZGZp6QmyPRK4yKeBjxvsUqI43OMC2fVKhQhUw14FVTyOI3YuganbSmJnU0HgKnJJGNVYX/Iva9hVeRFpRHVBkMddpqf6wvQku5x4GXK4HwoiJeUBssPIOZ6KqqJXO2lFjUNVwQGVPBI8pA7re1R6jIhHfBJEqleXNFCdBhHrTfSKzZFQd1Y5Pg19HLJCIicDcbFwVQOCLuOILhPJuhNyUChtvXBEQh4NCBatqhnpGNaVv+tZ2vkELxOhIlrbQNxmxFGVFkuT0+XDO2ifmJHWXNQas+OxTIZ3LCaKHp8sbync/0+MpKjarKcVk646wyzfFgVead9WZprHZbLFIAkVD9aBvgH0TaBvAX0bFHaAtgticw+YP9TnF9jLNYEew9h8A/V30HwP9Y8wBuswtwFzmzC3Bce2YWztqOdt7uT3n3Dzxh8LG3RL'

# =========
# HTTP, TLS
# =========

ua = None
http_read_size_hint = 1 << 20  # 1 MiB
http_timeout = 60

def http_init(cookie_jar=None, ca=None):
    """Initialize HTTP client with SSL/TLS settings."""
    global ua
    
    # Remove HTTPS_* environment variables
    for key in list(os.environ.keys()):
        if key.startswith('HTTPS_'):
            del os.environ[key]
    
    # Create SSL context
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = True
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    
    # Set minimum TLS version
    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
    
    if ca:
        ssl_context.load_verify_locations(cafile=ca)
    
    # Create cookie jar
    if cookie_jar and cookie_jar != '/dev/null':
        cj = http.cookiejar.MozillaCookieJar(cookie_jar)
        try:
            cj.load(ignore_discard=True, ignore_expires=True)
        except FileNotFoundError:
            pass
    else:
        cj = http.cookiejar.CookieJar()
    
    # Create opener with cookie support
    https_handler = urllib.request.HTTPSHandler(context=ssl_context)
    cookie_processor = urllib.request.HTTPCookieProcessor(cj)
    opener = urllib.request.build_opener(https_handler, cookie_processor)
    opener.addheaders = [
        ('User-Agent', browser_user_agent),
        ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
        ('Accept-Encoding', 'gzip, deflate'),
        ('Accept-Language', 'en-US,en;q=0.5'),
    ]
    
    ua = opener
    ua.cookie_jar = cj
    
    return ua

def download(request, ignore_errors=False, redact=None):
    """Download content from a URL."""
    method = request.get_method()
    url = request.full_url
    message = f'{method} {url}'
    
    if opt_debug_interactive:
        print(f"Request: {method} {url}", file=sys.stderr)
        ok = input('Proceed? [y]: ') or 'y'
        if ok != 'y':
            user_error('aborted by user')
    
    debug(message)
    
    try:
        response = ua.open(request, timeout=http_timeout)
        content = response.read()
        
        # Handle gzip/deflate encoding
        encoding = response.headers.get('Content-Encoding')
        if encoding == 'gzip':
            import gzip
            content = gzip.decompress(content)
        elif encoding == 'deflate':
            import zlib
            content = zlib.decompress(content)
        
        content = content.decode('utf-8', errors='replace')
        content = content.replace('\r', '')
        
        # Save debug output
        if opt_debug_dir:
            is_json = response.headers.get('Content-Type', '').startswith('application/json')
            default_ext = 'json' if is_json else 'html'
            
            path = url.split('//', 1)[-1]
            path = path.split('?')[0]
            path = re.sub(r'[^a-zA-Z0-9.]', '_', path)
            if not path or path == '_':
                path = 'index'
            path = f"{path}.{default_ext}"
            
            full_path = os.path.join(opt_debug_dir, path)
            with open(full_path, 'w', encoding='utf-8') as fh:
                fh.write(content)
            
            # Save request
            with open(f"{full_path}.request", 'w', encoding='utf-8') as fh:
                request_dump = f"{method} {url}\n"
                for header, value in request.headers.items():
                    if redact and redact in value:
                        value = '<redacted>'
                    request_dump += f"{header}: {value}\n"
                fh.write(request_dump)
            
            # Save response headers
            with open(f"{full_path}.headers", 'w', encoding='utf-8') as fh:
                fh.write(f"HTTP {response.status} {response.reason}\n")
                for header, value in response.headers.items():
                    fh.write(f"{header}: {value}\n")
        
        return {
            'response': response,
            'content': content,
            'url': response.geturl(),
        }
    
    except urllib.error.HTTPError as e:
        if isinstance(ignore_errors, list):
            if e.code in ignore_errors:
                return {'response': e, 'content': '', 'url': url}
        if not ignore_errors:
            class FakeRequest:
                def __init__(self, method, url):
                    self.method = method
                    self.full_url = url
            http_error(FakeRequest(method, url), e)
        raise
    except Exception as e:
        os_error(f"Request failed: {e}")

def simple_download(request):
    """Simple download without full processing."""
    method = request.get_method()
    url = request.full_url
    message = f'simple {method} {url}'
    debug(message)
    
    try:
        response = ua.open(request, timeout=http_timeout)
        return response
    except urllib.error.HTTPError as e:
        class FakeRequest:
            def __init__(self, method, url):
                self.method = method
                self.full_url = url
        http_error(FakeRequest(method, url), e)

def get_default_ca_path(name, *hashes):
    """Get the default CA certificate path."""
    filename = name.replace(' ', '_') + '.crt'
    path = f"/usr/share/ca-certificates/mozilla/{filename}"
    if os.path.isfile(path):
        return path
    
    ssl_cert_dir = os.environ.get('SSL_CERT_DIR')
    if not ssl_cert_dir and os.path.exists('/etc/ssl/certs'):
        ssl_cert_dir = '/etc/ssl/certs'
    
    if ssl_cert_dir:
        for hash_val in hashes:
            path = f"{ssl_cert_dir}/{hash_val}.0"
            if os.path.isfile(path):
                try:
                    rpath = os.readlink(path)
                    if not rpath.startswith('/'):
                        rpath = os.path.join(ssl_cert_dir, rpath)
                    return rpath
                except:
                    return path
    
    return os.path.join(os.path.dirname(__file__), 'ca.crt')

# ===========================
# configuration file handling
# ===========================

global_config = None
gpg_cmdline = os.environ.get('MBANK_CLI_GPG', 'gpg').split()

# Set GPG_TTY if not set
if 'GPG_TTY' not in os.environ:
    try:
        os.environ['GPG_TTY'] = os.ttyname(sys.stdin.fileno())
    except:
        pass

def read_config(path):
    """Read configuration file."""
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            config = _read_config(fh, path)
        return config
    except OSError as e:
        os_error(f"{path}: {e}")

def _read_config(fh, path):
    """Internal function to read configuration."""
    pgp = None
    config = {
        '__pgp__': [],
        '__path__': path,
    }
    
    for line in fh:
        line = line.rstrip('\n')
        
        if pgp is not None:
            pgp += line + '\n'
            if line == '-----END PGP MESSAGE-----':
                config['__pgp__'].append(pgp)
                pgp = None
        elif line == '-----BEGIN PGP MESSAGE-----':
            pgp = line + '\n'
        elif re.match(r'^(?:#|\s*$)', line):
            continue
        elif m := re.match(r'^\s*([\w-]+)\s+(.*\S)\s*$', line):
            key, value = m.groups()
            key = key.lower()
            # Simple shell-like parsing (remove quotes)
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            config[key] = value
        else:
            config_error(f"syntax error: {line}", config=path)
    
    return config

def _decrypt_config(config):
    """Decrypt encrypted configuration parts."""
    pgp_chunks = config['__pgp__']
    config['__pgp__'] = []
    
    if not pgp_chunks:
        return
    
    try:
        import subprocess
    except ImportError:
        user_error('subprocess is required to decrypt the configuration file')
    
    for encrypted_data in pgp_chunks:
        try:
            result = subprocess.run(
                gpg_cmdline + ['-d'],
                input=encrypted_data.encode('utf-8'),
                capture_output=True,
                check=True
            )
            decrypted_data = result.stdout.decode('utf-8')
        except subprocess.CalledProcessError as e:
            os_error(f"{' '.join(gpg_cmdline)} -d failed: {e}")
        
        for line in decrypted_data.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            elif m := re.match(r'^\s*([\w-]+)\s+(.*\S)\s*$', line):
                key, value = m.groups()
                key = key.lower()
                value = value.strip()
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                config[key] = value
            else:
                config_error(f"syntax error in encrypted part: {line}", config=config)
    
    return config

def get_config_var(var, default=None):
    """Get a configuration variable."""
    config = global_config
    
    if var in config or default is not None:
        return config.get(var, default)
    
    _decrypt_config(config)
    return config.get(var)

def config_error(message, config=None):
    """Report a configuration error."""
    if config is None:
        config = global_config
    
    if isinstance(config, dict):
        config_path = config.get('__path__', 'config')
    else:
        config_path = config
    
    message = f"{config_path}: {message}"
    return user_error(message)

# ===========================
# misc parsing and formatting
# ===========================

account_number_re = re.compile(r'''
    \d{2}(?:[ ]\d{4}){6}  # Polish IBAN (without the country code)
  | CZ\d{2}(?:[ ]\d{4}){5}  # Czech IBAN
  | SK\d{2}(?:[ ]\d{4}){5}  # Slovak IBAN
  | (?:\d{1,6}-)?\d{2,10}/\d{4}  # Slovak national format
''', re.VERBOSE)

def format_account_number(number):
    """Format an account number."""
    if not number:
        return number
    
    number = number.replace('PL', '', 1)
    number = number.replace(' ', '')
    
    if re.match(r'^\d{26}$', number):
        m = re.match(r'^(\d{2})(\d{4})(\d{4})(\d{4})(\d{4})(\d{4})(\d{4})$', number)
        if m:
            number = ' '.join(m.groups())
    
    return number

def format_amount(s, fp=False, plus=False, currency=None):
    """Format an amount with currency."""
    if fp:
        if not currency:
            internal_error('floating-point number, but no currency')
        s = format_number('%.2f', s)
    
    s = re.sub(r'[\s\xa0]+(?=\d)', '', s)
    
    sign_re = r'[+-]?' if plus else r'-?'
    amount_re = rf'({sign_re}\d+[.,]\d{{2}})'
    
    if currency:
        if not re.match(r'^[A-Z]{3}$', currency):
            return None
        currency_re = r''
    else:
        currency_re = r'\s+([A-Z]{3})'
    
    m = re.match(rf'^{amount_re}{currency_re}$', s)
    if not m:
        return None
    
    amount = m.group(1)
    if not currency:
        currency = m.group(2)
    
    amount = amount.replace(',', '.')
    return f'{amount:>10} {currency}'

def format_money(number, currency, context=None):
    """Format money with proper alignment."""
    match(number, re.compile(r'-?[\d ]+(?:[.,]\d+)?'), context=f"{context}.number" if context else None)
    number = number.replace(' ', '')
    number = number.replace(',', '.')
    match(currency, re.compile(r'[A-Z]{3}'), context=f"{context}.currency" if context else None)
    
    try:
        s = f'{float(number):>10.2f} {currency}'
        return s
    except:
        qnumber = quote(number)
        qcurrency = quote(currency)
        scraping_error(f"{context}: {qnumber}, {qcurrency}")

def format_number(fmt, n):
    """Format a number with the given format string."""
    try:
        return fmt % n
    except:
        return None

def wildcards_to_regexp(*wildcards):
    """Convert shell wildcards to a compiled regex."""
    patterns = []
    for wildcard in wildcards:
        pattern = re.escape(wildcard)
        pattern = pattern.replace(r'\*', '.*')
        patterns.append(pattern)
    
    re_str = '^(?i:(' + '|'.join(patterns) + '))$'
    return re.compile(re_str)

# =============
# date and time
# =============

def timestamp_to_date(timestamp, time_must_be=None):
    """Convert ISO timestamp to date string.
    
    >>> timestamp_to_date('2006-07-30T14:47:03')
    '2006-07-30'
    
    >>> timestamp_to_date('2006-02-30T14:47:03')
    None
    
    >>> timestamp_to_date('2006-07-30T14:47:03', time_must_be=0)
    None
    
    >>> timestamp_to_date('2006-07-30T00:00:00', time_must_be=0)
    '2006-07-30'
    """
    if not timestamp:
        return None
    
    m = re.match(r'^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}(?:\.\d+)?)(?:[+-]\d{2}:\d{2})?$', timestamp)
    if not m:
        return None
    
    date, time_part = m.groups()
    
    if time_must_be is not None:
        if time_must_be == 0:
            if not re.match(r'^[0:.]+$', time_part):
                return None
        else:
            internal_error('invalid time_must_be')
    
    try:
        dt = datetime.strptime(date, '%Y-%m-%d')
        pdate = dt.strftime('%Y-%m-%d')
        if date != pdate:
            return None
        return date
    except:
        return None

def match_ymd_date(timestamp, context=None, time_must_be=None):
    """Match a timestamp and extract the date."""
    result = timestamp_to_date(timestamp, time_must_be=time_must_be)
    if result:
        return result
    return no_match(timestamp, context=context)

