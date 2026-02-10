"""
Stripe Webhook 受信 API

checkout.session.completed → プロビジョニング → メタデータ更新 → ウェルカムメール
customer.subscription.deleted → クリーンアップ → サンキューメール

処理はバックグラウンドで実行し、Stripe には即座に 200 を返す。
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from api.services import stripe_service, email_service
from api.services.provision_service import run_provision
from api.services.cleanup_service import run_cleanup

logger = logging.getLogger(__name__)
router = APIRouter()


async def _handle_checkout_completed(session: dict) -> None:
    """checkout.session.completed のバックグラウンド処理"""
    metadata = session.get("metadata", {})
    subdomain = metadata.get("subdomain")
    oss_type = metadata.get("oss_type")
    duration_days = int(metadata.get("duration_days", 0))
    customer_email = session.get("customer_email")
    subscription_id = session.get("subscription")

    logger.info(
        "Checkout completed: email=%s, subdomain=%s, oss=%s",
        customer_email, subdomain, oss_type,
    )

    # 1. プロビジョニング実行
    result = await run_provision(
        customer_email=customer_email,
        oss_type=oss_type,
        subdomain=subdomain,
        duration_days=duration_days,
    )

    # 2. Subscription メタデータ更新
    if subscription_id:
        stripe_service.update_subscription_metadata(
            subscription_id=subscription_id,
            metadata={
                "vmid": result["vmid"],
                "url": result["url"],
                "tunnel_id": result["tunnel_id"],
            },
        )

    # 3. ウェルカムメール（失敗してもログのみ）
    try:
        email_service.send_welcome_email(
            email=customer_email,
            subdomain=subdomain,
            url=result["url"],
            oss_type=oss_type,
            duration_days=duration_days,
        )
    except Exception as e:
        logger.error("ウェルカムメール送信失敗（続行）: %s", e)


async def _handle_subscription_deleted(subscription: dict) -> None:
    """customer.subscription.deleted のバックグラウンド処理"""
    metadata = subscription.get("metadata", {})
    vmid_str = metadata.get("vmid")
    tunnel_id = metadata.get("tunnel_id")
    subdomain = metadata.get("subdomain")
    customer_email = subscription.get("customer", {})

    # customer が文字列 ID の場合があるため、メールは metadata や
    # Stripe API から取得するのが確実だが、ここでは Subscription から
    # 直接取得できる customer_email は無いので、ログのみ対応
    # → customer オブジェクト展開済みなら email が取れる
    if isinstance(customer_email, dict):
        customer_email = customer_email.get("email")

    logger.info(
        "Subscription deleted: vmid=%s, subdomain=%s",
        vmid_str, subdomain,
    )

    if not all([vmid_str, tunnel_id, subdomain]):
        logger.error(
            "メタデータ不足のためクリーンアップをスキップ: vmid=%s, tunnel_id=%s, subdomain=%s",
            vmid_str, tunnel_id, subdomain,
        )
        return

    # 1. クリーンアップ実行
    await run_cleanup(
        vmid=int(vmid_str),
        tunnel_id=tunnel_id,
        subdomain=subdomain,
    )

    # 2. サンキューメール（失敗してもログのみ）
    if customer_email:
        try:
            email_service.send_thankyou_email(
                email=customer_email,
                subdomain=subdomain,
            )
        except Exception as e:
            logger.error("サンキューメール送信失敗（続行）: %s", e)


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    stripe_signature: str = Header(...),
) -> dict:
    """
    Stripe Webhook を受信する。

    署名検証後、即座に 200 を返し、処理はバックグラウンドで実行する。
    """
    payload = await request.body()

    # 署名検証
    try:
        event = stripe_service.verify_webhook(payload, stripe_signature)
    except Exception as e:
        logger.warning("Webhook 署名検証失敗: %s", e)
        raise HTTPException(status_code=400, detail="署名検証失敗")

    # イベントタイプ別にバックグラウンド処理を登録
    if event.type == "checkout.session.completed":
        background_tasks.add_task(
            _handle_checkout_completed, event.data.object
        )
    elif event.type == "customer.subscription.deleted":
        background_tasks.add_task(
            _handle_subscription_deleted, event.data.object
        )
    else:
        logger.info("未対応イベント（無視）: %s", event.type)

    return {"status": "ok"}
