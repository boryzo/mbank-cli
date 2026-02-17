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
- opcjonalnie: ``CAfile``, ``PasswordManager``, ``DFP``

Użycie
------

Lista kont:

.. code-block:: bash

   python3 mbank-cli.py list

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

Testy (tylko unit)
------------------

Projekt używa wyłącznie testów jednostkowych (bez testów online/integracyjnych).

Uruchomienie:

.. code-block:: bash

   python3 -m unittest discover -s tests -p 'test_*.py' -v

Licencja
--------

MIT. Zobacz plik ``LICENSE``.
