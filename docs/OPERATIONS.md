# Operations: service autostart i cron

Poniżej są praktyczne przykłady dla wrappera HTTP i cyklicznego eksportu danych.

## 1) macOS: `launchd` (autostart wrappera)

Przykładowy plik:

`~/Library/LaunchAgents/pl.mbank.http.wrapper.plist`

Uwaga: zamień `/path/to/mbank-cli` na swoją lokalną ścieżkę repo.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>pl.mbank.http.wrapper</string>

    <key>ProgramArguments</key>
    <array>
      <string>/usr/bin/env</string>
      <string>bash</string>
      <string>-lc</string>
      <string>cd /path/to/mbank-cli && set -a && source mbank_http_service.config && set +a && python3 mbank_http_wrapper.py</string>
    </array>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/mbank_http_wrapper.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/mbank_http_wrapper.err.log</string>
  </dict>
</plist>
```

Załadowanie:

```bash
launchctl unload ~/Library/LaunchAgents/pl.mbank.http.wrapper.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/pl.mbank.http.wrapper.plist
launchctl start pl.mbank.http.wrapper
```

## 2) Linux: `systemd` (autostart wrappera)

Przykładowy unit:

`/etc/systemd/system/mbank-http-wrapper.service`

```ini
[Unit]
Description=mBank HTTP Wrapper
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/mbank-cli
EnvironmentFile=/path/to/mbank-cli/mbank_http_service.config
ExecStart=/usr/bin/python3 /path/to/mbank-cli/mbank_http_wrapper.py
Restart=always
RestartSec=2
User=YOUR_USER

[Install]
WantedBy=multi-user.target
```

Aktywacja:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mbank-http-wrapper.service
sudo systemctl status mbank-http-wrapper.service
```

## 3) Cron: cykliczny export `list` i `history`

Edytuj crontab:

```bash
crontab -e
```

Przykładowe wpisy (Europe/Warsaw, godzina 10:15 CET/CEST):

```cron
CRON_TZ=Europe/Warsaw
15 10 * * * cd /path/to/mbank-cli && python3 mbank-cli.py list >> balances_snapshot.txt 2>> balances_snapshot.err.log
```

Historia raz w tygodniu (poniedziałek 10:20):

```cron
CRON_TZ=Europe/Warsaw
20 10 * * 1 cd /path/to/mbank-cli && python3 mbank-cli.py history --all >> history_weekly.txt 2>> history_weekly.err.log
```

## 4) Rekomendacje operacyjne

- trzymaj `mbank_http_service.config` poza gitem (plik jest w `.gitignore`),
- ustaw prawa do configu: `chmod 600 mbank_http_service.config`,
- logi rotuj i czyść okresowo,
- na produkcji wystawiaj wrapper za reverse proxy + TLS.
