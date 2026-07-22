# 登录与注册功能数据模型设计

## 概述

SmartOncall 的用户认证系统，基于 MySQL（持久化）+ Redis（临时态）+ JWT（无状态令牌）实现。

- 认证方式：邮箱+密码、邮箱+验证码
- ORM：SQLAlchemy 2.0 (async)
- 无角色/权限区分
- 登录凭证仅为 email，username 为展示字段

## MySQL 数据模型

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(50))  # 仅展示用，非登录凭证
    password_hash: Mapped[str] = mapped_column(String(255))  # bcrypt
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
```

设计要点：
- `email` 唯一索引，作为唯一登录标识
- `username` 无唯一约束，纯展示字段，注册时填写，后续功能调用时读取
- `password_hash` 存 bcrypt 哈希，永不明文
- `is_active` 用于禁用账户
- 邮箱验证码登录时，只要 email 匹配且 `is_active=True` 即可

## Redis 键设计

```
# 1. 邮箱验证码（登录/注册）
key:    verify_code:{email}
value:  6位随机码
TTL:    300s (5分钟)

# 2. 验证码发送频率限制
key:    verify_limit:{email}
value:  1（存在即表示已发送）
TTL:    60s (1分钟内不可重复发送)

# 3. Refresh Token（支持主动吊销）
key:    refresh_token:{user_id}:{token_jti}
value:  token 元数据（创建时间、设备标识）
TTL:    604800s (7天，与 refresh token 有效期一致)

# 4. 登录失败限流（防暴力破解）
key:    login_fail:{email}
value:  连续失败次数
TTL:    900s (15分钟锁定窗口)

# 5. 用户会话缓存（减少 MySQL 查询）
key:    user_cache:{user_id}
value:  JSON序列化的用户基本信息（email, username, is_active）
TTL:    1800s (30分钟)
```

设计要点：
- 所有 key 用 `{类型}:{标识}` 命名，便于 SCAN 按前缀管理
- 验证码验证后立即删除（一次性使用）
- 登出时删除对应 refresh_token key，实现主动吊销
- 用户信息修改时主动失效 user_cache
- 登录失败 5 次后锁定 15 分钟，锁定期间拒绝密码登录（验证码登录不受影响）

## 认证流程

### 注册流程

```
用户提交 {email} 请求发送验证码
    │
    ├─ 1. 正则校验 email 格式，不合法则直接返回错误提示
    ├─ 2. 检查 email 是否已注册（MySQL 查询）
    ├─ 3. 检查 verify_limit:{email} 是否存在（60s 防重复）
    ├─ 4. 发送验证码到邮箱，写入 Redis verify_code:{email} (TTL 300s)
    │
用户提交 {email, code, username, password}（前端持有数据，验证时一并提交）
    │
    ├─ 5. 正则校验 email 格式（防止前端篡改）
    ├─ 6. 用提交的 email 去 Redis 读取 verify_code:{email}
    │     └─ 若不存在 → 说明验证码对应的不是这个邮箱，返回错误
    ├─ 7. 比对验证码，通过后立即删除
    ├─ 8. bcrypt 哈希密码，写入 MySQL users 表
    └─ 9. 返回注册成功
```

关键防护：
- 验证码绑定发送时的 email（key 就是 verify_code:{email}），用户提交验证时用修改后的 email 去查自然查不到
- 发送前和验证时都做正则校验，双重防护
- 正则：`^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`

### 密码登录流程

```
用户提交 {email, password}
    │
    ├─ 1. 检查 login_fail:{email} 是否被锁定
    ├─ 2. 查询 MySQL 获取用户（命中 user_cache 则跳过 DB）
    ├─ 3. bcrypt 验证密码
    │     ├─ 失败 → login_fail:{email} INCR，返回错误
    │     └─ 成功 → 删除 login_fail:{email}
    ├─ 4. 签发 access_token (JWT, 15min) + refresh_token (JWT, 7d)
    ├─ 5. refresh_token 写入 Redis refresh_token:{user_id}:{jti}
    └─ 6. 返回 tokens
```

### 验证码登录流程

```
用户提交 {email} 请求验证码
    │
    ├─ 1. 检查 verify_limit:{email} 是否存在（60s 防重复）
    ├─ 2. 检查 email 是否已注册（未注册则拒绝，引导注册）
    ├─ 3. 发送验证码，写入 Redis verify_code:{email} (TTL 300s)
    │
用户提交 {email, code}
    │
    ├─ 4. 校验验证码（Redis 读取后立即删除）
    ├─ 5. 签发 access_token + refresh_token（同上）
    └─ 6. 返回 tokens
```

### Token 刷新

```
用户提交 {refresh_token}
    │
    ├─ 1. 验证 JWT 签名和过期时间
    ├─ 2. 检查 Redis refresh_token:{user_id}:{jti} 是否存在（是否被吊销）
    ├─ 3. 签发新 access_token（可选：轮换 refresh_token）
    └─ 4. 返回新 token
```

### 登出

```
用户提交 {refresh_token}
    │
    ├─ 1. 删除 Redis refresh_token:{user_id}:{jti}
    └─ 2. access_token 自然过期（15min 内仍有效，无状态代价）
```

## 代码模块结构

```
apps/backend/src/smartoncall/
├── services/
│   ├── __init__.py
│   └── auth/
│       ├── __init__.py
│       ├── router.py          # /auth/register, /auth/login, /auth/refresh, /auth/logout
│       ├── schemas.py         # Pydantic 请求/响应模型
│       ├── service.py         # 认证业务逻辑
│       ├── jwt.py             # JWT 签发/验证
│       ├── dependencies.py    # FastAPI 依赖（get_current_user）
│       └── validators.py      # 邮箱正则校验
├── models/
│   ├── __init__.py
│   └── user.py                # SQLAlchemy User 模型
├── db/
│   ├── __init__.py
│   ├── mysql.py               # SQLAlchemy async engine + session
│   └── redis.py               # Redis 连接池（redis.asyncio）
├── config.py                  # Settings（pydantic-settings）
└── main.py
```

## 错误处理

| 场景 | HTTP 状态码 | 错误信息 |
|------|------------|----------|
| 邮箱格式不合法 | 422 | "邮箱格式不正确" |
| 邮箱已注册 | 409 | "该邮箱已注册" |
| 验证码发送过频（60s 内） | 429 | "请60秒后再试" |
| 验证码错误/过期 | 400 | "验证码错误或已过期" |
| 密码错误 | 401 | "邮箱或密码错误"（不区分哪个错） |
| 登录被锁定 | 423 | "登录尝试过多，请15分钟后再试" |
| refresh_token 无效/已吊销 | 401 | "登录已过期，请重新登录" |
| 账户被禁用 | 403 | "账户已被禁用" |

## 配置

```python
class Settings(BaseSettings):
    # MySQL
    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_DATABASE: str = "smartoncall"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 邮箱验证码
    VERIFY_CODE_TTL: int = 300
    VERIFY_SEND_INTERVAL: int = 60

    # 登录限流
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCK_TTL: int = 900
```

## 依赖库

```toml
"sqlalchemy[asyncio]>=2.0",
"aiomysql",
"redis[hiredis]>=5.0",
"pyjwt",
"bcrypt",
"pydantic-settings",
```

## 可观测性（结构化日志）

使用 `structlog` 实现结构化 JSON 日志，通过 FastAPI 中间件为每个请求注入唯一 `request_id`，贯穿整条调用链。

### 中间件

```python
# middleware/request_context.py
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

### structlog 配置

```python
# logging_config.py
import structlog

def setup_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
```

### 日志输出示例

```json
{
  "request_id": "a3f1b2c4-...",
  "level": "info",
  "timestamp": "2026-07-22T10:30:00Z",
  "event": "登录成功",
  "user_id": 42,
  "email": "user@example.com"
}
```

```python
logger.info("登录成功", user_id=user.id, email=user.email)
logger.warning("登录失败，密码错误", email=email)
logger.info("注册成功", user_id=user.id, email=user.email)
logger.info("验证码已发送", email=email)
```

### 使用规范

- 所有业务日志通过 `structlog.get_logger()` 获取 logger
- 禁止使用 `print()` 或标准 `logging` 模块直接输出
- 字段 key 保持英文（request_id、user_id 等），event 事件描述使用中文
- 敏感字段（password、验证码）禁止写入日志
- 认证相关关键事件必须记录：注册成功、登录成功/失败、token 刷新、登出

### 模块结构新增

```
apps/backend/src/smartoncall/
├── middleware/
│   ├── __init__.py
│   └── request_context.py   # RequestContextMiddleware
├── logging_config.py        # structlog 配置
```

### 依赖新增

```toml
"structlog>=24.0",
```

## 测试策略

| 层级 | 覆盖内容 | 工具 |
|------|----------|------|
| 单元测试 | validators（邮箱正则）、jwt 签发/验证、密码哈希 | pytest |
| 集成测试 | 完整注册/登录/刷新/登出流程 | pytest + httpx.AsyncClient |
| 依赖处理 | MySQL 用 testcontainers 或 SQLite in-memory；Redis 用 fakeredis | — |
