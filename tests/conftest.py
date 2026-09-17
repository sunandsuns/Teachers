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
from server.services import content_loader  # noqa: E402
from server.services import retriever as retriever_module  # noqa: E402
from server.services.llm import router as llm_router_module  # noqa: E402
from server.services.llm import session as llm_session_module  # noqa: E402


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
    yield content_loader.get_loader()
    content_loader.reset_loader()


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
