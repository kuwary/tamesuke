"""
Tamesuke API 設定モジュール

pydantic-settings で環境変数を一元管理する。
既存の .env ファイルを拡張し、Stripe / SendGrid / App 設定を追加。
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """アプリケーション設定（環境変数から読み込み）"""

    # --- Proxmox ---
    proxmox_host: str
    proxmox_user: str
    proxmox_password: str
    proxmox_node: str = "odin"

    # --- Cloudflare ---
    cloudflare_api_token: str
    cloudflare_account_id: str
    cloudflare_zone_id: str

    # --- File Server ---
    fileserver_host: str
    fileserver_port: int = 8080

    # --- ドメイン ---
    domain: str = "persys.jp"

    # --- Stripe ---
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_price_nginx_7d: str
    stripe_price_nginx_14d: str

    # --- SendGrid（初期リリースでは省略可） ---
    sendgrid_api_key: Optional[str] = None
    email_from: Optional[str] = None

    # --- App ---
    app_domain: str = "tamesuke.persys.jp"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


@lru_cache()
def get_settings() -> Settings:
    """設定のシングルトンを返す（キャッシュ付き）"""
    return Settings()
