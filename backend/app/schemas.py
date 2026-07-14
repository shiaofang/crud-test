"""请求/响应数据模型（Pydantic）：负责入参校验与出参序列化。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, EmailStr


class ProductBase(BaseModel):
    """商品公共字段，供创建与输出模型复用。"""

    name: str = Field(..., min_length=1, max_length=100, description="商品名称")
    description: str | None = Field(None, max_length=500, description="描述")
    price: float = Field(0, ge=0, description="价格")
    stock: int = Field(0, ge=0, description="库存")


class ProductCreate(ProductBase):
    """创建商品的入参。"""


class ProductUpdate(BaseModel):
    """更新商品的入参，所有字段可选，仅更新显式传入的字段。"""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    price: float | None = Field(None, ge=0)
    stock: int | None = Field(None, ge=0)


class ProductOut(ProductBase):
    """商品输出模型，可直接从 ORM 实例转换。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    clickCount: int = Field(0, ge=0, description="点击量")
    created_at: datetime
    updated_at: datetime


class ProductList(BaseModel):
    """分页列表响应。"""

    total: int
    items: list[ProductOut]


class UserRegister(BaseModel):
    """注册入参。"""

    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    email: EmailStr | None = Field(None, description="邮箱")


class UserLogin(BaseModel):
    """登录入参。"""

    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


class Token(BaseModel):
    """登录成功返回的令牌。"""

    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    """用户信息输出。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    created_at: datetime


class UserUpdate(BaseModel):
    """更新用户的入参，所有字段可选。"""

    username: str | None = Field(None, min_length=3, max_length=50)
    email: EmailStr | None = Field(None, description="邮箱")
    password: str | None = Field(None, min_length=6, max_length=128, description="新密码")


class UserList(BaseModel):
    """用户分页列表响应。"""

    total: int
    items: list[UserOut]


class ChatMessage(BaseModel):
    """对话中的单条消息。"""

    role: str = Field(..., pattern="^(user|assistant)$", description="角色")
    content: str = Field(..., min_length=1, max_length=8000, description="内容")


class ChatRequest(BaseModel):
    """智能助手聊天入参。"""

    message: str = Field(..., min_length=1, max_length=4000, description="用户当前消息")
    history: list[ChatMessage] = Field(default_factory=list, max_length=40, description="历史消息")
