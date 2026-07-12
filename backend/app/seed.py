"""首次启动时写入热门商品示例数据。"""

from sqlalchemy.orm import Session

from . import crud, schemas


SAMPLE_HOT_PRODUCTS = [
    {
        "name": "无线蓝牙耳机",
        "description": "降噪长续航，通勤运动皆宜",
        "price": 299.00,
        "stock": 128,
        "sort_order": 1,
    },
    {
        "name": "智能运动手表",
        "description": "心率监测 · GPS定位 · 50米防水",
        "price": 899.00,
        "stock": 56,
        "sort_order": 2,
    },
    {
        "name": "316不锈钢保温杯",
        "description": "24小时保温，简约便携",
        "price": 59.00,
        "stock": 320,
        "sort_order": 3,
    },
    {
        "name": "20000mAh 充电宝",
        "description": "双向快充，多设备同时充",
        "price": 129.00,
        "stock": 200,
        "sort_order": 4,
    },
    {
        "name": "轻量缓震跑鞋",
        "description": "透气网面，日常跑步舒适之选",
        "price": 399.00,
        "stock": 88,
        "sort_order": 5,
    },
    {
        "name": "静音加湿器",
        "description": "大容量水箱，卧室办公两用",
        "price": 199.00,
        "stock": 150,
        "sort_order": 6,
    },
]


def seed_hot_products(db: Session) -> None:
    """表为空时插入示例热门商品。"""
    if crud.count_hot_products(db) > 0:
        return
    for item in SAMPLE_HOT_PRODUCTS:
        crud.create_hot_product(db, schemas.HotProductCreate(**item))
