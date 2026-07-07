"""健康检查路由，用于探活/监控。"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """返回服务运行状态。"""
    return {"status": "ok"}
