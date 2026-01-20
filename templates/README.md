# Tamesuke Templates

LXCテンプレート（8010, 8011等）に配置するスクリプト群。

## ファイル一覧

| ファイル | 配置先 | 説明 |
|---------|--------|------|
| tamesuke-init.sh | /opt/tamesuke/bin/ | 起動時にメタデータをダウンロード |
| tamesuke-configure.sh | /opt/tamesuke/bin/ | Cloudflare Tunnelの設定・起動 |

## 配置手順

テンプレートLXC（例: 8011）に入って配置：

```bash
pct enter 8011

mkdir -p /opt/tamesuke/bin
# ファイルをコピー
chmod +x /opt/tamesuke/bin/tamesuke-init.sh
chmod +x /opt/tamesuke/bin/tamesuke-configure.sh
```

## systemd service

`tamesuke-init.sh` は systemd service から呼び出される：

```bash
# /etc/systemd/system/tamesuke-init.service
[Unit]
Description=Tamesuke Initialization Service
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/tamesuke/bin/tamesuke-init.sh
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## 変更履歴

- 2026-01-20: `--protocol http2` 対応（QUIC失敗時のフォールバック問題解決）
- 2026-01-06: hostname ベースのメタデータ取得に変更（cgroup v2対応）
