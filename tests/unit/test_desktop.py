"""桌面窗口入口的单元测试。

为什么只测这几个函数
--------------------------------------------------------------------------
``main`` 要拉起 GUI、真实监听端口，没法在测试里跑。但**白屏兜底**那条分支
恰恰是拿到包的人最容易踩的坑：WebView2 的浏览器进程崩掉之后，``load_url``
一声不吭地"成功"了，用户对着一个永远停在"正在编索引"的空窗口——而使用说明
里承诺过这种情况会自动改用系统浏览器。这条判断必须钉住。

验证方式是给它一个假窗口：内核正常时不该弹任何东西，内核死了才该开浏览器。
"""

import pytest

import desktop


class FakeWindow:
    """只实现被调用到的那几个方法，顺便记录调用轨迹。"""

    def __init__(self, *, evaluate_error: Exception | None = None,
                 load_error: Exception | None = None):
        self.calls: list[tuple] = []
        self._evaluate_error = evaluate_error
        self._load_error = load_error

    def load_url(self, url: str) -> None:
        self.calls.append(("load_url", url))
        if self._load_error is not None:
            raise self._load_error

    def load_html(self, html: str) -> None:
        self.calls.append(("load_html",))

    def evaluate_js(self, script: str):
        self.calls.append(("evaluate_js", script))
        if self._evaluate_error is not None:
            raise self._evaluate_error
        return 1


URL = "http://127.0.0.1:8760/"


@pytest.fixture(autouse=True)
def fast_paths(monkeypatch):
    """把探针重试压成瞬时，并假装索引已就绪。"""
    monkeypatch.setattr(desktop, "PROBE_ATTEMPTS", 2)
    monkeypatch.setattr(desktop, "PROBE_INTERVAL", 0.0)
    monkeypatch.setattr(desktop, "_wait_ready", lambda port, timeout=None: True)


@pytest.fixture
def fallback_record(monkeypatch):
    """记录「改用系统浏览器」的动作，但不真的开浏览器、不真的弹框。"""
    record: list[str] = []
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: record.append(url))
    monkeypatch.setattr(desktop, "_notify", lambda message, **kwargs: record.append(message))
    return record


def test_healthy_window_stays_native(fallback_record):
    """内核活着：载入页面 + 探针通过，不该有任何兜底动作。"""
    window = FakeWindow()
    desktop._boot(window, 8760, URL)
    assert window.calls == [("load_url", URL), ("evaluate_js", "1")]
    assert fallback_record == []


def test_dead_core_falls_back_to_browser(fallback_record):
    """核心场景：``load_url`` 不报错，但内核其实已经崩了。

    这就是"网页一片空白"的真身——异常没抛，窗口看着正常，只能靠探针发现。
    """
    window = FakeWindow(evaluate_error=RuntimeError("CoreWebView2 is no longer valid"))
    desktop._boot(window, 8760, URL)
    assert fallback_record[0] == URL
    assert any("改用你的默认浏览器" in item for item in fallback_record if isinstance(item, str))


def test_load_url_failure_falls_back_to_browser(fallback_record):
    """连窗口都没建起来（缺 WebView2 运行时）：同样退到浏览器。"""
    window = FakeWindow(load_error=RuntimeError("WebView2 runtime not found"))
    desktop._boot(window, 8760, URL)
    assert fallback_record[0] == URL


def test_server_not_ready_shows_failure_page(fallback_record, monkeypatch):
    """服务没起来：给一张"没能启动"的页面，而不是白屏，更不该误开浏览器。"""
    monkeypatch.setattr(desktop, "_wait_ready", lambda port, timeout=None: False)
    window = FakeWindow()
    desktop._boot(window, 8760, URL)
    assert window.calls == [("load_html",)]
    assert fallback_record == []


def test_probe_tolerates_transient_failure():
    """只要成功过一次就算活着。

    页面还在渲染时求值会抛错，那是正常现象；判成"内核已死"会让本该有窗口的
    用户被莫名其妙地丢进浏览器，所以只有**次次都抛**才判定为死。
    """
    attempts: list[str] = []

    class FlakyWindow:
        def evaluate_js(self, script: str):
            attempts.append(script)
            if len(attempts) == 1:
                raise RuntimeError("还在渲染")
            return 1

    assert desktop._probe_window(FlakyWindow()) is True
    assert len(attempts) == 2


def test_probe_gives_up_after_all_attempts():
    """次次都抛：判定为死，且不多试一次。"""
    attempts: list[str] = []

    class DeadWindow:
        def evaluate_js(self, script: str):
            attempts.append(script)
            raise RuntimeError("CoreWebView2 is no longer valid")

    assert desktop._probe_window(DeadWindow()) is False
    assert len(attempts) == desktop.PROBE_ATTEMPTS
