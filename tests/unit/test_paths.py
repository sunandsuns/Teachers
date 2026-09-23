"""运行时路径解析的单元测试。

为什么这些定位规则值得单独测
--------------------------------------------------------------------------
源码态与打包态的目录布局不同，解析错了不会报错、只会**静默故障**：

- 语料找不到 → 书架空空如也；
- ``.env`` 读不到 → AI 问答悄悄降级成纯检索，用户以为"模型不行"；
- 前端产物找不到 → 打开窗口是一片空白。

三种症状都不带异常，只能靠测试把规则钉住。这里用临时目录构造出一个
"程序目录 + corpus 子目录"的打包态布局来验优先级。
"""

import sys
import tempfile
from pathlib import Path

import pytest

from server import paths


@pytest.fixture
def frozen_layout(tmp_path, monkeypatch):
    """构造打包态布局：``app/人生导师.exe`` + ``app/corpus/理解笔记``。

    两个位置各放一份 ``.env``，用来验证"exe 同级优先于 corpus"。
    """
    app_dir = tmp_path / "app"
    corpus = app_dir / "corpus"
    (corpus / paths.NOTES_DIRNAME).mkdir(parents=True)
    exe = app_dir / "人生导师.exe"
    exe.write_bytes(b"")
    (app_dir / ".env").write_text("LLM_API_KEY=sk-exe\n", encoding="utf-8")
    (corpus / ".env").write_text("LLM_API_KEY=sk-corpus\n", encoding="utf-8")

    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.delenv(paths.ROOT_ENV_VAR, raising=False)
    monkeypatch.delenv(paths.ENV_FILE_VAR, raising=False)
    return app_dir, corpus


class TestResolveRoot:
    def test_explicit_env_var_wins(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom"
        (custom / paths.BOOKS_DIRNAME).mkdir(parents=True)
        monkeypatch.setenv(paths.ROOT_ENV_VAR, str(custom))

        assert paths.resolve_root() == custom.resolve()

    def test_frozen_prefers_corpus_subdir(self, frozen_layout):
        _app_dir, corpus = frozen_layout

        assert paths.resolve_root() == corpus.resolve()

    def test_frozen_falls_back_to_exe_dir(self, frozen_layout):
        """语料目录缺失时退回 exe 同级，至少让 .env 还读得到。"""
        app_dir, corpus = frozen_layout
        (corpus / paths.NOTES_DIRNAME).rmdir()

        assert paths.resolve_root() == app_dir.resolve()

    def test_source_mode_takes_repo_root(self, monkeypatch):
        monkeypatch.setattr(paths, "is_frozen", lambda: False)

        # server/paths.py 上溯两层 = 仓库根，其下应有语料目录
        assert (paths.resolve_root() / paths.NOTES_DIRNAME).is_dir()


class TestResolveEnvFile:
    def test_exe_side_env_wins_over_corpus(self, frozen_layout, monkeypatch):
        """配置文件放在程序根目录，不埋进 corpus——用户找得到才改得动。"""
        app_dir, corpus = frozen_layout
        monkeypatch.setattr(paths, "PROJECT_ROOT", corpus)

        assert paths.resolve_env_file() == (app_dir / ".env").resolve()

    def test_falls_back_to_project_root(self, frozen_layout, monkeypatch):
        app_dir, corpus = frozen_layout
        (app_dir / ".env").unlink()
        monkeypatch.setattr(paths, "PROJECT_ROOT", corpus)

        assert paths.resolve_env_file() == (corpus / ".env").resolve()

    def test_explicit_override_wins(self, frozen_layout, tmp_path, monkeypatch):
        target = tmp_path / "elsewhere.env"
        target.write_text("LLM_API_KEY=sk-x\n", encoding="utf-8")
        monkeypatch.setenv(paths.ENV_FILE_VAR, str(target))

        assert paths.resolve_env_file() == target.resolve()

    def test_returns_none_when_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "is_frozen", lambda: False)
        monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path / "nowhere")

        assert paths.resolve_env_file() is None


class TestServeFrontendToggle:
    @pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off"])
    def test_falsy_values_disable(self, value, monkeypatch):
        monkeypatch.setenv(paths.SERVE_ENV_VAR, value)

        assert paths.should_serve_frontend() is False

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
    def test_truthy_values_enable(self, value, monkeypatch):
        monkeypatch.setenv(paths.SERVE_ENV_VAR, value)

        assert paths.should_serve_frontend() is True

    def test_defaults_to_enabled(self, monkeypatch):
        monkeypatch.delenv(paths.SERVE_ENV_VAR, raising=False)

        assert paths.should_serve_frontend() is True


class TestResolveDataDir:
    """运行期数据目录（历史记录数据库的落点）。

    这也是"静默故障"的候选：目录选错或不建出来，症状是"历史记录一直空的"，
    界面上看不出任何异常。
    """

    def test_explicit_env_var_wins(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom"
        monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(custom))

        assert paths.resolve_data_dir() == custom.resolve()
        # 顺带建出来，存储层不必再管"目录在不在"
        assert custom.is_dir()

    def test_source_mode_uses_repo_root(self, monkeypatch):
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.setattr(paths, "is_frozen", lambda: False)

        assert paths.resolve_data_dir() == (paths.resolve_root() / paths.DATA_DIRNAME).resolve()

    def test_frozen_mode_sits_next_to_exe(self, frozen_layout, monkeypatch):
        """放在程序自己那一份里，好处是"拷贝即迁移"：搬走文件夹，记录跟着走。"""
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        app_dir, _corpus = frozen_layout

        assert paths.resolve_data_dir() == (app_dir / paths.DATA_DIRNAME).resolve()

    def test_falls_back_to_user_dir_when_program_dir_is_read_only(
        self, frozen_layout, monkeypatch, tmp_path
    ):
        """程序目录不可写（放进 Program Files、只读介质）时改用用户目录，
        而不是让历史记录功能直接消失。"""
        app_dir, _corpus = frozen_layout
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.setattr(paths, "_ensure_writable", lambda path: path != app_dir / paths.DATA_DIRNAME)
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

        assert paths.resolve_data_dir() == (tmp_path / "local" / paths.USER_DATA_DIRNAME).resolve()

    def test_survives_a_host_with_no_home_directory(self, tmp_path, monkeypatch):
        """没有家目录时不能抛异常——那会在启动阶段把整个应用带崩。

        真实事故：Linux 容器里既没有 ``LOCALAPPDATA``，``HOME`` 也没设，
        ``Path.home()`` 抛异常，于是 lifespan 里"碰一下历史库"那一步失败，
        服务根本起不来。历史记录只是附加项，不配拥有这种杀伤力。
        """
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setenv("HOME", "")
        monkeypatch.setattr(paths, "_ensure_writable", lambda path: False)

        def boom() -> Path:
            raise RuntimeError("Can't determine home directory")

        monkeypatch.setattr(Path, "home", staticmethod(boom))

        # 走到这里就说明没抛；落点退到临时目录，数据能不能留下另说
        assert paths._user_data_dir() == Path(tempfile.gettempdir()) / "renshengdaoshi"
        assert paths.resolve_data_dir() is not None

    def test_returns_first_candidate_when_nothing_is_writable(self, tmp_path, monkeypatch):
        """全都写不了也**不抛异常**：返回首选让存储层去报"不可用"，
        免得历史记录把书架和求教一起拖下水。"""
        monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(tmp_path / "hopeless"))
        monkeypatch.setattr(paths, "_ensure_writable", lambda path: False)

        assert paths.resolve_data_dir() == (tmp_path / "hopeless").resolve()


class TestResolveWebDist:
    def test_explicit_override_wins(self, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html></html>", encoding="utf-8")
        monkeypatch.setenv(paths.DIST_ENV_VAR, str(dist))

        assert paths.resolve_web_dist() == dist.resolve()

    def test_requires_index_html(self, tmp_path, monkeypatch):
        """只有目录不算数——没有 index.html 就点不开，等于没构建。"""
        empty = tmp_path / "dist"
        empty.mkdir()
        monkeypatch.setenv(paths.DIST_ENV_VAR, str(empty))
        monkeypatch.setattr(paths, "bundle_dir", lambda: None)

        resolved = paths.resolve_web_dist()
        assert resolved != empty.resolve()
