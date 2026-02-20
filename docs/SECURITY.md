# Security Guide (HTTP Wrapper)

To jest minimalny checklist dla danych krytycznych.

## 1) Dostęp sieciowy

- wystawiaj usługę za reverse proxy (Nginx/Caddy/Traefik),
- ogranicz ruch firewallem tylko do zaufanych adresów,
- ustaw `MBANK_WRAPPER_ALLOW_IPS`,
- użyj `MBANK_WRAPPER_DENY_IPS` dla znanych niepożądanych IP.

## 2) Klucz API

- ustaw długi losowy `MBANK_WRAPPER_API_KEY` (min. 32+ znaków),
- nie commituj klucza do repo,
- rotuj klucz cyklicznie (np. co 30-90 dni),
- trzymaj sekret w managerze sekretów lub w lokalnym env-file poza gitem.

## 3) Reverse proxy i IP klienta

- `MBANK_WRAPPER_TRUST_XFF=1` ustawiaj tylko za własnym reverse proxy,
- jeśli aplikacja jest wystawiona bez proxy, zostaw `MBANK_WRAPPER_TRUST_XFF=0`.

## 4) Ograniczanie nadużyć

- domyślny rate limit: 2 requesty / 10s / IP,
- nie wyłączaj limitu na publicznym interfejsie,
- dodatkowo możesz dołożyć limitowanie i WAF na reverse proxy.

## 5) Stabilność procesu

- wrapper przepuszcza tylko 1 komendę naraz (lock),
- ustaw `MBANK_WRAPPER_TIMEOUT` zgodnie z realnym SLA,
- monitoruj `429`, `502`, `504` (to sygnały problemów operacyjnych).

## 6) Logowanie i debug

- debug (`--debug`) zapisuje request/response; to mogą być dane wrażliwe,
- nie trzymaj debug logów długoterminowo,
- ogranicz uprawnienia do logów i katalogu roboczego.

## 7) Uprawnienia systemowe

- uruchamiaj usługę na dedykowanym użytkowniku systemowym,
- pliki konfiguracyjne i cookie jar ustaw na prawa `600`,
- nie uruchamiaj jako `root`.

## 8) Transport (TLS)

- jeśli ruch wychodzi poza localhost, użyj HTTPS,
- terminuj TLS na reverse proxy,
- wymuś nowoczesne szyfry i HSTS na warstwie proxy.
