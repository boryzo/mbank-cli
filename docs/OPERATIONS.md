# Operations: service autostart

Poniżej są praktyczne przykłady dla wrappera HTTP i cyklicznego eksportu danych.

## 1) macOS: `launchd` (autostart wrappera)

Przykładowy plik:

`~/Library/LaunchAgents/pl.mbank.http.wrapper.plist`

Uwaga: zamień `/srv/mbank-cli` na swoją lokalną ścieżkę repo.

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
      <string>cd /srv/mbank-cli && set -a && source ~/.config/mbank-cli/http-wrapper.env && set +a && python3 mbank_http_wrapper.py</string>
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
Wants=network-online.target
After=network-online.target local-fs.target

[Service]
Type=simple
WorkingDirectory=/srv/mbank-cli
EnvironmentFile=/etc/mbank-cli/http-wrapper.env
ExecStartPre=/bin/sleep 60
ExecStart=/usr/bin/python3 /srv/mbank-cli/mbank_http_wrapper.py
Restart=always
RestartSec=2
User=root

[Install]
WantedBy=multi-user.target
```

`ExecStartPre=/bin/sleep 60` daje czas na montowanie dysków i sieci po restarcie.

Aktywacja:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mbank-http-wrapper.service
sudo systemctl status mbank-http-wrapper.service
```

## 3) Rekomendacje operacyjne

- trzymaj config poza gitem, np. `~/.config/mbank-cli/http-wrapper.env` albo `/etc/mbank-cli/http-wrapper.env`,
- ustaw prawa do configu: `chmod 600 ~/.config/mbank-cli/http-wrapper.env` (lub `/etc/mbank-cli/http-wrapper.env`),
- logi rotuj i czyść okresowo,
- na produkcji wystawiaj wrapper za reverse proxy + TLS.
