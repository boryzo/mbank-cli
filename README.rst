mbank-cli (Python port)
=======================

Lekki, prosty port projektu `mbank-cli` do Pythona, utrzymywany pod kątem
czytelności kodu i łatwego onboardingu junior developerów.

To repozytorium jest portem oryginalnego projektu Jakuba Wilka:
https://github.com/jwilk/mbank-cli

Dokumentacja
------------

Pełna dokumentacja HTTP wrappera i bezpieczeństwa jest w repo:

- ``docs/HTTP_API.md`` - endpointy, auth, statusy, przykłady ``curl``.
- ``docs/SECURITY.md`` - hardening checklist i zalecenia produkcyjne.
- ``docs/OPERATIONS.md`` - uruchamianie jako service (autostart) i cron.
- ``mbank_http_service.config.example`` - przykładowy plik konfiguracyjny
  dla wrappera (env-file).

Status
------

Aktualnie wspierane są kluczowe komendy:

- ``list``
- ``history``
- ``logout``
- ``register-device``
- ``activate-profile``
- ``configure``

Reszta historycznych komend została celowo usunięta.

Wymagania
---------

- Python 3.9+

Instalacja lokalna
------------------

Uruchamianie bez instalacji pakietu:

.. code-block:: bash

   python3 mbank-cli.py --help

Konfiguracja
------------

Interaktywnie:

.. code-block:: bash

   python3 mbank-cli.py configure

Domyślna lokalizacja konfiguracji:

- ``~/.config/mbank-cli/config``

Przykładowe pola konfiguracji:

- ``CookieJar``
- ``Country`` (``PL`` / ``CZ`` / ``SK``)
- ``Login``
- ``Password``
- opcjonalnie: ``CAfile``, ``PasswordManager``, ``DFP``,
  ``BrowserUserAgent``, ``BrowserName``, ``BrowserVersion``

Override przez zmienne środowiskowe (najwyższy priorytet):

- ``MBANK_CLI_USER_AGENT``
- ``MBANK_CLI_BROWSER_NAME``
- ``MBANK_CLI_BROWSER_VERSION``
- ``MBANK_CLI_DFP``

Użycie
------

Lista kont:

.. code-block:: bash

   python3 mbank-cli.py list

Historia operacji:

.. code-block:: bash

   python3 mbank-cli.py history
   python3 mbank-cli.py history --from 2026-01-01 --to 2026-01-31
   python3 mbank-cli.py history --all

``history --all`` dodaje historię kont zewnętrznych (Accounts Aggregation)
z filtrem statusu transakcji ``DONE``.

Format wiersza ``history`` (ID transakcji jest zawsze):

.. code-block:: text

   Data;NumerKonta;TransactionId;Typ;Kwota;Saldo;Opis;Komentarz

Format wiersza ``list``:

.. code-block:: text

   2026-02-17T21:37:12+01:00;Nazwa konta;NumerKonta;Saldo;Dostepne;Zrodlo

Wylogowanie:

.. code-block:: bash

   python3 mbank-cli.py logout

Rejestracja urządzenia:

.. code-block:: bash

   python3 mbank-cli.py register-device
   python3 mbank-cli.py register-device "Moj Laptop"

Aktywacja profilu:

.. code-block:: bash

   python3 mbank-cli.py activate-profile personal

Wrapper HTTP (Flask)
--------------------

Prosty wrapper HTTP uruchamiający dokładnie te same komendy CLI:

- ``GET/POST /accounts`` -> ``python3 mbank-cli.py list``
- ``GET/POST /history`` -> ``python3 mbank-cli.py history --all``

Uruchomienie lokalne:

.. code-block:: bash

   pip install flask
   export MBANK_WRAPPER_API_KEY='zmien-to-na-dlugi-losowy-klucz'
   export MBANK_WRAPPER_ALLOW_IPS='127.0.0.1/32'
   python3 mbank_http_wrapper.py

Autoryzacja API key (jedna z metod):

- nagłówek ``X-API-Key: ...``
- query param ``?api_key=...``
- POST body ``api_key=...`` (form lub JSON)

Ważne zmienne środowiskowe wrappera:

- ``MBANK_WRAPPER_API_KEY`` (wymagane)
- ``MBANK_WRAPPER_ALLOW_IPS`` (lista CIDR/IP rozdzielona przecinkami)
- ``MBANK_WRAPPER_DENY_IPS`` (blacklista CIDR/IP)
- ``MBANK_WRAPPER_TRUST_XFF=1`` (ufanie ``X-Forwarded-For`` za reverse proxy)
- ``MBANK_WRAPPER_TIMEOUT`` (timeout subprocess, sekundy)
- ``MBANK_WRAPPER_RATE_LIMIT_COUNT`` (domyślnie ``2``)
- ``MBANK_WRAPPER_RATE_LIMIT_WINDOW_SEC`` (domyślnie ``10``)
- ``MBANK_WRAPPER_HOST`` / ``MBANK_WRAPPER_PORT``

Zachowanie bezpieczeństwa:

- bez poprawnego API key: ``401``,
- niedozwolony IP: ``403``,
- rate limit per IP (domyślnie max 2 requesty/10s): ``429``,
- równoległe uruchomienie komendy: ``429``,
- timeout backendu CLI: ``504``,
- błąd CLI: ``502`` + body ze stderr (lub stdout fallback),
- sukces: ``200`` + czysty output CLI ``text/plain``.

Service i cron
--------------

Masz gotowe przykłady uruchamiania z autostartem systemu (``launchd``/``systemd``)
oraz harmonogramu ``cron`` w:

- ``docs/OPERATIONS.md``

Debug
-----

- ``--verbose``: logi operacyjne na stderr.
- ``--debug DIR``: pełny dump HTTP (request/response/headers/body) do pliku
  ``DIR/log``.

Testy
-----

Projekt ma testy offline, bez logowania do prawdziwego mBanku:

- unit: funkcje pomocnicze i logika parsowania/normalizacji,
- contract: fixture JSON/HTML z formatami odpowiedzi,
- integration (offline): lokalny fake server HTTP i pełny przepływ wybranych
  komend,
- CLI black-box: testy ``subprocess`` na realnym wywołaniu skryptu.
- wrapper HTTP (unit + mocki): auth API key, blokowanie IP (allow/deny/XFF),
  stałe mapowanie endpoint->komenda, timeouty, lock współbieżności, kody HTTP.

Uruchomienie pełnego zestawu:

.. code-block:: bash

   python3 -m unittest discover -s tests -p 'test_*.py' -v

Uruchomienie tylko testów wrappera:

.. code-block:: bash

   python3 -m unittest tests/test_http_wrapper.py -v

Licencja
--------

MIT. Zobacz plik ``LICENSE``.
