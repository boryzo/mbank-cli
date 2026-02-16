# Python Port of mbank-cli

This is a 1:1 port of the Perl-based mbank-cli to Python 3.9+.

## Status

### ✅ Working Commands

**configure** - Interactive configuration wizard
- Prompts for country, login, password
- Optional GPG encryption of password
- Creates configuration file
- Usage: `python3 mbank-cli.py configure`

### 📋 Partially Working Commands

**list** - List accounts (stub with helpful message)
- Shows status and instructions
- Does not require authentication (for now)
- Usage: `python3 mbank-cli.py list`

### ⏸️ Not Yet Implemented Commands

All other commands show helpful error messages directing users to the Perl version:
- `history`, `history2019` - Transaction history
- `future` - Future transactions  
- `blocked` - Blocked amounts
- `deposits` - Deposits
- `cards` - Cards
- `funds` - Investment funds
- `pension` - Pension accounts
- `notices` - Notices
- `logout` - Logout
- `register-device` - Device registration
- `activate-profile` - Profile activation

### Core Infrastructure (100% Complete)

- ✅ Error handling and logging
- ✅ HTTP/TLS client with SSL
- ✅ Cookie jar management
- ✅ Configuration file parsing (including GPG encryption)
- ✅ Data formatting (account numbers, money, dates)
- ✅ Date/time handling
- ✅ HTML/JSON parsing
- ✅ UUID functions
- ✅ CLI argument parsing
- ✅ Command dispatching
- ✅ Main program flow

## Quick Start

### Configure mbank-cli

```bash
python3 mbank-cli.py configure
```

This will:
1. Ask for your country (PL, CZ, or SK)
2. Ask for your mBank login
3. Ask for your password
4. Optionally encrypt the password with GPG
5. Set up a cookie jar location
6. Create the configuration file

### Using Commands

```bash
# Show help
python3 mbank-cli.py --help

# Show version
python3 mbank-cli.py --version

# List accounts (shows status message)
python3 mbank-cli.py list

# Other commands show helpful "not implemented" messages
python3 mbank-cli.py history
```

## Configuration File

Default location: `~/.config/mbank-cli/config`

Example configuration:
```
CookieJar ~/.local/share/mbank-cli/username.cookies
Country PL
Login username
Password your_password
```

Or with GPG-encrypted password:
```
CookieJar ~/.local/share/mbank-cli/username.cookies
Country PL
Login username
# Password (encrypted):
-----BEGIN PGP MESSAGE-----
...
-----END PGP MESSAGE-----
```

## Dependencies

Uses only Python 3.9+ built-in libraries:
- `sys`, `os`, `re`, `json`, `argparse`, `getpass`
- `http.cookiejar`, `urllib`
- `ssl`, `datetime`, `uuid`, `subprocess`

No external dependencies required!

## Implementation Status

| Component | Status | Lines | Notes |
|-----------|--------|-------|-------|
| Core infrastructure | ✅ Complete | ~1200 | Error handling, HTTP, config, formatting |
| CLI framework | ✅ Complete | ~200 | Argument parsing, help, version |
| `configure` command | ✅ Complete | ~150 | Full interactive configuration |
| `list` command | 🟡 Stub | ~20 | Shows helpful message |
| Other commands | ❌ Not started | ~2000 | Require web scraping and authentication |

**Total ported:** ~1570 lines / 3650 lines (~43%)

## What Works Now

✅ **Fixed Issues:**
- Command lookup bug (empty dict treated as invalid)
- Command dispatching (now properly calls command functions)
- Configure command fully working
- List command shows helpful status message
- All commands show appropriate errors

✅ **You Can Now:**
- Run `configure` to set up mbank-cli
- Run `list` to see implementation status
- Get proper error messages for all commands
- Use `--help` and `--version`

## What Doesn't Work Yet

❌ **Not Implemented:**
- Authentication (login, 2FA)
- Web scraping (account data, transactions)
- All banking commands (history, cards, etc.)

These require porting ~2000 lines of complex web scraping and mBank-specific API logic.

## For Users

**To use working features:**
```bash
python3 mbank-cli.py configure  # Setup configuration
python3 mbank-cli.py list       # See status
```

**To use banking features:**
```bash
./mbank-cli list                # Use original Perl version
./mbank-cli history ACCOUNT     # Use original Perl version
```

## License

Copyright © 2006-2025 Jakub Wilk <jwilk@jwilk.net>

SPDX-License-Identifier: MIT
