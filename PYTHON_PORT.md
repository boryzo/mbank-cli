# Python Port of mbank-cli

This is a 1:1 port of the Perl-based mbank-cli to Python 3.9+.

## Status

### Completed ✅

**Core Infrastructure (100%)**
- Error handling and logging (write_log, debug, warning, user_error, server_error, etc.)
- Utility functions (normalize_whitespace, quote, match, check_type, unpack_list, etc.)
- Internationalization support (encoding fallback, locale handling, country/language mappings)

**HTTP & TLS (100%)**
- HTTP client initialization with SSL/TLS
- Download functions (download, simple_download)
- Cookie jar handling
- Certificate authority path resolution

**Configuration (100%)**
- Configuration file reading and parsing
- GPG-encrypted configuration support (requires subprocess)
- Configuration variable access

**Data Formatting (100%)**
- Account number formatting
- Amount and money formatting
- Number formatting
- Wildcard to regex conversion

**Date & Time (100%)**
- Timestamp parsing and conversion
- Date matching and validation
- Date shifting
- HTTP date parsing
- Local date/time handling
- JavaScript-compatible timestamp generation

**HTML & JSON (100%)**
- Simple HTML parsing (SimpleHTMLParser)
- HTML element finding and class matching
- JSON encoding/decoding with type checking

**UUIDs & Terminal (100%)**
- UUID parsing and generation
- Terminal/readline interface
- Password reading

**CLI & Main (100%)**
- Command-line argument parsing (argparse)
- Help and version display
- Configuration initialization
- Main program flow

### Not Yet Implemented ⏸️

The following commands require extensive web scraping and banking API interaction logic that was not yet ported:

- `do_login()` - Authentication and 2FA
- `do_list()` - List accounts
- `cmd::history()` - Transaction history
- `cmd::history2019()` - Transaction history (2019+ API)
- `cmd::future()` - Future transactions
- `cmd::blocked()` - Blocked amounts
- `cmd::deposits()` - Deposits
- `cmd::cards()` - Cards
- `cmd::funds()` - Funds
- `cmd::pension()` - Pension
- `cmd::notices()` - Notices
- `cmd::logout()` - Logout
- `cmd::register_device()` - Register device
- `cmd::activate_profile()` - Activate profile
- `cmd::configure()` - Interactive configuration

These functions would require porting approximately 1600+ lines of complex web scraping logic, form handling, and banking-specific business logic.

## Dependencies

The Python port uses only built-in Python 3.9+ libraries:

- `sys`, `os`, `re` - Core Python
- `json` - JSON handling
- `traceback` - Error tracking
- `argparse` - CLI argument parsing
- `getpass` - Password input
- `http.cookiejar` - Cookie management
- `urllib.parse`, `urllib.request`, `urllib.error` - HTTP client
- `ssl` - TLS/SSL support
- `time` - Time functions
- `locale`, `codecs` - Locale and encoding
- `datetime`, `timezone`, `timedelta` - Date/time handling
- `pathlib`, `Path` - File path handling
- `html.parser.HTMLParser` - HTML parsing
- `xml.etree.ElementTree` - XML/HTML tree (optional)
- `uuid` - UUID generation
- `subprocess` - For GPG decryption (optional)
- `zoneinfo` - Timezone support (Python 3.9+, optional fallback)

No external dependencies like `requests`, `beautifulsoup4`, or other third-party packages are required.

## Usage

```bash
# Show help
./mbank-cli.py --help

# Show version
./mbank-cli.py --version

# List accounts (not yet implemented)
./mbank-cli.py list
```

## File Structure

- `mbank-cli.py` - Main Python implementation (~1400 lines)
- `mbank-cli` - Original Perl implementation (~3650 lines)

## Implementation Notes

### 1:1 Port Philosophy

This port follows the Perl code structure as closely as possible:

1. **Function names**: Kept identical (e.g., `write_log`, `format_account_number`)
2. **Logic flow**: Preserved the same control flow and error handling
3. **Return values**: Matched Perl's return conventions where possible
4. **Exit codes**: Same exit codes (1=user error, 2=server error, 3=scraping error, 4=OS error)

### Key Differences

1. **Regular expressions**: Python's `re` module vs Perl's built-in regex
2. **HTTP library**: `urllib` vs Perl's `LWP::UserAgent`
3. **HTML parsing**: Simple custom parser vs `HTML::TreeBuilder`
4. **Cookie handling**: `http.cookiejar` vs `HTTP::Cookies`
5. **SSL/TLS**: `ssl` module vs `IO::Socket::SSL`

### Notable Challenges

1. **HTML Parsing**: Perl's `HTML::TreeBuilder` is more feature-rich than Python's built-in parser. A basic implementation is provided but may need enhancement for complex scraping tasks.

2. **Timezone Handling**: Perl's `Time::Piece` with local timezone support was replaced with Python's `datetime` and `zoneinfo`.

3. **Keyword Arguments**: Perl's `kwargs()` function for validating keyword arguments was re-implemented in Python with similar behavior.

4. **Unicode Fallback**: Perl's encoding fallback mechanism was replicated using custom error handlers.

## Testing

Basic CLI functionality works:

```bash
$ python3 mbank-cli.py --version
mbank-cli 20250101
+ Python 3.12.3
+ urllib.request (built-in)
+ http.cookiejar (built-in)

$ python3 mbank-cli.py --help
Usage: mbank-cli [OPTIONS] COMMAND [ARGS...]
...
```

## Next Steps

To complete the port, the following would need to be implemented:

1. Port the login and authentication logic (~400 lines)
2. Port HTML scraping and form handling (~300 lines)
3. Port each command implementation (~1000 lines)
4. Add comprehensive tests
5. Validate against live mBank API (if available)

## License

Copyright © 2006-2025 Jakub Wilk <jwilk@jwilk.net>

SPDX-License-Identifier: MIT

---

## Original Perl Version

The original Perl implementation is in the file `mbank-cli` and remains the authoritative, production-ready version.
