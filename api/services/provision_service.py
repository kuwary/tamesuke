"""
プロビジョニングサービス

provisioner.py の TamesukeProvisioner をラップし、
FastAPI から async で呼び出せるようにする。
"""

import asyncio
import logging
from functools import lru_cache
from typing import Any, Dict

from api.config import Settings, get_settings

# provisioner.py はリポジトリルートにあるため、sys.path 調整なしで
# プロジェクトルートから起動する前提
from provisioner import TamesukeProvisioner

logger = logging.getLogger(__name__)


@lru_cache()
def _get_provisioner() -> TamesukeProvisioner:
    """Settings から TamesukeProvisioner を生成（キャッシュ付き）"""
    s = get_settings()
    provisioner = TamesukeProvisioner(
        proxmox_host=s.proxmox_host,
        proxmox_user=s.proxmox_user,
        proxmox_password=s.proxmox_password,
        cloudflare_token=s.cloudflare_api_token,
        cloudflare_account_id=s.cloudflare_account_id,
        cloudflare_zone_id=s.cloudflare_zone_id,
        fileserver_host=s.fileserver_host,
        fileserver_port=s.fileserver_port,
        domain=s.domain,
        proxmox_node=s.proxmox_node,
    )
    provisioner.connect()
    return provisioner


async def run_provision(
    customer_email: str,
    oss_type: str,
    subdomain: str,
    duration_days: int,
) -> Dict[str, Any]:
    """
    プロビジョニングを非同期で実行する。

    provisioner.provision() は同期処理のため、
    run_in_executor でスレッドプールに委譲する。

    Args:
        customer_email: 顧客メールアドレス
        oss_type: OSSタイプ（nginx 等）
        subdomain: サブドメイン
        duration_days: 利用期間（日数）

    Returns:
        プロビジョニング結果
        {"vmid": int, "tunnel_id": str, "url": str, "status": str}

    Raises:
        ValueError: 入力バリデーションエラー
        Exception: インフラ側エラー
    """
    logger.info(
        "プロビジョニング開始: email=%s, oss=%s, subdomain=%s, days=%d",
        customer_email, oss_type, subdomain, duration_days,
    )

    provisioner = _get_provisioner()
    loop = asyncio.get_event_loop()

    result = await loop.run_in_executor(
        None,
        lambda: provisioner.provision(
            customer_email=customer_email,
            oss_type=oss_type,
            subdomain=subdomain,
            duration_days=duration_days,
        ),
    )

    logger.info(
        "プロビジョニング完了: vmid=%s, url=%s",
        result.get("vmid"), result.get("url"),
    )
    return result
