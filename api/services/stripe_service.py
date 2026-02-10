"""
Stripe サービス

Checkout Session 作成、Webhook 署名検証、Subscription メタデータ更新を行う。
"""

import logging
from typing import Any, Dict

import stripe

from api.config import get_settings

logger = logging.getLogger(__name__)

# price_id マッピング: (oss_type, duration_days) → Settings のフィールド名
_PRICE_FIELD_MAP: Dict[tuple, str] = {
    ("nginx", 7): "stripe_price_nginx_7d",
    ("nginx", 14): "stripe_price_nginx_14d",
}


def _get_price_id(oss_type: str, duration_days: int) -> str:
    """OSSタイプと期間から price_id を取得する。"""
    key = (oss_type, duration_days)
    field = _PRICE_FIELD_MAP.get(key)
    if field is None:
        raise ValueError(f"未対応の組み合わせ: oss_type={oss_type}, duration_days={duration_days}")
    return getattr(get_settings(), field)


def create_checkout_session(
    email: str,
    company_name: str,
    oss_type: str,
    duration_days: int,
    subdomain: str,
) -> stripe.checkout.Session:
    """
    Stripe Checkout Session を作成する。

    metadata に subdomain / oss_type / duration_days を埋め込み、
    Webhook (checkout.session.completed) で取り出す。

    Args:
        email: 顧客メールアドレス
        company_name: 会社名
        oss_type: OSSタイプ
        duration_days: 利用期間（日数）
        subdomain: 希望サブドメイン

    Returns:
        Stripe Checkout Session オブジェクト
    """
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    price_id = _get_price_id(oss_type, duration_days)

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        customer_email=email,
        line_items=[{"price": price_id, "quantity": 1}],
        metadata={
            "subdomain": subdomain,
            "oss_type": oss_type,
            "duration_days": str(duration_days),
            "company_name": company_name,
        },
        subscription_data={
            "metadata": {
                "subdomain": subdomain,
                "oss_type": oss_type,
                "duration_days": str(duration_days),
            },
        },
        success_url=f"https://{settings.app_domain}/success.html?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"https://{settings.app_domain}/cancel.html",
    )

    logger.info("Checkout Session 作成: id=%s, subdomain=%s", session.id, subdomain)
    return session


def verify_webhook(payload: bytes, sig_header: str) -> stripe.Event:
    """
    Stripe Webhook の署名を検証し、Event オブジェクトを返す。

    Args:
        payload: リクエストボディ（raw bytes）
        sig_header: Stripe-Signature ヘッダー値

    Returns:
        検証済み Stripe Event

    Raises:
        stripe.error.SignatureVerificationError: 署名不正
        ValueError: ペイロード不正
    """
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    event = stripe.Webhook.construct_event(
        payload,
        sig_header,
        settings.stripe_webhook_secret,
    )

    logger.info("Webhook 検証成功: type=%s, id=%s", event.type, event.id)
    return event


def update_subscription_metadata(
    subscription_id: str,
    metadata: Dict[str, Any],
) -> stripe.Subscription:
    """
    Subscription の metadata にプロビジョニング結果を書き込む。

    Args:
        subscription_id: Stripe Subscription ID
        metadata: 追加するメタデータ（vmid, url, tunnel_id 等）

    Returns:
        更新後の Subscription オブジェクト
    """
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key

    # metadata の値は文字列に変換
    str_metadata = {k: str(v) for k, v in metadata.items()}

    subscription = stripe.Subscription.modify(
        subscription_id,
        metadata=str_metadata,
    )

    logger.info(
        "Subscription メタデータ更新: id=%s, keys=%s",
        subscription_id, list(str_metadata.keys()),
    )
    return subscription
