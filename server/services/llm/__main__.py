"""命令行工具：列出端点模型并逐个探活，打印最终会选中的模型。

用法::

    python -m server.services.llm              # 探活全部候选
    python -m server.services.llm --limit 6    # 只探前 6 个
    python -m server.services.llm --json       # 输出 JSON，便于脚本消费
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import transport
from .config import load_config
from .router import ModelRouter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="探测 LLM 端点可用模型")
    parser.add_argument("--limit", type=int, default=0, help="最多探活几个候选（0 表示不限）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--no-proxy", action="store_true", help="绕过系统代理直连")
    args = parser.parse_args(argv)

    if args.no_proxy:
        import os

        os.environ["LLM_NO_PROXY"] = "1"

    config = load_config()
    if not args.json:
        print("端点      :", config.base_url)
        print("密钥      :", ("已配置 " + config.api_key[:8] + "…") if config.api_key else "未配置")
        print("显式模型  :", config.model or "(未指定，自动挑选)")
        print("显式候选  :", ", ".join(config.candidates) or "(无)")
        print()

    if not config.enabled:
        message = "未配置 LLM_API_KEY，应用将运行在本地检索模式。"
        print(json.dumps({"enabled": False, "error": message}, ensure_ascii=False)
              if args.json else "[!] " + message)
        return 1

    router = ModelRouter(config)
    available = router.available_models(force=True)
    ordered = config.ordered_candidates(available)
    if args.limit:
        ordered = ordered[: args.limit]

    if not args.json:
        print("端点暴露 %d 个模型，按优先级取 %d 个候选：" % (len(available), len(ordered)))
        print()

    results = []
    winner = ""
    for name in ordered:
        started = time.time()
        try:
            content = transport.chat(
                config, name,
                ({"role": "user", "content": "hi"},),
                max_tokens=8, temperature=0.0, timeout=config.probe_timeout,
            )
            elapsed = time.time() - started
            ok = bool(content and content.strip())
            results.append({"model": name, "ok": ok, "seconds": round(elapsed, 2)})
            if ok and not winner:
                winner = name
            if not args.json:
                print("  %-26s %s  (%.2fs)" % (name, "可用" if ok else "返回空", elapsed))
        except transport.LLMTransportError as exc:
            elapsed = time.time() - started
            results.append({"model": name, "ok": False, "seconds": round(elapsed, 2),
                            "error": str(exc)})
            if not args.json:
                print("  %-26s 不可用  %s" % (name, exc))

    if args.json:
        print(json.dumps({
            "enabled": True,
            "base_url": config.base_url,
            "available": list(available),
            "results": results,
            "selected": winner,
        }, ensure_ascii=False, indent=2))
    else:
        print()
        if winner:
            print("=> 会自动选用：", winner)
        else:
            print("=> 所有候选均不可用，应用将降级为本地检索模式。")

    return 0 if winner else 1


if __name__ == "__main__":
    sys.exit(main())
