"""
クリーンアップサービス

provisioner.py の TamesukeProvisioner.cleanup() をラップし、
FastAPI から async で呼び出せるようにする。
"""

import asyncio
import logging

from api.services.provision_service import _get_provisioner

logger = logging.getLogger(__name__)


async def run_cleanup(vmid: int, tunnel_id: str, subdomain: str) -> None:
    """
    クリーンアップを非同期で実行する。

    LXC停止・削除、Tunnel削除、DNS削除、メタデータ削除を行う。
    各ステップは独立して実行され、1つ失敗しても残りは続行する。

    Args:
        vmid: 削除対象の VMID
        tunnel_id: 削除対象の Cloudflare Tunnel ID
        subdomain: 削除対象のサブドメイン
    """
    logger.info(
        "クリーンアップ開始: vmid=%s, tunnel_id=%s, subdomain=%s",
        vmid, tunnel_id, subdomain,
    )

    provisioner = _get_provisioner()
    loop = asyncio.get_event_loop()

    await loop.run_in_executor(
        None,
        lambda: provisioner.cleanup(
            vmid=vmid,
            tunnel_id=tunnel_id,
            subdomain=subdomain,
        ),
    )

    logger.info("クリーンアップ完了: vmid=%s", vmid)
