mbank-cli (Python port)
=======================

Lekki, prosty port projektu `mbank-cli` do Pythona, utrzymywany pod kątem
czytelności kodu i łatwego onboardingu junior developerów.

To repozytorium jest portem oryginalnego projektu Jakuba Wilka:
https://github.com/jwilk/mbank-cli

Status
------

Aktualnie wspierane są kluczowe komendy:

- ``list``
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

Uruchomienie pełnego zestawu:

.. code-block:: bash

   python3 -m unittest discover -s tests -p 'test_*.py' -v

Licencja
--------

MIT. Zobacz plik ``LICENSE``.
