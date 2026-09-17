"""LLM 配置 / 提示词 / 传输 三层单元测试（全程不联网）。"""

import io
import urllib.error

import pytest

from server.services.llm import transport
from server.services.llm.config import (
    DEFAULT_BASE_URL,
    GLM_BASE_URL,
    LLMConfig,
    load_config,
    load_env_file,
)
from server.services.llm.prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
    clean_excerpt,
    local_fallback,
)
from server.services.retriever import SearchResult


def make_result(source: str, content: str) -> SearchResult:
    return SearchResult(
        book_id="01",
        book_title="易经",
        chapter_id="01",
        chapter_title="乾卦",
        content=content,
        score=0.9,
        source=source,
    )


# ── 配置层 ──────────────────────────────────────────────────────────────


class TestLoadEnvFile:
    def test_parses_pairs_comments_and_quotes(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# 注释\n"
            "LLM_BASE_URL=https://example.com/v1\n"
            'LLM_API_KEY="sk-quoted"\n'
            "\n"
            "LLM_MODEL='single-quoted'\n"
            "无等号的行\n",
            encoding="utf-8",
        )
        target: dict[str, str] = {}
        applied = load_env_file(env_file, target=target)

        assert target["LLM_BASE_URL"] == "https://example.com/v1"
        assert target["LLM_API_KEY"] == "sk-quoted"
        assert target["LLM_MODEL"] == "single-quoted"
        assert "无等号的行" not in applied

    def test_existing_env_wins(self, tmp_path):
        """真实环境变量优先级高于 .env —— 部署时才能覆盖。"""
        env_file = tmp_path / ".env"
        env_file.write_text("LLM_API_KEY=from-file\n", encoding="utf-8")
        target = {"LLM_API_KEY": "from-os"}

        load_env_file(env_file, target=target)

        assert target["LLM_API_KEY"] == "from-os"

    def test_missing_file_is_noop(self, tmp_path):
        assert load_env_file(tmp_path / "不存在", target={}) == {}


class TestLoadConfig:
    def test_reads_all_fields(self):
        config = load_config({
            "LLM_BASE_URL": "https://x/v1",
            "LLM_API_KEY": "sk-1",
            "LLM_MODEL": "m1",
            "LLM_MODEL_CANDIDATES": "a, b ,c",
            "LLM_TIMEOUT": "12",
            "LLM_MAX_TOKENS": "777",
        })
        assert config.base_url == "https://x/v1"
        assert config.api_key == "sk-1"
        assert config.model == "m1"
        assert config.candidates == ("a", "b", "c")
        assert config.timeout == 12
        assert config.max_tokens == 777
        assert config.enabled

    def test_defaults_without_api_key(self):
        config = load_config({})
        assert config.base_url == DEFAULT_BASE_URL
        assert not config.enabled

    def test_glm_fallback_for_backward_compat(self):
        """历史配置只写了 ZHIPUAI_API_KEY 时，仍应能工作（走智谱 OpenAI 兼容端点）。"""
        config = load_config({"ZHIPUAI_API_KEY": "glm-key"})
        assert config.api_key == "glm-key"
        assert config.base_url == GLM_BASE_URL

    def test_glm_fallback_is_lower_priority(self):
        config = load_config({"LLM_API_KEY": "llm-key", "ZHIPUAI_API_KEY": "glm-key"})
        assert config.api_key == "llm-key"
        assert config.base_url == DEFAULT_BASE_URL

    def test_malformed_numbers_fall_back_to_defaults(self):
        config = load_config({"LLM_TIMEOUT": "不是数字", "LLM_MAX_TOKENS": ""})
        assert config.timeout == LLMConfig().timeout
        assert config.max_tokens == LLMConfig().max_tokens

    def test_urls_are_built_from_base(self):
        config = LLMConfig(base_url="https://x/v1/")
        assert config.chat_url() == "https://x/v1/chat/completions"
        assert config.models_url() == "https://x/v1/models"


class TestOrderedCandidates:
    def test_explicit_model_comes_first(self):
        config = LLMConfig(model="chosen", candidates=("second",))
        assert config.ordered_candidates(("other",))[0] == "chosen"

    def test_available_sorted_by_preference(self):
        config = LLMConfig()
        ordered = config.ordered_candidates(
            ("llama3.1-8b", "gemini-2.5-flash", "deepseek-v4-pro-0813")
        )
        assert ordered == ("deepseek-v4-pro-0813", "gemini-2.5-flash", "llama3.1-8b")

    def test_denylist_filtered_out(self):
        """编排型 / 随机路由型模型不适合单轮问答，必须剔除。"""
        config = LLMConfig(model="kilo-auto", candidates=("openrouter-random", "ok-model"))
        assert config.ordered_candidates(()) == ("ok-model",)

    def test_deduplicates_preserving_order(self):
        config = LLMConfig(model="a", candidates=("b", "a"))
        assert config.ordered_candidates(("a", "b")) == ("a", "b")


# ── 提示词层 ────────────────────────────────────────────────────────────


class TestSystemPrompt:
    def test_prompt_structure(self):
        for section in ("你的处境", "经典怎么说", "我的分析", "建议你怎么办"):
            assert section in SYSTEM_PROMPT


class TestBuildUserPrompt:
    def test_includes_question_and_sources(self):
        prompt = build_user_prompt("如何坚持？", [make_result("《易经》· 乾卦", "天行健")])
        assert "如何坚持？" in prompt
        assert "《易经》· 乾卦" in prompt
        assert "天行健" in prompt


class TestCleanExcerpt:
    """降级回答把检索片段放进引用块，必须先清洗 Markdown 噪声。"""

    def test_strips_markdown_headings(self):
        assert clean_excerpt("### （一）君子与小人的对照\n正文内容") == "正文内容"

    def test_strips_table_rows(self):
        text = "| 项目 | 内容 |\n| --- | --- |\n| 书名 | 论语 |"
        assert clean_excerpt(text) == ""

    def test_keeps_blockquote_content_but_drops_marker(self):
        assert clean_excerpt('> "天行健，君子以自强不息。"') == '"天行健，君子以自强不息。"'

    def test_quoted_heading_is_dropped(self):
        """`> ### 标题` 这种双层结构正是嵌套错乱的来源。"""
        assert clean_excerpt("> ### 小标题") == ""

    def test_strips_emphasis_and_bullets(self):
        assert clean_excerpt("- **知足者富**就是需要得少") == "知足者富就是需要得少"

    def test_drops_separator_lines(self):
        assert clean_excerpt("正文一\n\n---\n\n正文二") == "正文一 正文二"

    def test_joins_multiple_lines_into_one_paragraph(self):
        assert clean_excerpt("第一句。\n第二句。") == "第一句。 第二句。"

    def test_truncates_with_ellipsis(self):
        result = clean_excerpt("字" * 300, limit=50)
        assert len(result) == 51
        assert result.endswith("…")

    def test_short_text_not_truncated(self):
        assert clean_excerpt("短句", limit=50) == "短句"

    def test_empty_input(self):
        assert clean_excerpt("") == ""
        assert clean_excerpt("\n\n  \n") == ""


class TestLocalFallback:
    def test_no_results_message(self):
        assert "没有找到" in local_fallback("问题", [])

    def test_results_formatted_with_source(self):
        answer = local_fallback(
            "如何坚持？", [make_result("《易经》· 乾卦", "天行健，君子以自强不息")]
        )
        assert "《易经》· 乾卦" in answer
        assert "天行健" in answer
        assert "如何坚持" in answer

    def test_error_note_included(self):
        answer = local_fallback("q", [make_result("s", "c")], error="超时")
        assert "超时" in answer

    def test_never_emits_nested_heading_quote(self):
        """回归：降级回答里不应再出现 `> #` 这种错乱引用。"""
        answer = local_fallback(
            "问题",
            [make_result("《论语》· 主题重编", "### 小标题\n> ### 内层标题\n真正的内容")],
        )
        assert "> #" not in answer
        assert "真正的内容" in answer


# ── 传输层 ──────────────────────────────────────────────────────────────


class TestExtractContent:
    def test_reads_content(self):
        data = {"choices": [{"message": {"content": "答案"}}]}
        assert transport._extract_content(data) == "答案"

    def test_falls_back_to_reasoning_content(self):
        """推理模型（如 glm 系列）正文可能在 reasoning_content 里。"""
        data = {"choices": [{"message": {"content": "", "reasoning_content": "思考"}}]}
        assert transport._extract_content(data) == "思考"

    def test_empty_when_both_blank(self):
        data = {"choices": [{"message": {"content": "   "}}]}
        assert transport._extract_content(data) == ""

    @pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": [{}]}])
    def test_raises_on_malformed_response(self, payload):
        with pytest.raises(transport.LLMTransportError):
            transport._extract_content(payload)


class TestTransportError:
    def test_5xx_is_retryable(self):
        assert transport.LLMTransportError("boom", 503).retryable

    def test_429_is_retryable(self):
        assert transport.LLMTransportError("slow down", 429).retryable

    def test_network_error_is_retryable(self):
        assert transport.LLMTransportError("timeout").retryable

    def test_4xx_is_not_retryable(self):
        """400/404 换模型也没用，应该直接放弃。"""
        assert not transport.LLMTransportError("bad", 400).retryable
        assert not transport.LLMTransportError("nope", 404).retryable


class TestDescribeHttpError:
    def _error(self, code: int, body: bytes) -> urllib.error.HTTPError:
        return urllib.error.HTTPError("http://x", code, "msg", {}, io.BytesIO(body))

    def test_extracts_upstream_message(self):
        exc = self._error(503, b'{"error":{"message":"Service unavailable"}}')
        assert "Service unavailable" in transport._describe_http_error(exc)

    def test_handles_non_json_body(self):
        exc = self._error(500, b"<html>oops</html>")
        assert "HTTP 500" in transport._describe_http_error(exc)


class TestMaxTokensRejection:
    def test_detects_conflicting_parameter(self):
        exc = transport.LLMTransportError(
            "HTTP 400：Unsupported parameter: max_tokens, use max_completion_tokens", 400
        )
        assert transport._is_max_tokens_rejection(exc)

    def test_ignores_unrelated_4xx(self):
        assert not transport._is_max_tokens_rejection(
            transport.LLMTransportError("HTTP 404：model not found", 404)
        )
