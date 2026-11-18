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

import os
import sqlite3
import sys
import tempfile
import time
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
    # 用户级兜底目录锁进临时目录：不然测"程序目录不可写"那一支时会真的去写
    # 本机的 %LOCALAPPDATA%\人生导师。
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.delenv("APPDATA", raising=False)
    return app_dir, corpus


def _write_database(path: Path, table: str = "history") -> None:
    """造一个**真的** SQLite 文件。

    接续那一步会看文件头来确认"这确实是个库"，随手写几个字节骗不过去——
    而"认错了把别人家的文件拷进用户的库"正是这一步最坏的失败方式。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS %s (id INTEGER)" % table)


@pytest.fixture
def upgrade_layout(tmp_path, monkeypatch):
    """搭一个"升级"现场：新旧两个版本文件夹是同一层的兄弟。

    ::

        临时目录/
          root/
            v1/人生导师/data/history.db   ← 上一版本留下的记录
            v2/app/人生导师.exe           ← 这次解压出来的新版本

    程序故意埋到两层之下，是为了让"往上找两级"只扫到这套自造的目录——
    pytest 在别处还放着同批次的临时目录，不能顺手摸到它们。
    """
    root = tmp_path / "root"
    old_db = root / "v1" / paths.USER_DATA_DIRNAME / paths.DATA_DIRNAME / paths.DB_FILENAME
    _write_database(old_db)

    app_dir = root / "v2" / "app"
    (app_dir / "corpus" / paths.NOTES_DIRNAME).mkdir(parents=True)
    exe = app_dir / "人生导师.exe"
    exe.write_bytes(b"")

    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
    monkeypatch.delenv(paths.ROOT_ENV_VAR, raising=False)
    monkeypatch.delenv(paths.ENV_FILE_VAR, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(paths, "LAST_ADOPTION", None)
    return app_dir, old_db


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
        # 开发机上不该冒出 /data 这个候选；显式关掉它，免得用例跟着平台变
        monkeypatch.setattr(paths, "deploy_data_dir", lambda: None)

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

    def test_survives_a_host_with_home_but_no_localappdata(self, tmp_path, monkeypatch):
        """有家目录、但没有 ``LOCALAPPDATA`` 的机器上同样不能抛异常。

        这条比"无家目录"那条更阴，因为它**看起来**一切正常：家目录取得到，
        不会走那条兜底分支，于是异常落在中间那行上。真实事故是少写了一对
        括号——``/`` 的优先级高于 ``+``，``Path.home() / "." + "renshengdaoshi"``
        被解析成 ``(Path.home() / ".") + "renshengdaoshi"``，``Path + str`` 抛
        ``TypeError``。它不是 ``OSError`` 的子类，逃过了当时的 except。

        后果是线上**所有碰数据库的接口**（回响、画像）整片 500，只有不碰库的
        页面还活着；而本地永远复现不出来——Windows 上 ``LOCALAPPDATA`` 有值，
        函数第一行就返回了，那一行根本没被执行过。本用例删掉这两个变量把它
        逼出来。
        """
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setattr(paths, "_ensure_writable", lambda path: False)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

        # 走到这里就说明没抛；落点是家目录下的隐藏目录
        assert paths._user_data_dir() == tmp_path / ".renshengdaoshi"
        assert paths.resolve_data_dir() is not None


class TestAdoptPreviousDatabase:
    """换一个新版本文件夹，不该等于换一个空库。

    用户的原话是"每次我更新版本数据库就没了"：桌面版的升级就是解压出一个新夹子，
    而库在程序自己那份目录里。旧库就在隔壁，这里把它接过来。
    """

    def test_new_version_folder_picks_up_the_previous_records(self, upgrade_layout):
        app_dir, old_db = upgrade_layout

        assert paths.resolve_data_dir() == (app_dir / paths.DATA_DIRNAME).resolve()

        adopted = app_dir / paths.DATA_DIRNAME / paths.DB_FILENAME
        assert adopted.is_file()
        assert adopted.read_bytes() == old_db.read_bytes()
        # 只拷贝、不搬走：旧的那份原地留着，用户想回头还找得到
        assert old_db.is_file()
        # 这件事必须能被启动日志念出来（见 server/main.py）
        assert paths.LAST_ADOPTION == (
            str(old_db), str(app_dir / paths.DATA_DIRNAME))

    def test_an_existing_database_is_left_alone(self, upgrade_layout):
        """原地覆盖升级、整包拷贝过来的副本：自带的那份说了算。

        说明书向用户承诺过"把整个文件夹拷走，data 跟着走"，所以绝不能因为
        附近还有一份更旧的库就把用户手里这份换掉。
        """
        app_dir, old_db = upgrade_layout
        mine = app_dir / paths.DATA_DIRNAME
        mine.mkdir(parents=True)
        marker = b"SQLite format 3\x00" + b"mine" * 40
        (mine / paths.DB_FILENAME).write_bytes(marker)

        assert paths.resolve_data_dir() == mine.resolve()
        assert (mine / paths.DB_FILENAME).read_bytes() == marker
        assert paths.LAST_ADOPTION is None

    def test_a_lookalike_file_is_not_treated_as_our_database(self, upgrade_layout):
        """邻居那个文件也叫 history.db，但不是 SQLite——不能认。

        认错的代价是把不相干的数据灌进用户的库，比"没接上"严重得多。
        """
        app_dir, old_db = upgrade_layout
        old_db.write_bytes("这个文件只是恰好叫 history.db 而已，不是数据库".encode("utf-8") * 8)

        paths.resolve_data_dir()

        assert not (app_dir / paths.DATA_DIRNAME / paths.DB_FILENAME).exists()
        assert paths.LAST_ADOPTION is None

    def test_the_most_recent_database_wins(self, upgrade_layout):
        """相邻有好几份时取最新的那一份——旧版本文件夹通常不止一个。"""
        app_dir, old_db = upgrade_layout
        newer = old_db.parent.parent.parent / "v0" / paths.USER_DATA_DIRNAME / paths.DATA_DIRNAME
        newer_db = newer / paths.DB_FILENAME
        _write_database(newer_db)
        # 显式把时间戳拉开，免得两秒内的文件系统精度让结果碰运气
        later = time.time() + 60
        os.utime(newer_db, (later, later))

        paths.resolve_data_dir()

        assert paths.LAST_ADOPTION is not None
        assert paths.LAST_ADOPTION[0] == str(newer_db)
        assert (app_dir / paths.DATA_DIRNAME / paths.DB_FILENAME).read_bytes() == newer_db.read_bytes()

    def test_explicit_data_dir_is_never_surprised(self, upgrade_layout, tmp_path, monkeypatch):
        """用户明确指定了数据目录，就别自作主张往里灌旧数据。"""
        chosen = tmp_path / "chosen"
        monkeypatch.setenv(paths.DATA_DIR_ENV_VAR, str(chosen))

        assert paths.resolve_data_dir() == chosen.resolve()
        assert not (chosen / paths.DB_FILENAME).exists()
        assert paths.LAST_ADOPTION is None


class TestDeployDataDir:
    """线上（部署态）的数据目录必须落在项目外面。

    "项目里的 data/" 会被下一次发布上传上去覆盖掉，线上注册的账号就跟着没了。
    以前这条靠"发布时记得带 RSDS_DATA_DIR=/data"，漏一次就复现；现在它是代码默认，
    流程纪律不再是唯一防线。
    """

    def test_deploy_container_keeps_the_database_out_of_the_project(self, tmp_path, monkeypatch):
        outside = tmp_path / "outside"
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.setattr(paths, "is_frozen", lambda: False)
        monkeypatch.setattr(paths, "deploy_data_dir", lambda: outside)

        resolved = paths.resolve_data_dir()

        assert resolved == outside.resolve()
        assert resolved != (paths.resolve_root() / paths.DATA_DIRNAME).resolve()

    def test_falls_through_when_the_deploy_dir_cannot_be_created(self, tmp_path, monkeypatch):
        """建不出 /data 的机器（普通 Linux 开发机）不能被它卡住，要退到项目目录。"""
        blocked = tmp_path / "nope"
        monkeypatch.delenv(paths.DATA_DIR_ENV_VAR, raising=False)
        monkeypatch.setattr(paths, "is_frozen", lambda: False)
        monkeypatch.setattr(paths, "deploy_data_dir", lambda: blocked)
        monkeypatch.setattr(paths, "_ensure_writable", lambda path: path != blocked)

        assert paths.resolve_data_dir() == (paths.resolve_root() / paths.DATA_DIRNAME).resolve()

    def test_windows_never_uses_the_deploy_dir(self):
        """Windows 下 ``Path("/data")`` 会落到当前盘符根目录——本地开发被它劫持
        是纯粹的坏事，而容器是 Linux，这个闸门不会误伤线上。"""
        if os.name == "nt":
            assert paths.deploy_data_dir() is None
        else:
            assert paths.deploy_data_dir() == Path(paths.DEPLOY_DATA_DIR)


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
