"""测试夹具：为单元 / 集成测试提供共享的内容层与 HTTP 客户端。

性能设计
--------------------------------------------------------------------------
内容层（`ContentLoader`）与检索索引（`TFIDFRetriever`）在整个测试过程中是
**只读**的——没有任何用例会修改它们。因此二者按 **session 级**构建一次，
所有用例共享；只有真正需要"重新加载"语义的用例才自行构造独立实例
（见 ``tests/unit/test_content_loader.py``）。

改为 session 级之前，每个用例都会重建一次全量索引（约 1.4s/例），
整套测试耗时约 114s；现在索引只建一次。

夹具分层
--------------------------------------------------------------------------
    isolate_llm      (autouse) 关掉一切真实模型调用
    isolate_history  (autouse) 把历史记录数据库指向临时目录
    loader  (session)  全量内容，只读
    index   (session)  全量索引，依赖 loader
    client  (function) 复用了 session 级索引的 HTTP 客户端
"""

import os
import sys

import pytest

SERVER_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, SERVER_DIR)

# 必须在导入 server.main **之前**设定：后端是否挂载前端静态产物是导入时决定的。
# 单元/集成测试只针对 API 层，而仓库里一旦存在 web/dist，"/" 就会返回前端页面
# 而不是 API 索引（test_api.py 断言的正是后者）。静态托管由 smoke.py 走真实
# HTTP 验证，不在这里覆盖。
os.environ["RSDS_SERVE_FRONTEND"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

import server.main as main  # noqa: E402
from server import paths  # noqa: E402
from server.services import advice as advice_module  # noqa: E402
from server.services import admin as admin_module  # noqa: E402
from server.services import auth as auth_module  # noqa: E402
from server.services import content_loader  # noqa: E402
from server.services import history as history_module  # noqa: E402
from server.services import kb as kb_module  # noqa: E402
from server.services import profile as profile_module  # noqa: E402
from server.services import retriever as retriever_module  # noqa: E402
from server.services import user_books as user_books_module  # noqa: E402
from server.services.llm import router as llm_router_module  # noqa: E402
from server.services.llm import session as llm_session_module  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_history(tmp_path, monkeypatch):
    """隔离历史记录：每个用例一个全新的数据目录。

    历史记录是**会落盘**的（这也是这个功能的重点），若都写进仓库根目录下的
    ``data/``，用例之间会互相看到对方写进去的记录，而且跑到哪儿都会在源码树里
    留一个数据库文件。指向 ``tmp_path`` 之后，每个用例都是干净的库，用完随
    pytest 的临时目录一起回收。

    单例必须一并重置：它在构造时就把当时的路径记下来了，不重置的话第一个
    用例的库会一直用到底。
    """
    monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(tmp_path / "data"))
    history_module.reset_history_store()
    # 画像与历史同一个库文件，单例同样要重置，否则会用上一个用例的路径
    profile_module.reset_profile_store()
    yield
    history_module.reset_history_store()
    profile_module.reset_profile_store()


@pytest.fixture(autouse=True)
def isolate_auth(monkeypatch):
    """隔离认证。

    认证与历史记录共用同一个库文件，``isolate_history`` 已经把数据目录指向
    ``tmp_path``；这里只需把认证单例重置掉——它在构造时就把当时的路径记下来了。

    密钥与管理员凭据都固定成常量：否则每个用例都会往 meta 表写一个新随机密钥，
    调试时想手工造一个 token 会很别扭；管理员凭据固定下来，用例才能断言
    "内置管理员能登录"。
    """
    monkeypatch.setenv("RSDS_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("RSDS_ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("RSDS_ADMIN_PASSWORD", "admin-test-pw")
    auth_module.reset_auth_store()
    user_books_module.reset_user_book_store()
    admin_module.reset_admin_store()
    yield
    auth_module.reset_auth_store()
    user_books_module.reset_user_book_store()
    admin_module.reset_admin_store()


@pytest.fixture(autouse=True)
def isolate_llm(monkeypatch):
    """隔离 LLM：测试一律运行在"未配置密钥"状态，绝不发起真实网络请求。

    必须把变量置为**空串**而不是删除：``load_env_file`` 只填充"目标中尚不存在"
    的键，删掉反而会让项目根目录的 ``.env`` 被重新读进来，导致测试真的去调 API。
    """
    for var in ("LLM_API_KEY", "ZHIPUAI_API_KEY", "GLM_API_KEY"):
        monkeypatch.setenv(var, "")
    llm_router_module.reset_router()
    # 自定义端点的路由器按 Key 缓存，不清会让上一个用例填的端点串进下一个用例
    llm_session_module.reset_endpoints()
    yield
    llm_router_module.reset_router()
    llm_session_module.reset_endpoints()


@pytest.fixture(scope="session")
def loader():
    """全量内容加载器（session 级共享）。"""
    content_loader.reset_loader()
    kb_module.reset_kb()
    advice_module.reset_advice()
    yield content_loader.get_loader()
    content_loader.reset_loader()
    # 知识库是从加载器派生出来的，加载器换了它就必须跟着换——
    # 否则下一个用例拿到的图还是上一个加载器装配的。
    # 求教的"书 → 主题"缓存同理：它也是从加载器里读出来的。
    kb_module.reset_kb()
    advice_module.reset_advice()


@pytest.fixture(scope="session")
def index(loader):
    """全量检索索引（session 级共享）。"""
    retriever_module.reset_retriever()
    yield retriever_module.build_retriever_from_loader(loader)
    retriever_module.reset_retriever()


@pytest.fixture()
def client(index):
    """干净的 FastAPI 测试客户端。

    依赖 `index` 保证索引已就绪；`main.lifespan` 是幂等的，
    因此进入上下文不会重复建索引，但仍覆盖启动路径。
    """
    with TestClient(main.app) as test_client:
        yield test_client
