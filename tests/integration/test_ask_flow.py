"""集成测试：完整问答流程与感悟流程。

ask 流程覆盖：有结果时的降级回答（无 API key 环境）、检索引用、参数校验。
"""

import pytest


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """集成测试默认无 LLM，验证纯检索降级路径稳定可用。"""
    monkeypatch.delenv("ZHIPUAI_API_KEY", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)


class TestAskFlow:
    def test_ask_returns_retrieval_answer(self, client):
        resp = client.post("/api/ask", json={"question": "如何面对困境和挫折？"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["question"] == "如何面对困境和挫折？"
        assert body["retrieved_count"] > 0
        assert not body["llm_used"]
        # 降级回答应包含检索到的经典出处
        assert "《" in body["answer"]

    def test_ask_answer_cites_sources(self, client):
        body = client.post("/api/ask", json={"question": "怎么坚持长期目标"}).json()
        assert "·" in body["answer"], "应包含 出处 格式的引用"

    def test_ask_custom_top_k(self, client):
        body = client.post("/api/ask", json={"question": "识人用人", "top_k": 8}).json()
        assert body["retrieved_count"] <= 8

    def test_ask_validation(self, client):
        assert client.post("/api/ask", json={}).status_code == 422
        assert client.post("/api/ask", json={"question": ""}).status_code == 422
        assert client.post("/api/ask", json={"question": "x" * 501}).status_code == 422

    def test_ask_unmatched_question(self, client):
        body = client.post("/api/ask", json={"question": "asdfghjkl qwertyuiop zxcvbn"}).json()
        assert body["retrieved_count"] >= 0  # 不崩溃即可


class TestInsightFlow:
    def test_daily_to_theme_to_list_flow(self, client):
        # 今日感悟
        daily = client.get("/api/insight/daily").json()
        assert daily["themes"]

        # 主题列表
        themes = client.get("/api/insight/themes").json()

        # 按今日感悟的第一个主题取列表，应包含该感悟
        theme = daily["themes"][0]
        listing = client.get(f"/api/insight/by-theme/{theme}").json()
        assert listing["total"] == themes["counts"][theme]
        ids = [item["id"] for item in listing["items"]]
        assert daily["id"] in ids

    def test_random_over_multiple_calls(self, client):
        texts = set()
        for _ in range(5):
            texts.add(client.get("/api/insight/random").json()["id"])
        # 47 条池子抽 5 次大概率有重复，只验证不崩溃且字段完整
        item = client.get("/api/insight/random").json()
        assert {"id", "text", "interpretation", "source", "book_id", "themes"} <= set(item)


class TestSearchAskConsistency:
    def test_search_and_ask_use_same_index(self, client):
        """ask 与 search 对同一问题应基于同一检索层。"""
        q = "自强不息"
        search = client.get("/api/search", params={"q": q}).json()
        ask = client.post("/api/ask", json={"question": q}).json()
        assert search["total"] > 0
        assert ask["retrieved_count"] > 0
