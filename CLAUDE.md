# Tamesuke プロジェクト

## プロジェクト概要

Tamesuke（ためすけ）は、中小企業向けOSSお試しSaaS環境。
ユーザーがWebフォームから申し込むと、自動でLXCコンテナがプロビジョニングされ、
`xxx.tamesuke.jp` でOSSを試用できる。

## リポジトリ構造

```
tamesuke/
├── provisioner.py          # ★既存★ 自動プロビジョニング（完成済み、変更しない）
├── requirements.txt        # 既存の依存関係
├── .env.example            # 既存の環境変数テンプレート
├── templates/              # LXCテンプレート関連
├── readme_provisioner.md   # provisioner.pyのドキュメント
│
├── CLAUDE.md               # このファイル
│
│── api/                    # ★新規作成★ バックエンドAPI
│   ├── main.py             # FastAPIアプリケーション
│   ├── routes/
│   │   ├── checkout.py     # Stripe Checkout Session作成
│   │   ├── webhook.py      # Stripe Webhook受信
│   │   └── subdomain.py    # サブドメイン重複チェック
│   ├── services/
│   │   ├── stripe_service.py    # Stripe操作
│   │   ├── provision_service.py # provisioner.py呼び出しラッパー
│   │   ├── cleanup_service.py   # 期限切れ自動削除
│   │   └── email_service.py     # メール送信
│   ├── config.py           # 設定・環境変数管理
│   └── requirements.txt    # API用追加依存関係
│
└── frontend/               # ★新規作成★ フロントエンド
    ├── index.html          # LP + 申し込みフォーム
    ├── success.html        # 決済完了ページ
    ├── cancel.html         # 決済キャンセルページ
    └── assets/
        ├── style.css
        └── app.js          # Stripe Checkout連携JS
```

## 既存コンポーネント（変更禁止）

### provisioner.py

自動プロビジョニングスクリプト。**このファイルは変更しない。**
まず `provisioner.py` を読んで、実際の関数シグネチャと戻り値を確認すること。

サービスフローから推測されるインターフェース（実際のコードで確認せよ）:

```python
# provisioner.py の主要関数（推測）
# 実際のシグネチャはコードを読んで確認すること

def provision(subdomain, oss_type, customer_email, ...):
    """
    プロビジョニング実行
    
    処理内容:
    1. VMID割り当て（9000-9999の未使用番号）
    2. Cloudflare Tunnel作成
    3. Tunnel Token取得
    4. Tunnelルーティング設定
    5. DNS CNAME登録
    6. メタデータJSON作成・アップロード
    7. LXCクローン（8011 → 新規VMID）
    8. LXC起動
    9. 初期化待機
    10. サービス起動確認（HTTP 200）
    
    Returns: dict with vmid, url, tunnel_id など
    """
```

### 環境変数（既存 .env）

```bash
# Proxmox接続
PROXMOX_HOST=192.168.11.5
PROXMOX_USER=root@pam
PROXMOX_PASSWORD=xxx
PROXMOX_NODE=odin

# File Server
FILESERVER_HOST=10.2.1.4
FILESERVER_PORT=8080

# Cloudflare（provisioner.pyが使用）
CLOUDFLARE_API_TOKEN=xxx
CLOUDFLARE_ACCOUNT_ID=xxx
CLOUDFLARE_ZONE_ID=xxx
```

## 新規作成するもの

### 1. バックエンドAPI（FastAPI）

**稼働場所**: testserver (LXC 8002) — provisioner.pyと同じサーバー

**エンドポイント**:

| Method | Path | 説明 |
|--------|------|------|
| GET | `/api/check-subdomain?subdomain=xxx` | サブドメイン重複チェック |
| POST | `/api/create-checkout` | Stripe Checkout Session作成 |
| POST | `/webhook/stripe` | Stripe Webhook受信 → プロビジョニング |
| GET | `/health` | ヘルスチェック |

**Stripe Webhook処理フロー**:
```
checkout.session.completed → provision() → Subscriptionメタデータ更新 → ウェルカムメール
customer.subscription.deleted → cleanup() → サンキューメール
```

**Stripeデータモデル**:
- Customer: email, name, metadata(company_name)
- Subscription metadata: subdomain, oss_type, duration_days, vmid, url, tunnel_id
- Product/Price: OSSタイプ × 期間の組み合わせ

**追加環境変数（.envに追加）**:
```bash
# Stripe
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_NGINX_7D=price_xxx
STRIPE_PRICE_NGINX_14D=price_xxx

# Email（SendGrid）
SENDGRID_API_KEY=SG.xxx
EMAIL_FROM=noreply@persys.jp

# App
APP_DOMAIN=tamesuke.persys.jp
SERVICE_DOMAIN=persys.jp
```

### 2. フロントエンド

**シンプルなvanilla HTML+JS**（フレームワーク不要）
- LP（ランディングページ）+ 申し込みフォーム
- Stripe Checkoutページへリダイレクト
- 成功/キャンセルページ

**フォーム入力項目**:
- メールアドレス
- 会社名
- 試したいOSS（選択: nginx / growi / wordpress）
- お試し期間（選択: 7日間 / 14日間）
- 希望サブドメイン（12文字以内、英小文字・数字・ハイフンのみ）

### 3. 自動削除（cleanup）

Stripe Subscription削除イベント → LXC停止・削除 + Tunnel削除 + DNS削除

## 技術的制約

- **顧客管理DB不要**: Stripeが全て管理
- **テンプレート**: 現在は nginx (8011) のみ。将来 WordPress, Growi 追加予定
- **ドメイン**: サービスURL は `{subdomain}.persys.jp`
- **初期リリースではメール送信と自動削除は手動で可**（①②③が揃えばリリース可能）

## コーディング規約

- Python: FastAPI + async/await
- 型ヒント必須
- docstring必須（日本語OK）
- エラーハンドリング: 適切なHTTPステータスコードとエラーメッセージ
- ログ: Python logging モジュール使用
- コメント: 日本語OK
