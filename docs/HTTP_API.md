# mbank HTTP Wrapper API

Ten wrapper wystawia tylko 2 endpointy i uruchamia stałe komendy:

- `GET/POST /accounts` -> `python3 mbank-cli.py list`
- `GET/POST /history` -> `python3 mbank-cli.py history --all`

Nie ma parametryzacji komend przez HTTP.

## Start

```bash
pip install flask
cp mbank_http_service.config.example mbank_http_service.config
# uzupełnij MBANK_WRAPPER_API_KEY
set -a
source mbank_http_service.config
set +a
python3 mbank_http_wrapper.py
```

Domyślny bind:

- host: `127.0.0.1`
- port: `8787`

## Autoryzacja

Wymagany jest `MBANK_WRAPPER_API_KEY`.

API key można przekazać jedną z metod:

- header: `X-API-Key`
- query: `?api_key=...`
- body POST: `api_key=...` (form lub JSON)

## Przykłady wywołań

```bash
curl -sS "http://127.0.0.1:8787/accounts?api_key=$MBANK_WRAPPER_API_KEY"
```

```bash
curl -sS -H "X-API-Key: $MBANK_WRAPPER_API_KEY" \
  "http://127.0.0.1:8787/history"
```

```bash
curl -sS -X POST -H "Content-Type: application/json" \
  -d "{\"api_key\":\"$MBANK_WRAPPER_API_KEY\"}" \
  "http://127.0.0.1:8787/accounts"
```

## Format odpowiedzi

- sukces: `200`, `Content-Type: text/plain`, body = dokładny output CLI
- błąd CLI: `502`, body = stderr CLI (lub stdout fallback)
- nagłówek `X-Exit-Code`:
  - `0` na sukcesie
  - kod wyjścia CLI dla `502`

## Kody HTTP

- `200`: komenda zakończona sukcesem
- `401`: brak/niepoprawny API key
- `403`: niedozwolony IP
- `429`: przekroczony rate limit lub równoległe uruchomienie
- `500`: brak `MBANK_WRAPPER_API_KEY` po stronie serwera
- `502`: błąd wywołania `mbank-cli.py`
- `504`: timeout komendy backendowej

## Konfiguracja (env)

- `MBANK_WRAPPER_API_KEY` - wymagane
- `MBANK_WRAPPER_ALLOW_IPS` - whitelist CIDR/IP, np. `127.0.0.1/32,10.0.0.0/8`
- `MBANK_WRAPPER_DENY_IPS` - blacklist CIDR/IP
- `MBANK_WRAPPER_TRUST_XFF` - `1` aby używać `X-Forwarded-For`
- `MBANK_WRAPPER_TIMEOUT` - timeout subprocess w sekundach
- `MBANK_WRAPPER_RATE_LIMIT_COUNT` - liczba requestów w oknie, domyślnie `2`
- `MBANK_WRAPPER_RATE_LIMIT_WINDOW_SEC` - okno w sekundach, domyślnie `10`
- `MBANK_WRAPPER_HOST` - host bind, domyślnie `127.0.0.1`
- `MBANK_WRAPPER_PORT` - port bind, domyślnie `8787`
- `MBANK_WRAPPER_SCRIPT` - ścieżka do `mbank-cli.py`
- `MBANK_WRAPPER_PYTHON` - interpreter python do uruchamiania CLI
- `MBANK_WRAPPER_CWD` - katalog roboczy subprocessu
