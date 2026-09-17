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
