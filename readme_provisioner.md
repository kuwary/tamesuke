# Tamesuke Provisioner

自動プロビジョニングシステム - Cloudflare Tunnel + Proxmox LXC + hostname版メタデータ配信

**バージョン:** 1.0.0  
**作成日:** 2026-01-07  
**最終更新:** 2026-01-08

---

## 概要

TamesukeプロビジョニングシステムのコアPythonスクリプト。

**機能:**
- Cloudflare Tunnel自動作成
- DNS CNAME自動登録
- LXC自動クローン（テンプレートベース）
- hostname版メタデータ配信（File Server経由）
- systemd service連携による初期化
- HTTPS公開（https://{subdomain}.persys.jp）

**実績:**
- ✅ demo.persys.jp で動作確認済み
- ✅ 複数インスタンス同時稼働対応（demo, demo2, demo3）

---

## システム構成

```
Proxmox Host (odin)
├─ dhcpserver (8001)     DHCP + DNS (dnsmasq)
├─ testserver (8002)     プロビジョニング実行環境 ← ここで実行
├─ fileserver (8003)     メタデータ配信
├─ cloudflare-tunnel-base (8010)  テンプレート（廃止）
├─ nginxtemplate (8011)  テンプレート（現行）
└─ 動的LXC (9000-9999)   プロビジョニング結果

Cloudflare
├─ Tunnel (動的作成)
├─ DNS (CNAME自動登録)
└─ Zero Trust Dashboard
```

---

## 前提条件

### 必須インフラ

1. **Proxmox VE**
   - ホスト: odin (192.168.11.5)
   - SDN: EVPN (Zone: tamevnet, VNet: customer)
   - テンプレート: nginxtemplate (VMID 8011)

2. **Cloudflare**
   - アカウントID
   - API Token（Tunnel作成権限）
   - Zone ID（persys.jp）

3. **File Server (LXC 8003)**
   - HTTP Server稼働: `http://fileserver:8080`
   - メタデータ配信: `/metadata/metadata-{subdomain}.json`

4. **DHCP Server (LXC 8001)**
   - dnsmasq稼働
   - IP範囲: 10.2.1.100-10.2.1.200
   - ゲートウェイ: 10.2.1.1
   - DNSサーバー: 10.2.1.2

### 必須Pythonパッケージ

```
proxmoxer>=2.0.1
requests>=2.31.0
python-dotenv>=1.0.0
```

インストール:
```bash
pip3 install -r requirements.txt
```

---

## 環境変数設定

`.env` ファイルを作成（testserver上）:

```bash
# Proxmox設定
PROXMOX_HOST=192.168.11.5
PROXMOX_USER=root@pam
PROXMOX_PASSWORD=your_password
PROXMOX_NODE=odin

# Cloudflare設定
CLOUDFLARE_API_TOKEN=your_api_token
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_ZONE_ID=your_zone_id

# File Server設定
FILESERVER_HOST=fileserver
FILESERVER_PORT=8080

# ドメイン設定
DOMAIN=persys.jp
```

**セキュリティ:**
- `.env` ファイルは `.gitignore` に追加
- 本番環境では環境変数またはシークレット管理ツールを使用

---

## 使い方

### 基本的な実行

```bash
# testserver (8002) で実行
cd /root
python3 provisioner.py <subdomain> <oss_type> <duration_days>
```

**例:**
```bash
# demo という名前で nginx を 7日間プロビジョニング
python3 provisioner.py demo nginx 7

# demo2 という名前で nginx を 14日間
python3 provisioner.py demo2 nginx 14
```

### スクリプト内で実行（推奨）

```python
from provisioner import TamesukeProvisioner
from dotenv import load_dotenv
import os

# 環境変数読み込み
load_dotenv()

# プロビジョニング実行
provisioner = TamesukeProvisioner(
    proxmox_host=os.getenv('PROXMOX_HOST'),
    proxmox_user=os.getenv('PROXMOX_USER'),
    proxmox_password=os.getenv('PROXMOX_PASSWORD'),
    cloudflare_token=os.getenv('CLOUDFLARE_API_TOKEN'),
    cloudflare_account_id=os.getenv('CLOUDFLARE_ACCOUNT_ID'),
    cloudflare_zone_id=os.getenv('CLOUDFLARE_ZONE_ID'),
    fileserver_host=os.getenv('FILESERVER_HOST'),
    fileserver_port=int(os.getenv('FILESERVER_PORT', 8080)),
    domain=os.getenv('DOMAIN', 'persys.jp'),
    proxmox_node=os.getenv('PROXMOX_NODE', 'odin')
)

result = provisioner.provision(
    customer_email='test@example.com',
    oss_type='nginx',
    subdomain='demo',
    duration_days=7
)

print(f"結果: {result}")
```

---

## プロビジョニングフロー

### Step 1-5: Cloudflare設定

1. **VMID割り当て** (9000-9999の未使用番号)
2. **Cloudflare Tunnel作成**
3. **Tunnel Token取得**
4. **Tunnelルーティング設定** (`https://{subdomain}.persys.jp` → `http://localhost:80`)
5. **DNS CNAME登録** (`{subdomain}.persys.jp` → `{tunnel_id}.cfargotunnel.com`)

### Step 6-7: メタデータ準備

6. **メタデータJSON作成**
   ```json
   {
     "tunnel_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
     "tunnel_token": "eyJh...",
     "subdomain": "demo",
     "domain": "persys.jp",
     "oss_type": "nginx",
     "customer_email": "test@example.com",
     "duration_days": 7,
     "created_at": "2026-01-07T12:00:00Z"
   }
   ```

7. **File Serverへアップロード**
   - URL: `http://fileserver:8080/upload`
   - ファイル名: `metadata-{subdomain}.json`

### Step 8-9: LXC作成

8. **LXCクローン作成**
   - ソース: nginxtemplate (8011)
   - ターゲット: 新規VMID
   - オプション: `--full`（完全クローン）
   - hostname設定: `{subdomain}`

9. **LXC起動**

### Step 10: 初期化待機

10. **サービス起動待機**
    - URL: `https://{subdomain}.persys.jp`
    - タイムアウト: 300秒（5分）
    - チェック間隔: 10秒

---

## LXC内の自動初期化

LXC起動後、以下の処理が自動実行されます（`tamesuke-init.service`）:

### 初期化スクリプト (`/opt/tamesuke/bin/tamesuke-init.sh`)

```bash
#!/bin/bash
set -e

# 1. hostnameからメタデータURL生成
HOSTNAME=$(hostname)
METADATA_URL="http://fileserver:8080/metadata/metadata-${HOSTNAME}.json"

# 2. メタデータダウンロード
curl -o /opt/tamesuke/etc/metadata.json $METADATA_URL

# 3. 設定スクリプト実行
/opt/tamesuke/bin/tamesuke-configure.sh

# 4. cloudflared起動
systemctl start cloudflared
```

### 設定スクリプト (`/opt/tamesuke/bin/tamesuke-configure.sh`)

```bash
#!/bin/bash
set -e

# メタデータ読み込み
TUNNEL_TOKEN=$(jq -r '.tunnel_token' /opt/tamesuke/etc/metadata.json)

# cloudflared設定
mkdir -p /root/.cloudflared
cat > /root/.cloudflared/config.yml << EOF
tunnel: $(jq -r '.tunnel_id' /opt/tamesuke/etc/metadata.json)
credentials-file: /root/.cloudflared/tunnel.json

ingress:
  - hostname: $(jq -r '.subdomain' /opt/tamesuke/etc/metadata.json).$(jq -r '.domain' /opt/tamesuke/etc/metadata.json)
    service: http://localhost:80
  - service: http_status:404
EOF

# Tunnel credentials
echo $TUNNEL_TOKEN | base64 -d > /root/.cloudflared/tunnel.json
```

---

## 出力例

### 成功時

```
============================================================
プロビジョニング開始
============================================================
顧客: test@example.com
OSS: nginx
サブドメイン: demo
ドメイン: persys.jp
期間: 7日
============================================================

[OK] Proxmox connected: 9.1.2
[OK] Cloudflare connected
1. [OK] VMID割り当て: 9000
2. [OK] Tunnel作成: 88b57df7-554c-4550-b8b2-89e891cb962d
3. [OK] Tunnel Token取得
4. [OK] Tunnelルーティング設定
   - 既存DNSレコード削除: e91bc94c34466fcdf26492b5523232d6
5. [OK] DNS登録: demo.persys.jp
6. [OK] メタデータJSON作成
7. [OK] File Serverへアップロード
   - Clone completed (waited 6s)
8. [OK] LXCクローン作成
9. [OK] LXC起動
10. [WAIT] 初期化完了待機中... (最大5分)
   120秒経過...
10. [OK] サービス起動完了

結果: {
  "vmid": 9000,
  "subdomain": "demo",
  "url": "https://demo.persys.jp",
  "tunnel_id": "88b57df7-554c-4550-b8b2-89e891cb962d",
  "customer_email": "test@example.com",
  "oss_type": "nginx",
  "duration_days": 7
}
```

### エラー時

```
[ERROR] エラーが発生しました: タイムアウト: 300秒以内にサービスが起動しませんでした
Traceback (most recent call last):
  ...
Exception: タイムアウト: 300秒以内にサービスが起動しませんでした
```

---

## トラブルシューティング

### タイムアウトエラー

**症状:**
```
[ERROR] タイムアウト: 300秒以内にサービスが起動しませんでした
```

**確認手順:**

```bash
# 1. LXCが起動しているか
pct list | grep 9000

# 2. cloudflaredサービスの状態
pct exec 9000 -- systemctl status cloudflared

# 3. ログ確認
pct exec 9000 -- journalctl -u cloudflared -n 50
pct exec 9000 -- journalctl -u tamesuke-init.service -n 50

# 4. ネットワーク確認
pct exec 9000 -- ip a
pct exec 9000 -- ip route
pct exec 9000 -- ping -c 3 10.2.1.1   # ゲートウェイ
pct exec 9000 -- ping -c 3 1.1.1.1    # インターネット

# 5. メタデータ確認
pct exec 9000 -- cat /opt/tamesuke/etc/metadata.json
```

**よくある原因:**

1. **DHCP でゲートウェイが取得できていない**
   - 対処: `/etc/network/interfaces` を確認、`dhclient` 実行

2. **cloudflared が Cloudflare に接続できない**
   - 対処: ネットワーク疎通確認、`systemctl restart cloudflared`

3. **メタデータダウンロード失敗**
   - 対処: File Serverが起動しているか確認

### Cloudflare Tunnel接続エラー

```
ERR Failed to dial a quic connection
ERR failed to accept incoming stream requests
```

**原因:** VRF間のネットワーク問題、またはCloudflare側の一時的な問題

**対処:**
```bash
# cloudflared再起動
pct exec 9000 -- systemctl restart cloudflared

# ログ監視
pct exec 9000 -- journalctl -u cloudflared -f
```

---

## 制限事項

### タイムアウト

- **初期化待機: 300秒（5分）**
  - DHCP IP取得 + cloudflared接続確立に時間がかかる場合、タイムアウトする可能性あり
  - 対処: `provisioner-verbose.py`（600秒版）を使用

### VMID範囲

- **9000-9999 の範囲のみ**
  - 1000個まで同時稼働可能
  - VMIDが枯渇した場合はエラー

### ネットワーク

- **VRF間TCP通信の制限**
  - Proxmox SDN (EVPN) の制限により、VRF間のTCP通信が不安定な場合あり
  - 対処: 外部NIC経由のルーティング追加

---

## ファイル構成

```
/root/
├── provisioner.py          メインスクリプト
├── requirements.txt        依存パッケージ
└── .env                    環境変数（Gitに含めない）

/opt/tamesuke/              LXC内（テンプレート）
├── bin/
│   ├── tamesuke-init.sh           初期化スクリプト
│   └── tamesuke-configure.sh      設定スクリプト
└── etc/
    └── metadata.json              メタデータ（起動時にダウンロード）

/etc/systemd/system/        LXC内（テンプレート）
└── tamesuke-init.service          初期化サービス
```

---

## TODO（未実装機能）

- [ ] 自動削除機能（期限切れ時）
- [ ] Stripe Webhook連携
- [ ] メール送信（ウェルカムメール、期限切れ通知）
- [ ] 複数OSSテンプレート対応（Growi, WordPress等）
- [ ] 管理ダッシュボード
- [ ] ログ記録・監視

---

## 関連ドキュメント

- [TEMPLATE_CREATION_GUIDE.md](./TEMPLATE_CREATION_GUIDE.md) - テンプレート作成手順
- [tamesuke-infrastructure-summary.md](./tamesuke-infrastructure-summary.md) - インフラ全体構成
- [tamesuke-service-flow.md](./tamesuke-service-flow.md) - サービスフロー全体像

---

## ライセンス

MIT License

---

## 変更履歴

### v1.0.0 (2026-01-07)
- ✅ 初回リリース
- ✅ Cloudflare Tunnel自動作成
- ✅ hostname版メタデータシステム
- ✅ demo.persys.jp で動作確認完了

### v1.0.1 (2026-01-08)
- ⚠️ タイムアウト問題の調査中
- 📝 トラブルシューティング追加
- 🔧 provisioner-verbose.py（詳細ログ版）作成中
