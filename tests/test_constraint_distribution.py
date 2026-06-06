"""測試 constraint 分配穩定性。

執行 3 次 disassemble，觀察同一組 clarify_data 下
每個 unit 的 assigned_constraints 是否一致。
"""

import asyncio
import sys
from pathlib import Path

# 加入專案根目錄到 sys.path（直接執行時需要）
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from bootstrap import build_orchestrator


async def test():
    orchestrator = await build_orchestrator()

    clarify_data = {
        "goal": "讀取 HISTORY.md 提取 CVE 記錄，讀取 AUTHORS.rst 找出核心維護者（包含之前的），整理成 security_audit.md",
        "constraints": ["包含之前的核心維護者", "按時間倒序排列"],
        "entities": [],
        "scope": "",
        "success_criteria": []
    }

    # 執行 3 次，觀察 constraint 分配穩定性
    for i in range(3):
        result = await orchestrator.disassembler.disassemble(
            clarify_result=clarify_data,
            available_servers=["filesystem", "fetch", "brave-search"],
            skill_guide=""
        )

        print(f"\n=== 第 {i+1} 次 ===")
        if result.success:
            units = result.data or []
            for unit in units:
                print(f"Unit {unit.unit_id}: goal={unit.goal}, depends_on={unit.depends_on}, mcp_server={unit.mcp_server}, output_type={unit.output_type}, constraints={unit.assigned_constraints}")
        else:
            print(f"ERROR: {result.error}")


if __name__ == "__main__":
    asyncio.run(test())