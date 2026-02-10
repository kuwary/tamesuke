"""
サブドメイン重複チェック API

Cloudflare DNS に既存の CNAME レコードがあるかどうかで判定する。
"""

import asyncio
import logging
import re

from cloudflare import Cloudflare
from fastapi import APIRouter, HTTPException, Query

from api.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_subdomain(subdomain: str) -> None:
    """
    サブドメインのバリデーション。
    provisioner.py の _validate_subdomain と同じルール。

    Raises:
        HTTPException: バリデーションエラー（400）
    """
    if len(subdomain) > 12:
        raise HTTPException(
            status_code=400,
            detail=f"サブドメインは12文字以内にしてください（現在: {len(subdomain)}文字）",
        )
    if not re.match(r"^[a-z0-9-]+$", subdomain):
        raise HTTPException(
            status_code=400,
            detail="サブドメインは英小文字、数字、ハイフンのみ使用可能です",
        )
    if subdomain.startswith("-") or subdomain.endswith("-"):
        raise HTTPException(
            status_code=400,
            detail="サブドメインはハイフンで始まる・終わることはできません",
        )


def _check_dns(subdomain: str) -> bool:
    """
    Cloudflare DNS に CNAME レコードが存在するか確認する。

    Returns:
        True: 利用可能（レコードなし）, False: 使用中
    """
    s = get_settings()
    cf = Cloudflare(api_token=s.cloudflare_api_token)
    fqdn = f"{subdomain}.{s.domain}"

    records = cf.dns.records.list(
        zone_id=s.cloudflare_zone_id,
        name=fqdn,
    )

    for record in records:
        if record.name == fqdn:
            return False
    return True


@router.get("/api/check-subdomain")
async def check_subdomain(
    subdomain: str = Query(..., description="チェックするサブドメイン"),
) -> dict:
    """
    サブドメインの利用可否を返す。

    Returns:
        {"available": bool, "subdomain": str}
    """
    _validate_subdomain(subdomain)

    loop = asyncio.get_event_loop()
    available = await loop.run_in_executor(None, _check_dns, subdomain)

    return {"available": available, "subdomain": subdomain}
