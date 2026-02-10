"""
メール送信サービス

SendGrid Web API v3 経由でメールを送信する。
sendgrid_api_key が未設定の場合はスキップする（開発・テスト用）。
設定済みで送信に失敗した場合は例外を raise する。
"""

import logging
from pathlib import Path

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Content

from api.config import get_settings

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def _load_template(name: str, **kwargs: str) -> str:
    """テンプレートファイルを読み込み、プレースホルダを置換する。"""
    path = _TEMPLATE_DIR / name
    template = path.read_text(encoding="utf-8")
    return template.format_map(kwargs)


def _is_enabled() -> bool:
    """SendGrid が設定済みかどうか"""
    s = get_settings()
    return bool(s.sendgrid_api_key and s.email_from)


def _send(to_email: str, subject: str, html_body: str) -> None:
    """
    メールを送信する共通処理。

    Args:
        to_email: 宛先メールアドレス
        subject: 件名
        html_body: 本文（HTML）

    Raises:
        RuntimeError: 送信失敗
    """
    if not _is_enabled():
        logger.warning("SendGrid 未設定のためメール送信をスキップ: to=%s", to_email)
        return

    s = get_settings()
    message = Mail(
        from_email=s.email_from,
        to_emails=to_email,
        subject=subject,
        html_content=Content("text/html", html_body),
    )

    try:
        client = SendGridAPIClient(s.sendgrid_api_key)
        response = client.send(message)
    except Exception as e:
        logger.error("メール送信エラー: to=%s, error=%s", to_email, e)
        raise RuntimeError(f"メール送信失敗: {e}") from e

    if response.status_code >= 400:
        logger.error(
            "メール送信失敗: to=%s, status=%s", to_email, response.status_code
        )
        raise RuntimeError(f"メール送信失敗: HTTP {response.status_code}")

    logger.info("メール送信成功: to=%s, subject=%s", to_email, subject)


def send_welcome_email(
    email: str,
    subdomain: str,
    url: str,
    oss_type: str,
    duration_days: int,
) -> None:
    """
    ウェルカムメール（プロビジョニング完了時）を送信する。

    Args:
        email: 宛先メールアドレス
        subdomain: サブドメイン
        url: サービスURL
        oss_type: OSSタイプ
        duration_days: 利用期間（日数）

    Raises:
        RuntimeError: 送信失敗（SendGrid 設定済みの場合）
    """
    subject = f"【Tamesuke】{oss_type} お試し環境のご案内"
    html_body = _load_template(
        "welcome_email.html",
        url=url,
        oss_type=oss_type,
        subdomain=subdomain,
        duration_days=str(duration_days),
    )
    _send(email, subject, html_body)


def send_thankyou_email(email: str, subdomain: str) -> None:
    """
    サンキューメール（解約・cleanup時）を送信する。

    Args:
        email: 宛先メールアドレス
        subdomain: サブドメイン

    Raises:
        RuntimeError: 送信失敗（SendGrid 設定済みの場合）
    """
    subject = "【Tamesuke】ご利用ありがとうございました"
    html_body = _load_template(
        "thankyou_email.html",
        subdomain=subdomain,
    )
    _send(email, subject, html_body)
