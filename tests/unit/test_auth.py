"""认证：注册、登录、会话、内置管理员。

走真实 HTTP（TestClient）而不是直接调 service：要验证的正是"cookie 有没有
正确下发、401 有没有正确返回、响应里有没有漏出密码字段"这类接口层行为。
"""

from __future__ import annotations

import pytest

from server.services import auth as auth_module

EMAIL = "reader@example.com"
PASSWORD = "goodpass123"


def register(client, email=EMAIL, password=PASSWORD, name=""):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": name},
    )


def login(client, email, password):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def me(client, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/api/auth/me", headers=headers)


class TestRegister:
    def test_registers_and_logs_in_right_away(self, client):
        """注册成功即登录——他刚证明了自己知道密码，不必再登一次。"""
        resp = register(client)
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == EMAIL
        assert body["is_admin"] is False
        assert body["name"] == "reader"  # 没填昵称时取邮箱 @ 之前的部分
        assert me(client).json()["user"]["id"] == body["id"]

    def test_never_returns_password_material(self, client):
        """响应里绝不能出现密码相关字段。"""
        body = register(client).json()
        assert not {"password", "password_hash", "salt"} & set(body)

    def test_duplicate_email_rejected(self, client):
        register(client)
        resp = register(client, name="second")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "email_taken"

    def test_email_is_case_insensitive(self, client):
        """换个大小写不该能注册出第二个账号。"""
        register(client, email="Reader@Example.com")
        assert register(client, email="reader@example.com").status_code == 400

    @pytest.mark.parametrize("bad", ["not-an-email", "a@b", "@b.com", "a b@c.com", ""])
    def test_invalid_email_rejected(self, client, bad):
        resp = register(client, email=bad)
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_email"

    def test_short_password_rejected(self, client):
        resp = register(client, password="short")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "weak_password"

    def test_display_name_is_optional(self, client):
        body = register(client, name="").json()
        assert body["display_name"] == ""
        assert body["name"] == "reader"


class TestLogin:
    def test_login_success(self, client):
        register(client)
        client.post("/api/auth/logout")
        assert me(client).json()["user"] is None

        assert login(client, EMAIL, PASSWORD).status_code == 200
        assert me(client).json()["user"]["email"] == EMAIL

    def test_wrong_password_is_401(self, client):
        register(client)
        client.post("/api/auth/logout")
        resp = login(client, EMAIL, "wrongpass123")
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "bad_credentials"

    def test_unknown_email_gives_the_same_error(self, client):
        """不区分"邮箱不存在"与"密码错误"，免得把注册情况泄露给试探者。"""
        resp = login(client, "nobody@example.com", "whatever123")
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "bad_credentials"

    def test_bearer_token_also_works(self, client):
        """cookie 之外还支持 Authorization: Bearer，方便脚本与冒烟测试。"""
        register(client)
        token = client.cookies.get("rsds_session")
        assert token
        client.cookies.clear()
        assert me(client).json()["user"] is None
        assert me(client, token).json()["user"]["email"] == EMAIL

    def test_session_cookie_is_httponly(self, client):
        """cookie 不该能被 JS 读到。"""
        resp = register(client)
        header = resp.headers.get("set-cookie", "")
        assert "HttpOnly" in header
        assert "SameSite=lax" in header.replace("samesite", "SameSite")


class TestSession:
    def test_logout_invalidates_the_token(self, client):
        register(client)
        token = client.cookies.get("rsds_session")
        client.post("/api/auth/logout")
        # token 本身仍然验签通过，但服务端那份会话已被删掉
        assert me(client, token).json()["user"] is None

    def test_logout_without_session_is_still_ok(self, client):
        """登出的意图是"让我处于未登录状态"，已经达成就该算成功。"""
        assert client.post("/api/auth/logout").status_code == 200

    def test_tampered_token_rejected(self, client):
        register(client)
        token = client.cookies.get("rsds_session")
        assert me(client, token[:-4] + "AAAA").json()["user"] is None

    def test_token_signed_with_another_secret_rejected(self, client, monkeypatch):
        """换了签名密钥，旧 token 立刻失效。"""
        register(client)
        token = client.cookies.get("rsds_session")
        monkeypatch.setenv("RSDS_SECRET_KEY", "a-completely-different-secret")
        auth_module.reset_auth_store()
        assert me(client, token).json()["user"] is None

    @pytest.mark.parametrize("bad", ["abc", "a.b", "1.2.3.4", "..", "x.y.z", "1.2"])
    def test_garbage_token_rejected(self, client, bad):
        """畸形 token 一律当成未登录，不抛 500。"""
        resp = me(client, bad)
        assert resp.status_code == 200
        assert resp.json()["user"] is None

    def test_password_change_kills_old_sessions(self, client):
        """改密码的动机常是"怀疑别人在用我账号"，旧 token 必须一起失效。"""
        register(client)
        token = client.cookies.get("rsds_session")
        resp = client.post(
            "/api/auth/password",
            json={"old_password": PASSWORD, "new_password": "brandnew456"},
        )
        assert resp.status_code == 200
        assert me(client, token).json()["user"] is None
        assert login(client, EMAIL, "brandnew456").status_code == 200

    def test_password_change_requires_the_old_one(self, client):
        register(client)
        resp = client.post(
            "/api/auth/password",
            json={"old_password": "not-my-password", "new_password": "brandnew456"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "bad_password"

    def test_password_change_requires_login(self, client):
        assert client.post(
            "/api/auth/password",
            json={"old_password": "x" * 10, "new_password": "brandnew456"},
        ).status_code == 401


class TestBuiltinAdmin:
    def test_admin_exists_and_can_login(self, client):
        """内置管理员：首次启动写进库，凭据取自环境变量。"""
        resp = login(client, "admin@test.local", "admin-test-pw")
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True

    def test_admin_password_is_not_reset_on_restart(self, client):
        """重启不该把管理员自己改过的密码改回默认值。"""
        login(client, "admin@test.local", "admin-test-pw")
        assert client.post(
            "/api/auth/password",
            json={"old_password": "admin-test-pw", "new_password": "changed-by-admin"},
        ).status_code == 200

        # 模拟"再启动一次"：ensure_admin 应当什么都不做
        assert auth_module.get_auth_store().ensure_admin() is None
        assert login(client, "admin@test.local", "admin-test-pw").status_code == 401
        assert login(client, "admin@test.local", "changed-by-admin").status_code == 200

    def test_ensure_admin_is_idempotent(self, client):
        store = auth_module.get_auth_store()
        assert store.ensure_admin() is None
        assert store.ensure_admin() is None

    def test_normal_user_is_not_admin(self, client):
        register(client)
        assert me(client).json()["user"]["is_admin"] is False


class TestPasswordHashing:
    """哈希层的纯函数行为。"""

    def test_never_stores_plaintext(self):
        salt = auth_module.new_salt()
        digest = auth_module.hash_password("goodpass123", salt)
        assert "goodpass123" not in digest
        assert digest != "goodpass123"

    def test_same_password_different_salt_gives_different_digest(self):
        """每个用户独立 salt：库泄露也不能一张彩虹表通杀。"""
        a = auth_module.hash_password("goodpass123", auth_module.new_salt())
        b = auth_module.hash_password("goodpass123", auth_module.new_salt())
        assert a != b

    def test_verify_roundtrip(self):
        salt = auth_module.new_salt()
        digest = auth_module.hash_password("goodpass123", salt)
        assert auth_module.verify_password("goodpass123", salt, digest)
        assert not auth_module.verify_password("goodpass124", salt, digest)

    def test_unicode_password_works(self):
        """中文/emoji 密码不该炸。"""
        salt = auth_module.new_salt()
        digest = auth_module.hash_password("密码密码密码", salt)
        assert auth_module.verify_password("密码密码密码", salt, digest)

    def test_secret_is_persisted_not_regenerated(self):
        """签名密钥存在 meta 表里：重启后已发出的 token 不该集体失效。"""
        store = auth_module.get_auth_store()
        first = store._secret_value()
        auth_module.reset_auth_store()
        assert auth_module.get_auth_store()._secret_value() == first
