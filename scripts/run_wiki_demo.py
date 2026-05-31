"""手动验收：用真实 LLM 对 astrbot 的一个子包跑 Wiki 生成子图。

用法：uv run python scripts/run_wiki_demo.py
"""

import asyncio
import time
from pathlib import Path

from asukabot.config import get_settings
from asukabot.core.graph.wiki import build_wiki_graph

TARGET = "ref/normal_agent/astrbot/astrbot/core/pipeline"


async def main() -> None:
    settings = get_settings()
    graph = build_wiki_graph()
    project_name = "astrbot_pipeline"
    print(f"目标: {TARGET}  模型: {settings.default_model}")
    t0 = time.monotonic()
    result = await graph.ainvoke(
        {
            "project_path": TARGET,
            "project_name": project_name,
            "language": "chinese",
            "output_dir": settings.wiki_output_dir,
            "max_abstractions": 6,
        }
    )
    dt = time.monotonic() - t0
    out = Path(result["final_output_dir"])
    print(f"\n用时 {dt:.1f}s  输出目录: {out}")
    print(f"识别抽象数: {len(result['abstractions'])}")
    for a in result["abstractions"]:
        print(f"  - {a['name']}: {a['description'][:40]}...")
    print(f"章节数: {len(result['chapters'])}")
    print("生成文件:")
    for f in sorted(out.glob("*.md")):
        print(f"  {f.name}  ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
