"""认证：邮箱注册、密码哈希、会话 token。

为什么全用标准库
--------------------------------------------------------------------------
项目原则是"下载下来就能用"，不引额外依赖。密码哈希用 ``hashlib.pbkdf2_hmac``，
token 用 ``hmac`` + ``base64`` 自签——两者都是密码学原语，标准库就有，
不必为此装一个包。

密码怎么存
--------------------------------------------------------------------------
只存 ``pbkdf2_hmac("sha256", 密码, salt, 迭代数)`` 的结果与 salt，绝不存明文。
**每个用户一个独立 salt**（而不是全局一个 pepper）：库一旦泄露，攻击者也不能
用一张彩虹表把所有人一起破掉，必须逐用户算。迭代数取 20 万——在本机约 60ms，
是"用户能忍的登录延迟"与"暴力破解成本"之间的平衡点。

``hash_password`` 刻意做成**纯函数**，慢活留在 ``session()`` 之外跑：
数据库那把锁是全程持有的，把 60ms 的哈希塞进去会把别的请求一起堵住。

token 怎么签
--------------------------------------------------------------------------
``{user_id}.{过期时刻}.{签名}``，签名是 ``hmac_sha256(secret, "{user_id}.{过期时刻}")``。
无状态那部分（验签）让服务端不必查库就能挡掉伪造与篡改；**同时**在
``sessions`` 表留一份，才能做到"登出即失效"。两件事都做，各管一头。

secret 从哪来
--------------------------------------------------------------------------
优先环境变量 ``RSDS_SECRET_KEY``；没有就在库里生成一个随机值存进 ``meta``。
零配置也能用，而且重启之后已发出的 token 不会集体失效（若每次启动随机生成，
用户每重启一次就被登出一次）。

降级约定
--------------------------------------------------------------------------
数据库不可用时抛 :class:`~.db.DatabaseUnavailable`，由路由层转成 503。
认证与历史记录不同——历史是附加项，认证是入口本身，不能悄悄降级成"随便进"。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

from . import meta
from .db import Database, DatabaseUnavailable
from .errors import DomainError
from .store import StoreBase

#: PBKDF2 迭代次数。见模块注释。
PBKDF2_ITERATIONS = 200_000

#: 每个用户的 salt 长度（字节）
SALT_BYTES = 16

#: 会话有效期：30 天。桌面版是"自己的机器"，不必频繁重新登录。
TOKEN_TTL = 30 * 24 * 3600.0

#: secret 在 meta 表里的键名
SECRET_META_KEY = "auth_secret"

#: 内置管理员。可用环境变量覆盖，见 :func:`admin_credentials`。
DEFAULT_ADMIN_EMAIL = "admin@renshengdaoshi.local"
DEFAULT_ADMIN_PASSWORD = "admin123456"

#: 邮箱校验。刻意宽松——只挡明显不是邮箱的输入，不做 RFC 5322 全集匹配：
#: 过严的正则会误杀合法地址，而"这个邮箱是否真的存在"本来也验证不了。
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: 密码最短长度
MIN_PASSWORD_LEN = 8


class AuthError(DomainError):
    """可预期的业务错误（邮箱重复、密码太短、账号密码不对）。

    只声明默认 ``code``——存 ``code``、转 HTTP 那些事都在 :class:`DomainError`
    与 ``server/errors.py`` 里，不在这里重写一遍。
    """

    default_code = "auth_error"


@dataclass(frozen=True)
class User:
    """一个已注册用户。**不含密码与 salt**——它会一路传到接口层。"""

    id: int
    email: str
    display_name: str
    is_admin: bool
    created_ts: float

    @property
    def name(self) -> str:
        """展示名：没填就用邮箱 @ 之前的部分。"""
        return self.display_name or self.email.split("@", 1)[0]


# ── 纯函数：密码 ────────────────────────────────────────────────────────


def new_salt() -> str:
    """生成一个 salt（base64url，无 padding）。"""
    return _b64(secrets.token_bytes(SALT_BYTES))


def hash_password(password: str, salt: str) -> str:
    """把密码派生成可入库的摘要。**纯函数**，可在锁外调用。"""
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    )
    return _b64(digest)


def verify_password(password: str, salt: str, expected: str) -> bool:
    """比对密码。用 ``compare_digest`` 而不是 ``==``：后者会在第一个不同的
    字节处提前返回，比对耗时随匹配前缀长度变化，理论上可被用来逐字节试探。"""
    return hmac.compare_digest(hash_password(password, salt), expected)


def _b64(raw: bytes) -> str:
    """urlsafe base64，去掉 ``=`` padding。

    去掉 padding 是为了让它能安全地放进 cookie 与 URL 里；urlsafe 的字母表
    只有 ``-`` 和 ``_``，所以用 ``.`` 做分隔符不会与内容冲突。
    """
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def validate_email(email: str) -> str:
    """规范化并校验邮箱，返回规范化结果。"""
    cleaned = (email or "").strip().lower()
    if not _EMAIL_RE.match(cleaned):
        raise AuthError("请填写有效的邮箱地址", "invalid_email")
    if len(cleaned) > 254:
        raise AuthError("邮箱地址过长", "invalid_email")
    return cleaned


def validate_password(password: str) -> str:
    """校验密码强度。"""
    if not password or len(password) < MIN_PASSWORD_LEN:
        raise AuthError(f"密码至少 {MIN_PASSWORD_LEN} 位", "weak_password")
    if len(password) > 200:
        raise AuthError("密码过长", "weak_password")
    return password


def admin_credentials() -> tuple[str, str]:
    """内置管理员的邮箱与初始密码（可被环境变量覆盖）。

    写死一份默认值是"开箱即用"的必要代价，所以另外留了两个环境变量：
    部署到线上时应该覆盖掉，否则任何人都能用这组公开的默认凭据进后台。
    """
    email = (os.environ.get("RSDS_ADMIN_EMAIL") or DEFAULT_ADMIN_EMAIL).strip().lower()
    password = os.environ.get("RSDS_ADMIN_PASSWORD") or DEFAULT_ADMIN_PASSWORD
    return email, password


# ── 存储 ────────────────────────────────────────────────────────────────


class AuthStore(StoreBase):
    """用户与会话的读写。

    ``Database`` 是惰性的，本类也惰性——构造时不碰磁盘。
    """

    def __init__(self, db: Optional[Database] = None, *, ttl: float = TOKEN_TTL) -> None:
        super().__init__(db)
        self._ttl = ttl
        self._secret: Optional[str] = None

    # ── 状态 ────────────────────────────────────────────────────────

    @property
    def ttl(self) -> float:
        return self._ttl

    # ── 用户 ────────────────────────────────────────────────────────

    def register(self, email: str, password: str, display_name: str = "") -> User:
        """注册一个用户。邮箱重复时抛 :class:`AuthError`。"""
        clean_email = validate_email(email)
        validate_password(password)
        clean_name = (display_name or "").strip()[:60]

        # 慢活（PBKDF2）留在事务外——见模块注释
        salt = new_salt()
        digest = hash_password(password, salt)

        now = time.time()
        with self._db.session() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO users (email, password_hash, salt, display_name, is_admin, created_ts) "
                    "VALUES (?, ?, ?, ?, 0, ?)",
                    (clean_email, digest, salt, clean_name, now),
                )
            except sqlite3.IntegrityError as exc:
                # UNIQUE 冲突。用异常而不是"先查再插"：后者在并发下有竞态，
                # 而唯一索引是数据库层面的事实
                raise AuthError("该邮箱已注册", "email_taken") from exc
            user_id = int(cursor.lastrowid)
        return User(
            id=user_id, email=clean_email, display_name=clean_name,
            is_admin=False, created_ts=now,
        )

    def authenticate(self, email: str, password: str) -> Optional[User]:
        """校验账号密码。失败返回 ``None``（不区分"邮箱不存在"与"密码错误"，
        免得把"这个邮箱注册过"这件事告诉给试探者）。"""
        clean_email = (email or "").strip().lower()
        row = self._fetch_user_row(clean_email)
        if row is None:
            # 邮箱不存在时也走一遍哈希，让两条分支耗时相近，
            # 不通过响应时间泄露"这个邮箱是否注册过"
            hash_password(password or "", new_salt())
            return None
        if not verify_password(password or "", row["salt"], row["password_hash"]):
            return None
        return _row_to_user(row)

    def get_user(self, user_id: int) -> Optional[User]:
        try:
            with self._db.session() as conn:
                row = conn.execute(
                    "SELECT * FROM users WHERE id = ?", (user_id,)
                ).fetchone()
        except DatabaseUnavailable:
            return None
        return _row_to_user(row) if row is not None else None

    def list_users(self) -> list[User]:
        with self._db.session() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY created_ts DESC, id DESC"
            ).fetchall()
        return [_row_to_user(r) for r in rows]

    def count_users(self) -> int:
        try:
            with self._db.session() as conn:
                return int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])
        except DatabaseUnavailable:
            return 0

    def set_admin(self, user_id: int, is_admin: bool) -> bool:
        with self._db.session() as conn:
            cursor = conn.execute(
                "UPDATE users SET is_admin = ? WHERE id = ?",
                (1 if is_admin else 0, user_id),
            )
            return cursor.rowcount > 0

    def update_password(self, user_id: int, password: str) -> bool:
        """改密码。**顺带踢掉该用户的所有会话**——改密码的常见动机是
        "我怀疑别人在用我的账号"，这时让旧 token 继续有效就说不过去了。"""
        validate_password(password)
        salt = new_salt()
        digest = hash_password(password, salt)
        with self._db.session() as conn:
            cursor = conn.execute(
                "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
                (digest, salt, user_id),
            )
            changed = cursor.rowcount > 0
            if changed:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            return changed

    def delete_user(self, user_id: int) -> bool:
        """删除用户，并清掉他的会话与个人书库。

        历史与画像**不删**：那两张表可能还留着别的用户的数据，而按 user_id
        删是另一个动作。这里只保证"人走了，登录入口与他的书没了"。
        """
        with self._db.session() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM user_books WHERE user_id = ?", (user_id,))
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cursor.rowcount > 0

    def _fetch_user_row(self, email: str):
        try:
            with self._db.session() as conn:
                return conn.execute(
                    "SELECT * FROM users WHERE email = ?", (email,)
                ).fetchone()
        except DatabaseUnavailable:
            return None

    # ── 会话 ────────────────────────────────────────────────────────

    def issue_token(self, user_id: int, *, ttl: Optional[float] = None) -> tuple[str, float]:
        """签发一个 token，返回 ``(token, 过期时刻)``。"""
        span = self._ttl if ttl is None else ttl
        expires = time.time() + span
        payload = f"{user_id}.{int(expires)}"
        signature = _b64(
            hmac.new(self._secret_bytes(), payload.encode("ascii"), hashlib.sha256).digest()
        )
        token = f"{payload}.{signature}"
        with self._db.session() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (token, user_id, created_ts, expires_ts) "
                "VALUES (?, ?, ?, ?)",
                (token, user_id, time.time(), expires),
            )
        return token, expires

    def resolve_token(self, token: str) -> Optional[User]:
        """验签 + 查库，返回对应用户；任一环节不过都返回 ``None``。"""
        parsed = self._verify_signature(token)
        if parsed is None:
            return None
        user_id, expires = parsed
        if expires < time.time():
            return None
        try:
            with self._db.session() as conn:
                row = conn.execute(
                    "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                    "WHERE s.token = ? AND s.expires_ts > ?",
                    (token, time.time()),
                ).fetchone()
        except DatabaseUnavailable:
            return None
        if row is None:
            return None
        return _row_to_user(row)

    def revoke_token(self, token: str) -> bool:
        """登出：把这条会话删掉。token 本身仍然验签通过，但查库查不到了。"""
        with self._db.session() as conn:
            return conn.execute("DELETE FROM sessions WHERE token = ?", (token,)).rowcount > 0

    def revoke_user_sessions(self, user_id: int) -> int:
        with self._db.session() as conn:
            return conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,)).rowcount

    def purge_expired_sessions(self, *, now: Optional[float] = None) -> int:
        """清掉过期会话。登录时顺带跑一次即可，不必定时任务。"""
        stamp = time.time() if now is None else now
        try:
            with self._db.session() as conn:
                return conn.execute(
                    "DELETE FROM sessions WHERE expires_ts < ?", (stamp,)
                ).rowcount
        except DatabaseUnavailable:
            return 0

    def _verify_signature(self, token: str) -> Optional[tuple[int, float]]:
        """只验签，不查库。返回 ``(user_id, 过期时刻)``。"""
        if not token or token.count(".") != 2:
            return None
        raw_id, raw_exp, signature = token.split(".")
        payload = f"{raw_id}.{raw_exp}"
        expected = _b64(
            hmac.new(self._secret_bytes(), payload.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            return int(raw_id), float(raw_exp)
        except ValueError:
            return None

    # ── secret ──────────────────────────────────────────────────────

    def _secret_bytes(self) -> bytes:
        return self._secret_value().encode("utf-8")

    def _secret_value(self) -> str:
        """取签名密钥：环境变量优先，其次库里持久化的那个，最后生成一个。

        缓存到实例上，避免每次验签都读一次库——验签是每个请求都要做的事。
        """
        if self._secret is not None:
            return self._secret

        from_env = (os.environ.get("RSDS_SECRET_KEY") or "").strip()
        if from_env:
            self._secret = from_env
            return self._secret

        with self._db.session() as conn:
            stored = meta.read_value(conn, SECRET_META_KEY)
            if stored:
                self._secret = stored
                return self._secret
            generated = _b64(secrets.token_bytes(32))
            meta.write_value(conn, SECRET_META_KEY, generated)
            self._secret = generated
            return self._secret

    # ── 初始化 ──────────────────────────────────────────────────────

    def ensure_admin(self) -> Optional[User]:
        """确保内置管理员存在。返回新建的（或已存在的）管理员。

        幂等：已存在同邮箱的账号就什么都不做——**不会**重置密码，
        否则管理员自己改过的密码会被每次重启悄悄改回默认值。
        """
        email, password = admin_credentials()
        if self._fetch_user_row(email) is not None:
            return None

        clean_email = validate_email(email)
        salt = new_salt()
        digest = hash_password(password, salt)
        now = time.time()
        with self._db.session() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO users "
                "(email, password_hash, salt, display_name, is_admin, created_ts) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (clean_email, digest, salt, "管理员", now),
            )
            if cursor.rowcount == 0:
                return None
            user_id = int(cursor.lastrowid)
        return User(
            id=user_id, email=clean_email, display_name="管理员",
            is_admin=True, created_ts=now,
        )


def _row_to_user(row) -> User:
    return User(
        id=int(row["id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"] or ""),
        is_admin=bool(row["is_admin"]),
        created_ts=float(row["created_ts"]),
    )


# ── 全局单例 ────────────────────────────────────────────────────────────

_store: Optional[AuthStore] = None


def get_auth_store() -> AuthStore:
    global _store
    if _store is None:
        _store = AuthStore()
    return _store


def reset_auth_store(store: Optional[AuthStore] = None) -> None:
    """换掉单例（测试用）。"""
    global _store
    _store = store
