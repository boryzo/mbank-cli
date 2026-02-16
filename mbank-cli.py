#!/usr/bin/env python3

# Python port of the original mbank-cli by Jakub Wilk <jwilk@jwilk.net>.
# Original project: https://github.com/jwilk/mbank-cli

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
import gzip
import zlib
from datetime import datetime, timezone

opt_verbose = 0
opt_debug_dir = None
opt_debug_interactive = 0

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
    
    # Only read error content for client-side errors (like SSL failures)
    # This matches the Perl version which checks for "Client-Warning: Internal response"
    client_warning = response.headers.get('Client-Warning', '')
    if response.status == 500 and client_warning == 'Internal response':
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

def scraping_error(message):
    """Handle web scraping errors."""
    message = f"Scraping error: {message}"
    write_log(message)
    traceback.print_stack()
    print(message, file=sys.stderr)
    sys.exit(3)

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

def first_defined(*values):
    for value in values:
        if value is not None:
            return value
    return None

def match(text, pattern, context=None):
    """Match text against a pattern with context."""
    if isinstance(pattern, str):
        pattern = re.compile(re.escape(pattern))
    
    if not isinstance(pattern, re.Pattern):
        internal_error('match(): invalid argument', 1)
    
    # Perl version accepts numeric scalars in regex matches; keep parity here.
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        text = str(text)
    
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
    sys.exit(255)

def unicode_display(s):
    """Convert text for terminal display."""
    if s is None:
        return ''
    return str(s)

country_to_language = {
    'cz': 'cs',  # Czech Republic => Czech
    'pl': 'pl',  # Poland => Polish
    'sk': 'sk',  # Slovakia => Slovak
}

known_countries = sorted(country_to_language.keys())

def guess_country():
    """Guess country code from locale."""
    try:
        loc = locale.getlocale()[0] or ''
    except Exception:
        return None
    if '_' not in loc:
        return None
    cc = loc.split('_', 1)[1].lower()
    if cc in country_to_language:
        return cc
    return None

browser_user_agent = 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128'
browser_name = 'Firefox'
browser_version = '128'
browser_dfp = 'eJyFkT1MFEEUx/dm/NhsUJcj4PmZDYUxJOgFDSEkhg89UDmQ4AfEZpzdnbubcXdnM7MHh9XaGSs7LCwsKYkVJYUFhSaUlMTExMpYUFyns3u35AiiL9ndt//fe/PmvWf0Gl1lGtQbVmNkGA3fzsOnczMFLX9NbxrmPiw0DWsfXm8axX04mi96OHClg0MyGArqY7F68YQBSNA/pX/eBXmdNEKPOjQqAAsM6DIk+CURspgb0UqasvuxOR/rS99+ty334sOB63/9Uh4buDOudcUqckv7v8VHlCFj/t6U9YySFSKGuu/WBPeJ1SH1pBKt+53ihVnqCC55JbJKbvVw/CKxZ2hk2XXqRYM0SNioNv56be3TmYendM3UCtoCnLs5kb6e543Ts/wV9TyczxxbY30Tc9PlEqKBjHDgEBdhIfCqZGZp6QmyPRK4yKeBjxvsUqI43OMC2fVKhQhUw14FVTyOI3YuganbSmJnU0HgKnJJGNVYX/Iva9hVeRFpRHVBkMddpqf6wvQku5x4GXK4HwoiJeUBssPIOZ6KqqJXO2lFjUNVwQGVPBI8pA7re1R6jIhHfBJEqleXNFCdBhHrTfSKzZFQd1Y5Pg19HLJCIicDcbFwVQOCLuOILhPJuhNyUChtvXBEQh4NCBatqhnpGNaVv+tZ2vkELxOhIlrbQNxmxFGVFkuT0+XDO2ifmJHWXNQas+OxTIZ3LCaKHp8sbync/0+MpKjarKcVk646wyzfFgVead9WZprHZbLFIAkVD9aBvgH0TaBvAX0bFHaAtgticw+YP9TnF9jLNYEew9h8A/V30HwP9Y8wBuswtwFzmzC3Bce2YWztqOdt7uT3n3Dzxh8LG3RL'

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
            # Cookie file doesn't exist yet, will be created on save
            pass
        except http.cookiejar.LoadError as e:
            # Cookie file exists but is corrupted or in wrong format
            # Start with empty cookie jar (will overwrite on save)
            debug(f"Cookie file load error (will start fresh): {e}")
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

def _decode_http_content(content, headers):
    """Decode HTTP content handling gzip/deflate encoding."""
    # Handle gzip/deflate encoding
    encoding = headers.get('Content-Encoding')
    if encoding == 'gzip':
        content = gzip.decompress(content)
    elif encoding == 'deflate':
        content = zlib.decompress(content)
    
    content = content.decode('utf-8', errors='replace')
    content = content.replace('\r', '')
    return content

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
        content = _decode_http_content(content, response.headers)
        
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
                # Read error response content (similar to Perl's decoded_content)
                content = e.read()
                
                content = _decode_http_content(content, e.headers)
                
                return {'response': e, 'content': content, 'url': url}
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

global_config = None
gpg_cmdline = os.environ.get('MBANK_CLI_GPG', 'gpg').split()
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

account_number_re = re.compile(r'''
    \d{2}(?:[ ]\d{4}){6}  # Polish IBAN (without the country code)
  | CZ\d{2}(?:[ ]\d{4}){5}  # Czech IBAN
  | SK\d{2}(?:[ ]\d{4}){5}  # Slovak IBAN
  | (?:\d{1,6}-)?\d{2,10}/\d{4}  # Slovak national format
''', re.VERBOSE)

mbank_account_known_fields = {
    'ProductName', 'SubTitle', 'AccountNumber', 'Currency',
    'Balance', 'AvailableBalance',
}

external_account_known_fields = {
    'name', 'productName', 'ProductName', 'externalAccountName', 'accountTypeName',
    'number', 'accountNumber', 'iban', 'Iban',
    'balance', 'Balance', 'availableBalance', 'AvailableBalance',
    'currency', 'Currency', 'bankName', 'providerName', 'provider',
    'bankAvatarName',
}

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

def format_money(number, currency, context=None):
    """Format money with proper alignment."""
    match(number, re.compile(r'-?[\d ]+(?:[.,]\d+)?'), context=f"{context}.number" if context else None)
    number = str(number)
    number = number.replace(' ', '')
    number = number.replace(',', '.')
    match(currency, re.compile(r'[A-Z]{3}'), context=f"{context}.currency" if context else None)
    currency = str(currency)
    
    try:
        s = f'{float(number):.2f} {currency}'
        return s
    except:
        qnumber = quote(number)
        qcurrency = quote(currency)
        scraping_error(f"{context}: {qnumber}, {qcurrency}")

def safe_format_money(number, currency, context):
    if number is None:
        return ''
    currency = '' if currency is None else str(currency)
    if not currency:
        return ''
    if not re.fullmatch(r'[A-Z]{3}', currency):
        warning(f"{context}.currency: invalid value {quote(currency)}")
        return ''
    text = str(number).replace('\xa0', ' ')
    if not re.fullmatch(r'-?[\d ]+(?:[.,]\d+)?', text):
        warning(f"{context}.number: invalid value {quote(number)}")
        return ''
    try:
        value = float(text.replace(' ', '').replace(',', '.'))
    except Exception:
        warning(f"{context}.number: invalid value {quote(number)}")
        return ''
    return f'{value:.2f} {currency}'

def timestamp_to_date(timestamp, time_must_be=None):
    """Convert ISO timestamp to date string."""
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

def decode_json(json_str, context=None, type=None):
    if type is None:
        type = {}
    
    try:
        obj = json.loads(json_str)
    except json.JSONDecodeError as e:
        scraping_error(f"{context}: {e}")
    
    return check_type(obj, type, context=context)

uuid_template = 'XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX'

def parse_uuid(s):
    """Parse and validate a UUID string."""
    if not isinstance(s, str):
        return None
    uuid_pattern = uuid_template.replace('X', '[0-9a-fA-F]')
    if re.match(f'^{uuid_pattern}$', s):
        return s
    return None

def gen_uuid():
    """Generate a random UUID."""
    import uuid
    return str(uuid.uuid4())

def match_uuid(s, context=None):
    """Match and validate a UUID string."""
    result = parse_uuid(s)
    if result:
        return result
    return no_match(s, context=context)

def term_readpasswd(prompt='Password: '):
    """Read password from terminal."""
    return getpass.getpass(prompt)

VERSION = '20250101'  # Version placeholder
mbank_host = None
root_url = None
base_url = None
csite_url = None

opt_config = None
opt_cookie_jar = None

header_xhr = {
    'X-Requested-With': 'XMLHttpRequest',
}

header_accept_json = {
    'Accept': 'application/json, text/javascript, */*; q=0.01',
}

def show_help():
    """Show help message."""
    print("""Usage: mbank-cli [OPTIONS] COMMAND [ARGS...]

Options:
  --verbose               Enable verbose output
  --debug DIR             Enable debug mode and save debug info to DIR
  --debug-interactive     Enable interactive debugging
  --config FILE           Configuration file path
  --cookie-jar FILE       Cookie jar file path
  -h, --help              Show this help
  --version               Show version

Commands:
  list                    List accounts
  logout                  Logout
  register-device         Register device
  activate-profile        Activate profile
  configure               Configure mbank-cli
""")
    sys.exit(0)

def show_version():
    """Show version information."""
    print(f"mbank-cli {VERSION}")
    print(f"+ Python {sys.version.split()[0]}")
    print(f"+ urllib.request (built-in)")
    print(f"+ http.cookiejar (built-in)")
    sys.exit(0)

def expand_tilde(path):
    """Expand ~ in file paths."""
    if path.startswith('~'):
        return os.path.expanduser(path)
    return path

def unexpand_tilde(path):
    """Replace home directory with ~ in path."""
    home = os.path.expanduser('~')
    if path.startswith(home):
        return '~' + path[len(home):]
    return path

def xdg_config_home():
    """Get XDG config home directory."""
    xdg = os.environ.get('XDG_CONFIG_HOME')
    if xdg:
        return xdg
    return os.path.expanduser('~/.config')

def xdg_data_home():
    """Get XDG data home directory."""
    xdg = os.environ.get('XDG_DATA_HOME')
    if xdg:
        return xdg
    return os.path.expanduser('~/.local/share')

def makedirs(path):
    """Create directory and parents if needed."""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        os_error(f"{path}: {e}")

def initialize():
    """Initialize configuration and HTTP client."""
    global global_config, ua, mbank_host, root_url, base_url, csite_url
    
    if not os.path.exists(opt_config):
        user_error(
            f"missing configuration file: {opt_config}\n" +
            'Run "mbank-cli configure" or create the configuration file manually.'
        )
    
    global_config = read_config(opt_config)
    
    if opt_cookie_jar:
        cookie_jar_path = opt_cookie_jar
    else:
        cookie_jar_path = get_config_var('cookiejar')
        if not cookie_jar_path:
            config_error('missing cookiejar')
        cookie_jar_path = expand_tilde(cookie_jar_path)
    
    debug(f"cookiejar = {cookie_jar_path}")
    
    ca_path = get_config_var('cafile')
    if ca_path:
        ca_path = expand_tilde(ca_path)
        if not os.path.isfile(ca_path):
            os_error(f"{ca_path}: file not found")
        debug(f"cafile = {ca_path}")
    
    tld = get_config_var('country')
    if not tld:
        config_error('missing country')
    
    tld = tld.lower()
    lang = country_to_language.get(tld)
    if not lang:
        user_error(f"unknown country {tld.upper()}, not in {', '.join(known_countries).upper()}")
    
    mbank_host = f"online.mbank.{tld}"
    root_url = f"https://{mbank_host}"
    base_url = f"https://{mbank_host}/{lang}"
    csite_url = f"https://{mbank_host}/csite"
    
    http_init(cookie_jar=cookie_jar_path, ca=ca_path)

def parse_args():
    """Parse command-line arguments."""
    global opt_verbose, opt_debug_dir, opt_debug_interactive
    global opt_config, opt_cookie_jar
    
    parser = argparse.ArgumentParser(
        prog='mbank-cli',
        add_help=False,
        description='Command-line interface to mBank'
    )
    
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--debug', metavar='DIR', help='Enable debug mode')
    parser.add_argument('--debug-interactive', action='store_true', help='Enable interactive debugging')
    parser.add_argument('--config', metavar='FILE', help='Configuration file')
    parser.add_argument('--cookie-jar', metavar='FILE', help='Cookie jar file')
    parser.add_argument('-h', '--help', action='store_true', help='Show help')
    parser.add_argument('--version', action='store_true', help='Show version')
    parser.add_argument('command', nargs='?', help='Command to execute')
    parser.add_argument('args', nargs='*', help='Command arguments')
    
    try:
        args = parser.parse_args()
    except SystemExit:
        user_error('Invalid arguments')
    
    if args.help:
        show_help()
    
    if args.version:
        show_version()
    
    opt_verbose = args.verbose
    opt_debug_interactive = args.debug_interactive
    opt_config = args.config or os.path.join(xdg_config_home(), 'mbank-cli', 'config')
    opt_cookie_jar = args.cookie_jar
    
    if args.debug:
        if args.debug.startswith('-'):
            user_error(f"suspicious directory name for --debug: {args.debug}")
        makedirs(args.debug)
        opt_debug_dir = args.debug
    
    command = args.command or 'list'
    return command, args.args

def _extract_login_profiles(page_content):
    """Extract available profiles from the post-login page."""
    def extract_js_object_assignment(content, var_name):
        marker_pos = content.find(var_name)
        if marker_pos < 0:
            return None
        
        eq_pos = content.find('=', marker_pos + len(var_name))
        if eq_pos < 0:
            return None
        
        start = content.find('{', eq_pos + 1)
        if start < 0:
            return None
        
        depth = 0
        in_string = False
        string_quote = ''
        escaped = False
        
        for i in range(start, len(content)):
            ch = content[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == '\\':
                    escaped = True
                elif ch == string_quote:
                    in_string = False
                continue
            
            if ch == '"' or ch == "'":
                in_string = True
                string_quote = ch
                continue
            
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return content[start:i + 1]
        
        return None

    profiles = {
        'personal': [],
        'business': [],
    }

    for m in re.finditer(r'<script\b[^>]*>(.*?)</script>', page_content, re.IGNORECASE | re.DOTALL):
        content = m.group(1)
        json_payload = extract_js_object_assignment(content, 'Ebre.Venezia.ProfileData')
        if not json_payload:
            continue
        
        data = decode_json(json_payload, context='login.profiles.json')
        
        for key, value in data.items():
            if key == 'iProfiles':
                key = 'personal'
            elif key == 'fProfiles':
                key = 'business'
            else:
                no_match(key, context='login.profiles.key')
            
            if not isinstance(value, dict):
                scraping_error(f'login.profiles.{key}: not an object')
            js_profiles = value.get('profiles', [])
            if not isinstance(js_profiles, list):
                scraping_error(f'login.profiles.{key}.profiles: not an array')
            
            n = 0
            for js_profile in js_profiles:
                if not isinstance(js_profile, dict):
                    scraping_error(f'login.profiles.{key}.profile: not an object')
                code = match(js_profile.get('profileCode', ''), re.compile(r'.+'), context='login.profiles.profile-code')
                profiles[key].append(code)
                n += 1
                
                if key == 'business':
                    name = match(js_profile.get('firmName', ''), re.compile(r'.+'), context='login.profiles.company-name')
                else:
                    name = f'{key}/{code}'
                profiles.setdefault(name, []).append(code)
            
            if n > 1:
                profiles.pop(key, None)
        
        break
    
    return profiles

def do_login(probe=False, register_device=None):
    """Perform login with authentication."""
    global ua
    
    # Initial request to check if we're already logged in
    request = urllib.request.Request(base_url)
    doc = download(request)
    
    if '/Login' in doc['url']:
        if probe:
            debug('not logged in')
            return None
        
        clear_temp_cookies()
        debug('logging in...')
        
        # Extract language and return URL
        lang_match = re.search(r'/(\w\w)$', base_url)
        lang = lang_match.group(1) if lang_match else 'pl'
        
        return_url_match = re.search(
            rf"'/signin/connect/authorize\?ui_locales={lang}&(request_uri=urn%3aietf%3aparams%3aoauth%3arequest_uri%3a[0-9A-F]+&client_id=Ib)'",
            doc['content']
        )
        if not return_url_match:
            scraping_error('login.return-url')
        
        return_url = return_url_match.group(1)
        return_url = return_url.replace('%3a', '%3A')
        return_url = f"/signin/connect/authorize/callback?{return_url}&suppressed_prompt=login"
        
        # Get login credentials
        login = get_config_var('login')
        if not login:
            config_error('missing login')
        
        # Get password
        password_manager = get_config_var('passwordmanager')
        if password_manager:
            import subprocess
            try:
                result = subprocess.run(
                    ['sh', '-c', password_manager],
                    capture_output=True,
                    text=True,
                    check=True
                )
                password = result.stdout.split('\n')[0]
            except subprocess.CalledProcessError:
                os_error('password manager failed')
        else:
            password = get_config_var('password')
            if not password:
                if sys.stdin.isatty():
                    password = term_readpasswd('Password: ')
                else:
                    config_error('missing password')
        
        if not password:
            user_error('login failed: empty password')
        
        # Make sure the SMSInbox feature is configured properly before we
        # try to log in (dummy date/number, try_num=0 triggers pre-check only):
        if get_config_var('smsinbox'):
            _ask_for_sms_password('2006-07-30', 1, 0)
        
        # Pre-login request
        headers_dict = {
            'Origin': root_url,
            'Referer': f'{root_url}/connect/Login',
            'Content-Type': 'application/json; charset=UTF-8',
        }
        
        prelogin_data = {
            'language': lang,
            'login': login,
            'password': password,
            'returnUrl': return_url,
        }
        
        request = urllib.request.Request(
            f'{root_url}/signin/connect/api/users/prelogin',
            data=json.dumps(prelogin_data).encode('utf-8'),
            headers=headers_dict,
            method='POST'
        )
        
        doc = download(request, ignore_errors=[422])
        data = decode_json(doc['content'], context='login.prelogin.json')
        
        if data.get('type') != 'PreLoginResponse':
            message = data.get('detail', '')
            user_error(f"login failed: {message}")
        
        # 2FA
        token = do_2fa(register_device)
        
        # Final login
        finallogin_data = {
            'language': lang.capitalize(),
            'returnUrl': return_url,
            'token': token,
        }
        
        request = urllib.request.Request(
            f'{root_url}/signin/connect/api/users/finallogin',
            data=json.dumps(finallogin_data).encode('utf-8'),
            headers=headers_dict,
            method='POST'
        )
        
        doc = download(request)
        data = decode_json(doc['content'], context='login.final')
        return_url = match(data.get('returnUrl', ''), re.compile(r'/.+'), context='login.final.return-url')
        
        # Follow return URL
        request = urllib.request.Request(f'{root_url}{return_url}')
        doc = download(request)
        
        # Get final page
        request = urllib.request.Request(base_url)
        doc = download(request)
    
    # Extract tab ID and CSRF token
    tabid = get_tabid()
    content = doc['content']

    # Check for technical break
    if re.search(r'<header\b[^>]*class=["\'][^"\']*\btech-break\b[^"\']*["\']', content, re.IGNORECASE):
        server_error('service is temporarily unavailable')

    # Get CSRF token
    csrf_token = None
    for meta in re.finditer(r'<meta\b[^>]*>', content, re.IGNORECASE):
        tag = meta.group(0)
        name_m = re.search(r'name=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if not name_m:
            continue
        if name_m.group(1) != '__AjaxRequestVerificationToken':
            continue
        content_m = re.search(r'content=["\']([^"\']+)["\']', tag, re.IGNORECASE)
        if content_m:
            csrf_token = content_m.group(1)
            break

    if not csrf_token or len(csrf_token) < 20:
        scraping_error(f'login.csrf-token: invalid token')
    profiles = _extract_login_profiles(content)
    
    debug('logged in')
    
    headers = {
        'Referer': doc['url'],
        'X-Tab-Id': tabid,
        'X-Request-Verification-Token': csrf_token,
    }
    headers.update(header_xhr)
    
    return {
        'headers': headers,
        'csrf_token': csrf_token,
        'profiles': profiles,
        'url': doc['url'],
    }

def do_2fa(device_to_add=None):
    """Handle 2-factor authentication."""
    headers_api_auth = {
        'Origin': root_url,
        'Referer': f'{root_url}/connect/Login',
        'Content-Type': 'application/json; charset=UTF-8',
    }
    
    # Get DFP
    dfp = get_config_var('dfp') or browser_dfp
    
    # SCA request
    request = urllib.request.Request(
        f'{root_url}/signin/connect/api/sca',
        data=json.dumps({'dfp': dfp}).encode('utf-8'),
        headers=headers_api_auth,
        method='POST'
    )
    
    doc = download(request)
    unexpire_cookie('mBank8', context='login.sca.cookie')
    
    data = decode_json(doc['content'], context='login.sca')
    sca_status = match(data.get('imsStatus', ''), re.compile(r'(Is|Not)Trusted|Suspicious'), context='login.sca.status')
    debug(f"SCA status: {sca_status}")
    sca_limit_exceeded = data.get('maximumNumberOfDevicesExceeded')
    if not isinstance(sca_limit_exceeded, bool):
        no_match(sca_limit_exceeded, context='login.sca.limit')
    
    if sca_status == 'IsTrusted':
        # No 2FA needed
        if device_to_add:
            user_error('device already registered')
        return match_uuid(data.get('token', ''), context='login.sca.token')
    
    # Prepare module data
    mod_data = {
        'authorizationAction': 1,  # OneTimeLogin
        'browserName': browser_name,
        'browserVersion': browser_version,
        'deviceName': f"Komputer Linux {browser_name}",
        'osName': 'Linux',
        'dfp': dfp,
    }
    
    if device_to_add:
        if sca_status != 'NotTrusted':
            user_error('device already registered')
        if sca_limit_exceeded:
            user_error('too many registered devices')
        # Validate device name uniqueness
        while True:
            request = urllib.request.Request(
                f'{root_url}/signin/connect/api/sca/uniqueDevice',
                data=json.dumps({'deviceName': device_to_add}).encode('utf-8'),
                headers=headers_api_auth,
                method='POST'
            )
            doc = download(request)
            unique_data = decode_json(doc['content'], context='login.sca.unique-dev')
            if unique_data.get('isUnique'):
                break
            print('Device name has been rejected. Try another one.', file=sys.stderr)
            new_name = input('Device name: ').strip()
            if len(new_name) > 1:
                device_to_add = new_name
        mod_data['authorizationAction'] = 2  # AddTrusted
        mod_data['deviceName'] = device_to_add
    
    # Initialize mediator
    request = urllib.request.Request(
        f'{root_url}/signin/connect/api/mediator/initialize',
        data=json.dumps({
            'moduleData': mod_data,
            'moduleId': 'IB20',
        }).encode('utf-8'),
        headers=headers_api_auth,
        method='POST'
    )
    
    doc = download(request)
    data = decode_json(doc['content'], context='login.2fa.init')
    auth_data = data.get('authorizationData', {})
    
    auth_mode = match(auth_data.get('authorizationType', ''), re.compile(r'\w+'), context='login.2fa.init.auth-type')
    auth_id = match_uuid(auth_data.get('authorizationId', ''), context='login.2fa.init.auth-id')
    auth_date = auth_data.get('authorizationDate', '')
    auth_date = timestamp_to_date(auth_date) or scraping_error(f"login.2fa.init.operation-date: {auth_date}")
    auth_no = match(auth_data.get('authorizationNumber', ''), re.compile(r'\d+'), context='login.2fa.init.operation-no')
    
    if auth_mode == 'MA':
        # Mobile app authorization
        print(f"Waiting for confirmation of operation no {auth_no} from {auth_date} in the mobile app...", file=sys.stderr)
        
        while True:
            request = urllib.request.Request(
                f'{root_url}/signin/connect/api/mediator/status',
                data=json.dumps({'authorizationId': auth_id}).encode('utf-8'),
                headers=headers_api_auth,
                method='POST'
            )
            
            doc = download(request)
            
            if doc['response'].status == 204:
                status = '_'
                data = {}
            else:
                data = decode_json(doc['content'], context='login.2fa.status')
                status = data.get('authorizationStatus', '')
            
            debug(f"2FA mobile auth: {status}")
            
            if status == '_':
                time.sleep(1)
            elif status == 'Authorized':
                token = data.get('postResult', {}).get('token')
                return match_uuid(token, context='login.2fa.status.token')
            elif status == 'Canceled':
                user_error('login failed: rejected mobile authentication request')
            elif status == 'TimeOut':
                user_error('login failed: mobile authentication request timed out')
            else:
                scraping_error(f"login.2fa.status.status: {status}")
    
    elif auth_mode == 'SMS':
        # SMS authorization
        try_num = 1
        while True:
            sms_password = _ask_for_sms_password(auth_date, auth_no, try_num)
            
            request = urllib.request.Request(
                f'{root_url}/signin/connect/api/mediator/authorize',
                data=json.dumps({
                    'authorizationCode': sms_password,
                    'authorizationId': auth_id,
                    'authorizationType': auth_mode,
                }).encode('utf-8'),
                headers=headers_api_auth,
                method='POST'
            )
            
            doc = download(request, ignore_errors=[422])
            data = decode_json(doc['content'], context='login.2fa.exec')
            token = data.get('postResult', {}).get('token')
            
            if token:
                return match_uuid(token, context='login.2fa.exec.token')
            else:
                error_code = data.get('type')
                if error_code == 'AuthApi-SMS014':
                    print('Incorrect SMS password', file=sys.stderr)
                    try_num += 1
                    continue
                else:
                    no_match(error_code, context='login.2fa.exec.error')
    
    else:
        no_match(auth_mode, context='login.2fa.init.auth-mode')
    
    return None

def _ask_for_sms_password(date, n, try_num):
    """Ask for SMS password from terminal."""
    if try_num == 0:
        return None
    if try_num > 1:
        print(f"(try #{try_num})", file=sys.stderr)
    return input(f"SMS password from {date} (operation #{n}): ")

def clear_temp_cookies():
    """Clear temporary cookies."""
    debug('clearing temporary cookies')
    if ua and hasattr(ua, 'cookie_jar'):
        # Keep parity with Perl implementation.
        ua.cookie_jar.clear_session_cookies()

def unexpire_cookie(name, context=None):
    """Make a cookie permanent (remove expiry)."""
    if not ua or not hasattr(ua, 'cookie_jar'):
        return
    
    cookie = None
    for c in ua.cookie_jar:
        if c.name != name:
            continue
        domain = (c.domain or '').lstrip('.')
        if domain == mbank_host:
            cookie = c
    
    if cookie is None:
        ctx = context or 'cookie'
        scraping_error(f"{ctx}: cookie {name} missing")
    
    if cookie.expires is None or cookie.discard:
        debug(f"setting expiration date for cookie {name}")
        cookie.expires = int(1e10)  # ~317 years
        cookie.discard = False
    
    if cookie.expires is None:
        internal_error(f"cookie {name} does not expire")
    
    expires = datetime.fromtimestamp(cookie.expires, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    debug(f"cookie {name} expires on {expires}")

def get_cookie_info(name):
    """Get a cookie value for mBank domain."""
    if not ua or not hasattr(ua, 'cookie_jar'):
        return None
    
    value = None
    for c in ua.cookie_jar:
        if c.name != name:
            continue
        domain = (c.domain or '').lstrip('.')
        if domain == mbank_host:
            value = c.value
    
    return value

def get_tabid():
    """Read tab ID from mBank cookie."""
    tabid = get_cookie_info('mBank_tabId')
    if tabid is None:
        scraping_error('login.tabid')
    return match_uuid(tabid, context='login.tabid')

def normalize_mbank_account(raw_account):
    if not isinstance(raw_account, dict):
        scraping_error('list.mbank.account: not an object')

    name = match(raw_account.get('ProductName', ''), re.compile(r'.+'), context='list.product-name')
    subtitle = raw_account.get('SubTitle', '')
    if subtitle:
        name += f" - {subtitle}"

    number = match(raw_account.get('AccountNumber', ''), account_number_re, context='list.account-number')
    return {
        'name': name,
        'number': number,
        'balance': raw_account.get('Balance'),
        'available': raw_account.get('AvailableBalance'),
        'currency': first_defined(raw_account.get('Currency'), ''),
        'source': 'mbank',
    }

def normalize_external_account(raw_account):
    if not isinstance(raw_account, dict):
        return None

    name = first_defined(
        raw_account.get('name'),
        raw_account.get('productName'),
        raw_account.get('ProductName'),
        raw_account.get('externalAccountName'),
        raw_account.get('accountTypeName'),
    )
    number = first_defined(
        raw_account.get('number'),
        raw_account.get('accountNumber'),
        raw_account.get('iban'),
        raw_account.get('Iban'),
    )
    if not name or not number:
        return None

    source = first_defined(
        raw_account.get('bankName'),
        raw_account.get('providerName'),
        raw_account.get('provider'),
        'external',
    )
    currency = first_defined(raw_account.get('currency'), raw_account.get('Currency'), '')
    currency = '' if currency is None else str(currency)
    if currency and not re.fullmatch(r'[A-Z]{3}', currency):
        warning(f"list.external.currency: invalid value {quote(currency)}")
        currency = ''

    return {
        'name': str(name),
        'number': format_account_number(str(number)),
        'balance': first_defined(raw_account.get('balance'), raw_account.get('Balance')),
        'available': first_defined(raw_account.get('availableBalance'), raw_account.get('AvailableBalance')),
        'currency': currency,
        'source': str(source) if source else 'external',
    }

def parse_offline_accounts(json_content):
    """Parse offline accounts from JSON."""
    try:
        data = json.loads(json_content)
    except:
        return []
    
    # Handle different JSON structures
    if isinstance(data, list):
        account_list = data
    elif isinstance(data, dict):
        account_list = first_defined(data.get('payload'), data.get('accounts'), data.get('Accounts'), [])
    else:
        return []
    
    if not isinstance(account_list, list):
        return []
    
    accounts = []
    for a in account_list:
        normalized = normalize_external_account(a)
        if normalized is not None:
            accounts.append(normalized)
    
    return accounts

def fetch_offline_accounts(login_info):
    """Fetch offline accounts."""
    url = f'{root_url}/api/AccountsAggregation/Accounts/accounts/Offline'
    headers = login_info['headers'].copy()
    headers.update(header_accept_json)
    
    try:
        # Try POST first
        request = urllib.request.Request(
            url,
            data=json.dumps({}).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        doc = download(request, ignore_errors=[404, 405])
        
        if doc['response'].status in [404, 405]:
            # Try GET
            request = urllib.request.Request(url, headers=headers)
            doc = download(request, ignore_errors=[404, 405])
            
            if doc['response'].status in [404, 405]:
                return []
        
        if 200 <= doc['response'].status < 300:
            return parse_offline_accounts(doc['content'])
    except:
        pass
    
    return []

def do_list(login=None, quiet=False):
    """List accounts."""
    if not login:
        user_error('Not logged in')
    
    # Request account list
    headers = login['headers'].copy()
    headers.update(header_accept_json)
    headers['Content-Type'] = 'application/json; charset=UTF-8'
    
    request = urllib.request.Request(
        f'{base_url}/MyDesktop/Desktop/GetAccountsList',
        data=json.dumps({}).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    
    doc = download(request)
    json_data = decode_json(doc['content'], context='list.json')
    accounts = check_type(json_data.get('accountDetailsList'), [], context='list.accounts')
    
    result = []
    for raw_account in accounts:
        account = normalize_mbank_account(raw_account)
        result.append({
            'name': account['name'],
            'number': account['number'],
            'source': account['source'],
        })
        
        if not quiet:
            balance = safe_format_money(account.get('balance'), account.get('currency'), context='list.balance')
            available = safe_format_money(account.get('available'), account.get('currency'), context='list.available')
            display_name = unicode_display(account['name'])
            print(f"{display_name};{account['number']};{balance};{available};{account['source']}")
    
    # Add offline accounts
    offline_accounts = fetch_offline_accounts(login)
    for a in offline_accounts:
        result.append({'name': a['name'], 'number': a['number'], 'source': a['source']})
        
        if not quiet:
            bal = safe_format_money(a.get('balance'), a.get('currency'), context='list.offline.balance')
            avl = safe_format_money(a.get('available'), a.get('currency'), context='list.offline.available')
            display_name = unicode_display(a['name'])
            display_source = unicode_display(a['source'])
            print(f"{display_name};{a['number']};{bal};{avl};{display_source}")
    
    return result

def do_lazy_logout(login=None):
    """Perform lazy logout API call."""
    if not login:
        internal_error('do_lazy_logout(): missing login')
    
    headers = login['headers'].copy()
    headers.update(header_accept_json)
    headers['Content-Type'] = 'application/json'
    
    request = urllib.request.Request(
        f'{base_url}/LoginMain/Account/LazyLogout',
        data=b'',
        headers=headers,
        method='POST'
    )
    
    doc = download(request)
    data = decode_json(doc['content'], context='logout.json')
    if not data.get('lazy'):
        scraping_error('logout.lazy')

def do_logout(maybe=False):
    """Log out current user session."""
    login_info = do_login(probe=True)
    if not login_info:
        clear_temp_cookies()
        if maybe:
            return
        user_error('logout: the user was not logged in')
    
    debug('logging out...')
    do_lazy_logout(login=login_info)
    
    request = urllib.request.Request(
        f'{base_url}/LoginMain/Account/Logout',
        headers={'Referer': login_info['url']},
        method='GET'
    )
    simple_download(request)
    debug('successful logout')
    
    clear_temp_cookies()

def _cookiejar_sanity_check_for_register_device():
    """Ensure cookie jar is writable and persistent."""
    if not ua or not hasattr(ua, 'cookie_jar'):
        user_error('missing cookie jar')
    
    cookie_jar = ua.cookie_jar
    cookie_jar_path = getattr(cookie_jar, 'filename', None) or '/dev/null'
    
    if cookie_jar_path == '/dev/null':
        user_error('/dev/null: unwritable cookie file')
    
    if not hasattr(cookie_jar, 'save'):
        user_error(f"{cookie_jar_path}: unwritable cookie file")
    
    uuid = gen_uuid()
    test_cookie = http.cookiejar.Cookie(
        version=0,
        name='UUID',
        value=uuid,
        port=None,
        port_specified=False,
        domain='mbank-cli.test',
        domain_specified=True,
        domain_initial_dot=False,
        path='/cookie-jar',
        path_specified=True,
        secure=False,
        expires=int(time.time()) + 60,
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )
    cookie_jar.set_cookie(test_cookie)
    
    try:
        cookie_jar.save(ignore_discard=True, ignore_expires=True)
    except OSError as e:
        os_error(f"{cookie_jar_path}: {e}")
    
    try:
        cookie_jar.clear(domain='mbank-cli.test', path='/cookie-jar', name='UUID')
    except KeyError:
        pass
    
    try:
        with open(cookie_jar_path, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
    except OSError as e:
        os_error(f"{cookie_jar_path}: {e}")
    
    if uuid not in content:
        user_error(f"{cookie_jar_path}: unwritable cookie file")

def cmd_register_device(**kwargs):
    """Register current device as trusted."""
    args = kwargs.get('args') or []
    if len(args) > 1:
        user_error('register-device: too many arguments')
    
    name = args[0] if args else 'CLI'
    _cookiejar_sanity_check_for_register_device()
    do_logout(maybe=True)
    do_login(register_device=name)

def cmd_logout(**kwargs):
    """Log out."""
    do_logout()

def cmd_configure(**kwargs):
    """Interactive configuration wizard."""
    config_path = kwargs.get('config_path')
    cookie_jar_path = kwargs.get('cookie_jar_path')
    
    # Check if config exists and ask to overwrite
    if config_path and os.path.exists(config_path):
        overwrite = ''
        while overwrite not in ['y', 'Y', 'n', 'N']:
            overwrite = input(f"{unexpand_tilde(config_path)} already exists. Overwrite (y/n)? ")
            if not overwrite:
                overwrite = ''
        if overwrite in ['n', 'N']:
            user_error('Configuration cancelled')
    
    # Get country
    guessed_cc = guess_country() or ''
    cc = ''
    while cc not in country_to_language:
        countries = ', or '.join([c.upper() for c in known_countries])
        cc = input(f"Country ({countries}): ") or guessed_cc.upper()
        cc = cc.lower()
    
    # Get login
    login = ''
    while not login:
        login = input('Login: ')
    
    # Get password
    password = ''
    while not password:
        password = term_readpasswd('Password: ')
    
    # Get cookie jar path
    sanitized_login = re.sub(r'\W', '_', login)
    xdg_data = xdg_data_home()
    cookie_home = f"{unexpand_tilde(xdg_data)}/mbank-cli"
    default_cookie_jar = cookie_jar_path or f"{cookie_home}/{sanitized_login}.cookies"
    
    cookie_jar_path = ''
    while len(cookie_jar_path) <= 1:
        cookie_jar_path = input(f'Session cookie store [{default_cookie_jar}]: ') or default_cookie_jar
    
    # Create cookie directory if needed
    cookie_dir = os.path.dirname(expand_tilde(cookie_jar_path))
    if cookie_dir and not os.path.exists(cookie_dir):
        makedirs(cookie_dir)
        print(f"Created directory for session cookie store: {unexpand_tilde(cookie_dir)}")
    
    # Create config directory
    config_dir = os.path.dirname(config_path)
    if config_dir:
        makedirs(config_dir)
    
    # Write config file
    config_new = f"{config_path}.new"
    try:
        with open(config_new, 'w') as fh:
            fh.write(_make_config_line('CookieJar', cookie_jar_path))
            fh.write(_make_config_line('Country', cc.upper()))
            fh.write(_make_config_line('Login', login))
            fh.write(_make_config_line('Password', password))
    except OSError as e:
        os_error(f"{config_new}: {e}")
    
    # Backup old config if it exists
    if os.path.exists(config_path):
        try:
            os.rename(config_path, f"{config_path}.bak")
            print(f"Backup copy: {unexpand_tilde(config_path)}.bak")
        except OSError:
            pass
    
    # Move new config into place
    try:
        os.rename(config_new, config_path)
        print(f"Created configuration file: {unexpand_tilde(config_path)}")
    except OSError as e:
        os_error(f"{config_path}: {e}")

def _make_config_line(key, value):
    """Format a configuration line."""
    if re.match(r'^[/\w.~-]+$', value):
        return f"{key} {value}\n"
    else:
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'{key} "{escaped}"\n'

def cmd_list(**kwargs):
    """List accounts."""
    login_info = kwargs.get('login')
    if not login_info:
        user_error('list: login required')
    do_list(login=login_info, quiet=False)

def cmd_activate_profile(**kwargs):
    """Activate personal/business profile."""
    login_info = kwargs.get('login')
    args = kwargs.get('args') or []
    
    if len(args) < 1:
        user_error('activate-profile: no profile selected')
    if len(args) > 1:
        user_error('activate-profile: too many arguments')
    
    name = args[0]
    profiles = login_info.get('profiles') or {}
    
    def sortkey(key):
        k = re.sub(r'^personal(?:/?|$)', '\x00', key)
        if k == 'business':
            k = '\x01'
        return k
    
    if name not in profiles:
        profile_names = ', or '.join(
            f'"{pname}"' for pname in sorted(profiles.keys(), key=sortkey)
        )
        profile_names = unicode_display(profile_names)
        user_error(f"activate-profile: invalid profile name (should be {profile_names})")
    
    codes = profiles[name]
    if len(codes) == 0:
        user_error(f"activate-profile: {name} profile not available")
    if len(codes) > 1:
        internal_error('activate-profile: ambiguous profile name')
    
    code = codes[0]
    if code == 'T':
        # Perl behavior: I (individual) is a superset of T (own products).
        code = 'I'
    
    debug(f'activating profile {code}...')
    
    headers = login_info['headers'].copy()
    headers['Accept'] = '*/*'
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    
    request = urllib.request.Request(
        f'{base_url}/LoginMain/Account/JsonActivateProfile',
        data=urllib.parse.urlencode({'profileCode': code}).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    download(request)
    
    # Response is not valid JSON despite content-type in Perl implementation.
    do_lazy_logout(login=login_info)

def main():
    """Main entry point."""
    command_name, args = parse_args()
    debug(f"selected command: {command_name}")
    
    commands = {
        'list': {'login': True},
        'logout': {'login': False},
        'register-device': {'login': False, 'args': True},
        'activate-profile': {'login': True, 'args': True},
        'configure': {'login': False, 'config': False},
    }
    
    command_info = commands.get(command_name)
    if command_info is None:
        user_error(f"{command_name}: invalid command")
    
    # Get command function
    command_func_name = command_name.replace('-', '_')
    command_func = globals().get(f'cmd_{command_func_name}')
    
    if not command_func:
        user_error(f"{command_name}: invalid command")
    
    need_login = command_info.get('login', True)
    cmd_options = {}

    if command_info.get('config', True):
        initialize()
    else:
        cmd_options['config_path'] = opt_config
        cmd_options['cookie_jar_path'] = opt_cookie_jar
    
    if command_info.get('args'):
        cmd_options['args'] = args
    
    if need_login:
        login_info = do_login()
        cmd_options['login'] = login_info
    command_func(**cmd_options)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(1)
    except SystemExit:
        # Re-raise SystemExit to preserve exit codes
        raise
    except Exception as e:
        # Catch any unexpected errors and display them clearly
        print(f"\nUnexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        if opt_verbose or opt_debug_dir:
            print("\nFull traceback:", file=sys.stderr)
            traceback.print_exc()
        else:
            print("Run with --verbose for full traceback", file=sys.stderr)
        sys.exit(255)
    finally:
        # Save cookies
        if ua and hasattr(ua, 'cookie_jar'):
            try:
                if hasattr(ua.cookie_jar, 'save'):
                    ua.cookie_jar.save(ignore_discard=True, ignore_expires=True)
            except:
                pass
