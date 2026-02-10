"""
Tamesuke バックエンド API

FastAPI アプリケーションのエントリポイント。
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.config import get_settings
from api.routes import subdomain, checkout, webhook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """起動・終了時のログ出力"""
    logger.info("Tamesuke API 起動")
    yield
    logger.info("Tamesuke API 終了")


app = FastAPI(
    title="Tamesuke API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"https://{settings.app_domain}",
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(subdomain.router)
app.include_router(checkout.router)
app.include_router(webhook.router)


@app.get("/health")
async def health() -> dict:
    """ヘルスチェック"""
    return {"status": "ok"}


# フロントエンド静的ファイル配信（APIルートより後にマウント）
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
