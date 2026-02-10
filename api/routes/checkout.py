"""
Stripe Checkout Session 作成 API

フォーム入力を受け取り、Stripe Checkout ページの URL を返す。
"""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from api.routes.subdomain import _validate_subdomain, _check_dns
from api.services import stripe_service

logger = logging.getLogger(__name__)
router = APIRouter()


class CheckoutRequest(BaseModel):
    """Checkout Session 作成リクエスト"""
    email: EmailStr
    company_name: str
    oss_type: Literal["nginx"]
    duration_days: Literal[7, 14]
    subdomain: str


@router.post("/api/create-checkout")
async def create_checkout(body: CheckoutRequest) -> dict:
    """
    Stripe Checkout Session を作成し、checkout_url を返す。

    処理フロー:
    1. サブドメインバリデーション
    2. サブドメイン重複チェック
    3. Checkout Session 作成

    Returns:
        {"checkout_url": str}
    """
    # 1. サブドメインバリデーション
    _validate_subdomain(body.subdomain)

    # 2. サブドメイン重複チェック
    loop = asyncio.get_event_loop()
    available = await loop.run_in_executor(None, _check_dns, body.subdomain)
    if not available:
        raise HTTPException(
            status_code=409,
            detail=f"サブドメイン '{body.subdomain}' は既に使用されています",
        )

    # 3. Checkout Session 作成
    try:
        session = stripe_service.create_checkout_session(
            email=body.email,
            company_name=body.company_name,
            oss_type=body.oss_type,
            duration_days=body.duration_days,
            subdomain=body.subdomain,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Checkout Session 作成失敗: %s", e)
        raise HTTPException(status_code=500, detail="決済セッションの作成に失敗しました")

    return {"checkout_url": session.url}
