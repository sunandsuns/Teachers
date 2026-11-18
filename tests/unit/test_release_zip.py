"""发布链上的一条闸：产物里绝不能夹带数据库。

为什么值得单独测
--------------------------------------------------------------------------
"更新了个版本，账号和历史记录全没了"最直接的一条成因，就是发布包里带着一份
``data/history.db``——用户解压覆盖时 Windows 会拿它盖掉用户自己的库。

而它冒出来的方式**不需要谁犯错**：数据库默认就落在程序目录里，只要有人在产物
目录里双击一次 exe 试用，``dist/人生导师/data/`` 就长出来了，之后每一次
``build_app.py --zip`` 与 ``packaging/make_release_zip.py`` 都会把它打包进去。

两个脚本各管一段，中间还隔着"有人手动跑过 exe"这种人为步骤，所以两处都要有
守卫，也都要有用例钉住——这类静默失误只会在用户那边显形。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_product(tmp_path: Path, *, with_data: bool) -> Path:
    """造一个产物目录的骨架。``with_data`` 模拟"有人在里面跑过 exe"。"""
    app = tmp_path / "dist" / "人生导师"
    (app / "_internal").mkdir(parents=True)
    (app / "人生导师.exe").write_bytes(b"MZ")
    if with_data:
        (app / "data").mkdir()
        (app / "data" / "history.db").write_bytes(b"SQLite format 3\x00 pretend-db")
    return app


class TestBuildAppZipGuard:
    def test_data_dir_is_moved_out_before_zipping(self, tmp_path, monkeypatch):
        module = _load("_build_app", "build_app.py")
        app = _fake_product(tmp_path, with_data=True)
        monkeypatch.setattr(module, "APP_DIR", app)
        monkeypatch.setattr(module, "WORK_DIR", tmp_path / "build")

        module._retire_runtime_data()

        assert not (app / "data").exists(), "数据库必须被挪出产物，否则会随包发出去"
        moved = list((tmp_path / "build").glob("prev-packaged-data-*"))
        assert len(moved) == 1
        assert (moved[0] / "history.db").is_file(), "挪走而不是删掉，便于排查"

    def test_a_clean_product_is_left_untouched(self, tmp_path, monkeypatch):
        module = _load("_build_app", "build_app.py")
        app = _fake_product(tmp_path, with_data=False)
        monkeypatch.setattr(module, "APP_DIR", app)
        monkeypatch.setattr(module, "WORK_DIR", tmp_path / "build")

        module._retire_runtime_data()

        assert (app / "人生导师.exe").is_file()
        assert not (tmp_path / "build").exists(), "没有 data/ 时不该凭空建目录"


class TestReleaseZipGuard:
    def test_data_dir_is_moved_out(self, tmp_path, monkeypatch):
        module = _load("_make_release_zip", "packaging/make_release_zip.py")
        app = _fake_product(tmp_path, with_data=True)
        monkeypatch.setattr(module, "APP_DIR", app)
        monkeypatch.setattr(module, "ROOT", tmp_path)

        note = module.retire_runtime_data()

        assert "data" in note and "挪到" in note
        assert not (app / "data").exists()
        moved = list((tmp_path / "build").glob("prev-release-data-*"))
        assert len(moved) == 1
        assert (moved[0] / "history.db").is_file()

    def test_a_clean_product_is_reported_as_such(self, tmp_path, monkeypatch):
        module = _load("_make_release_zip", "packaging/make_release_zip.py")
        app = _fake_product(tmp_path, with_data=False)
        monkeypatch.setattr(module, "APP_DIR", app)
        monkeypatch.setattr(module, "ROOT", tmp_path)

        assert "没有 data/" in module.retire_runtime_data()
        assert not (tmp_path / "build").exists()
