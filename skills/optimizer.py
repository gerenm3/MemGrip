# optimizer.py

import asyncio
import ollama
import json
import sys
from pathlib import Path

# 兼容從外部匯入（如 from skills.optimizer import run_optimizer）
_skill_path = Path(__file__).parent.resolve()
if str(_skill_path) not in sys.path:
    sys.path.insert(0, str(_skill_path))

try:
    from skill_manager import load_skill, apply_update, save_history
    from trace_reader import build_execution_record
except ImportError:
    from .skill_manager import load_skill, apply_update, save_history
    from .trace_reader import build_execution_record

MODEL = "qwen3.6:35b-a3b"

DIMENSIONS_DEFINITION = """
五個維度定義：

1. 推論解析度 (Reasoning Resolution)
   方向範圍：direct → step_by_step → chain_of_thought
   描述：模型思考的步長，決定推導過程的顯式程度

2. 約束剛性 (Constraint Rigidity)
   方向範圍：guideline → rule → hard_schema
   描述：模型的自由度與合規性的平衡

3. 資訊信噪比 (Signal-to-Noise Ratio)
   方向範圍：minimal → balanced → rich
   描述：核心上下文與邊緣資訊的比例

4. 邊界錨定 (Boundary Anchoring)
   方向範圍：happy_path → mixed → edge_cases
   描述：典型案例與邊緣案例的比例

5. 不確定性處置 (Uncertainty Handling)
   方向範圍：aggressive → balanced → conservative
   描述：資訊不足時的行為模式
"""


def _parse_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("`", 1)[0]
    return json.loads(content.strip())


# ──────────────────────────────────────────────
# 步驟一：意圖對齊檢查
# ──────────────────────────────────────────────

async def intent_check(client, execution_record: dict) -> dict:
    """步驟一：對比任務意圖（goal）與最終實際輸出，判斷是否對齊。

    輸出格式：
    {
      "aligned": true/false,
      "gaps": ["具體哪個 constraint 沒有達到", "..."]
    }
    """
    goal = execution_record.get("goal", "")
    units = execution_record.get("units", [])

    # 直接找最後一個有 actual_output 的 unit，不過濾 status
    final_output = ""
    for unit in reversed(units):
        final_output = unit.get("actual_output", "")
        if final_output:
            break

    response = await client.chat(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": f"""
你是一個意圖對齊驗證系統。

請對比以下任務意圖與最終實際輸出，判斷模型是否正確理解了用戶意圖。

任務意圖：
{goal}

最終實際輸出：
{final_output}

請分析：
1. 最終輸出是否達到了任務意圖的核心目標？
2. 如果有差距，具體是哪些 constraint 或 success_criteria 沒有達到？

只輸出 JSON，不要有任何其他文字：
{{
  "aligned": true/false,
  "gaps": ["具體哪個 constraint 沒有達到", "..."]
}}
""".strip()
        }],
        think=False,
        options={"temperature": 0}
    )
    return _parse_json(response["message"]["content"])


# ──────────────────────────────────────────────
# 步驟二：規劃品質檢查
# ──────────────────────────────────────────────

async def planning_check(client, execution_record: dict) -> dict:
    """步驟二：分析規劃階段的品質。

    輸出格式：
    {
      "plan_quality": "整體規劃品質描述",
      "plan_gaps": ["規劃缺失", "..."],
      "failed_units": ["失敗的 unit 列表"]
    }
    """
    units = execution_record.get("units", [])

    units_json = json.dumps(units, ensure_ascii=False, indent=2)

    response = await client.chat(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": f"""
你是一個規劃品質分析系統。

請分析以下任務規劃品質：

{units_json}

請分析：
1. 每個 unit 的 planned_goal 是否清晰、可執行？
2. planned_goal 與 expected_output 是否一致？
3. 哪些 unit 執行失敗？原因可能為何？
4. 哪些 unit 的 error 欄位不為空？error 的原因可能為何？

只輸出 JSON，不要有任何其他文字：
{{
  "plan_quality": "整體規劃品質描述",
  "plan_gaps": ["規劃缺失", "..."],
  "failed_units": ["失敗的 unit 列表"]
}}
""".strip()
        }],
        think=False,
        options={"temperature": 0}
    )
    return _parse_json(response["message"]["content"])


# ──────────────────────────────────────────────
# 步驟三：執行品質檢查
# ──────────────────────────────────────────────

async def execution_check(client, execution_record: dict) -> dict:
    """步驟三：分析執行階段的品質。

    輸出格式：
    {
      "tool_usage_quality": "工具使用品質描述",
      "execution_gaps": ["執行落差", "..."],
      "missing_tools": ["缺失的工具", "..."]
    }
    """
    units = execution_record.get("units", [])

    # 只提取 agentic_loop 內容供 LLM 分析
    loop_data = []
    for unit in units:
        for step in unit.get("steps", []):
            for turn in step.get("agentic_loop", []):
                loop_data.append({
                    "unit_id": unit.get("unit_id"),
                    "step_id": step.get("step_id"),
                    "turn": turn.get("turn"),
                    "tool_called": turn.get("tool_called"),
                    "tool_result": turn.get("tool_result", "")[:500],  # 截斷避免過長
                    "output": turn.get("output", "")[:500],
                })

    response = await client.chat(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": f"""
你是一個執行品質分析系統。

請分析以下任務執行品質：

Agentic Loop 記錄：
{json.dumps(loop_data, ensure_ascii=False, indent=2)}

請分析：
1. 工具呼叫是否正確且充分？
2. 工具結果是否足以生成最終輸出？
3. 哪些步驟產生了預期外的落差？

只輸出 JSON，不要有任何其他文字：
{{
  "tool_usage_quality": "工具使用品質描述",
  "execution_gaps": ["執行落差", "..."],
  "missing_tools": ["缺失的工具", "..."]
}}
""".strip()
        }],
        think=False,
        options={"temperature": 0}
    )
    return _parse_json(response["message"]["content"])


# ──────────────────────────────────────────────
# 步驟四：映射到五個維度
# ──────────────────────────────────────────────

async def map_to_dimensions(
    client,
    intent_result: dict,
    planning_result: dict,
    execution_result: dict,
) -> dict:
    """步驟四：綜合前三個階段的診斷，映射到五個維度。

    輸出格式：
    {
      "reasoning_resolution": {"problem": "問題描述", "direction": "調整方向"},
      "constraint_rigidity": {"problem": "...", "direction": "..."},
      "signal_noise_ratio": {"problem": "...", "direction": "..."},
      "boundary_anchoring": {"problem": "...", "direction": "..."},
      "uncertainty_handling": {"problem": "...", "direction": "..."}
    }
    """
    response = await client.chat(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": f"""
你是一個 skill 維度映射系統。

以下是五個評估維度的定義：
{DIMENSIONS_DEFINITION}

以下是三個階段的診斷結果：

【階段一：意圖對齊】
{json.dumps(intent_result, ensure_ascii=False, indent=2)}

【階段二：規劃品質】
{json.dumps(planning_result, ensure_ascii=False, indent=2)}

【階段三：執行品質】
{json.dumps(execution_result, ensure_ascii=False, indent=2)}

請綜合以上診斷，將問題映射到五個維度。每個維度輸出：
- problem：這個問題在該維度上代表什麼問題
- direction：需要往哪個方向調整（例如 direct → step_by_step）

只輸出 JSON，不要有任何其他文字：
{{
  "reasoning_resolution": {{"problem": "...", "direction": "..."}},
  "constraint_rigidity": {{"problem": "...", "direction": "..."}},
  "signal_noise_ratio": {{"problem": "...", "direction": "..."}},
  "boundary_anchoring": {{"problem": "...", "direction": "..."}},
  "uncertainty_handling": {{"problem": "...", "direction": "..."}}
}}
""".strip()
        }],
        think=False,
        options={"temperature": 0}
    )
    return _parse_json(response["message"]["content"])


# ──────────────────────────────────────────────
# 步驟五：更新 skill
# ──────────────────────────────────────────────

async def update_skills(client, task_type: str, dimension_map: dict) -> dict:
    """步驟五：根據五個維度的調整方向，更新 skill 指導。

    輸出格式：
    {
      "modified_dimensions": ["被修改的維度"],
      "updated_skills": {"dimension_name": "更新後的內容"},
      "change_summary": {"dimension_name": "修改說明"}
    }
    """
    current_skills = load_skill(task_type)

    if task_type == "general":
        specificity_rule = "所有新增或修改的規則必須是通用原則，適用於所有任務類型。嚴禁包含具體的資料類型、欄位名稱或特定任務名稱；若診斷問題來自特定任務細節，應提煉為通用原則再寫入。"
    else:
        specificity_rule = f"規則可以包含 {task_type} 領域的具體指引，但仍應避免過於具體的資料欄位名稱。"

    response = await client.chat(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": f"""
你是一個 prompt 優化系統。

以下是五個維度的調整方向：
{json.dumps(dimension_map, ensure_ascii=False, indent=2)}

以下是目前的 skill 指導文件：
{json.dumps(current_skills, ensure_ascii=False, indent=2)}

請根據五個維度的調整方向，對 skill 指導文件做出最小修改。

規則：
- 只修改診斷結果中指出有問題的維度
- 保留原有結構，只在必要處增加、修改或刪除內容
- 不要重寫整份文件
- {specificity_rule}

只輸出 JSON，不要有任何其他文字：
{{
  "modified_dimensions": ["被修改的維度"],
  "updated_skills": {{
    // 只包含被修改的維度及其完整更新後內容
  }},
  "change_summary": {{
    // 每個維度的修改說明
  }}
}}
""".strip()
        }],
        think=False,
        options={"temperature": 0}
    )
    return _parse_json(response["message"]["content"])


# ──────────────────────────────────────────────
# 步驟六：驗證更新
# ──────────────────────────────────────────────

async def verify(client, update_result: dict, dimension_map: dict) -> dict:
    """步驟六：驗證更新後的 skill 是否能真正解決診斷出的問題。

    輸出格式：
    {
      "passed": true/false,
      "reason": "驗證理由"
    }
    """
    response = await client.chat(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": f"""
你是一個 skill 更新驗證系統。

以下是需要解決的維度問題：
{json.dumps(dimension_map, ensure_ascii=False, indent=2)}

以下是本次更新內容：
{json.dumps(update_result.get("updated_skills", {}), ensure_ascii=False, indent=2)}

請逐一檢查五個維度的問題是否被對應的更新妥善處理。
如果所有維度都被解決則 passed=true，否則 passed=false。

只輸出 JSON，不要有任何其他文字：
{{
  "passed": true/false,
  "reason": "驗證理由"
}}
""".strip()
        }],
        think=False,
        options={"temperature": 0}
    )
    return _parse_json(response["message"]["content"])


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

async def run_optimizer(session_id: str, task_type: str = None) -> tuple:
    """完整優化循環：依序執行六個步驟。

    verify 失敗時最多重試 2 次（重新跑 update_skills + verify）。
    只在 verify 通過後才寫入 skill_guide。
    """
    # 從 trace 組裝 execution_record
    execution_record = build_execution_record(session_id)
    if execution_record is None:
        return ({"error": f"Session '{session_id}' not found"}, None)

    # 若 task_type 為 None，從 execution_record 取得
    if task_type is None:
        task_type = execution_record.get("task_type", "global")

    client = ollama.AsyncClient()

    # ── 步驟 1-3：並行執行三個檢查 ──
    print(f"[1/6] 意圖對齊檢查...")
    print(f"[2/6] 規劃品質檢查...")
    print(f"[3/6] 執行品質檢查...")
    intent_result, planning_result, execution_result = await asyncio.gather(
        intent_check(client, execution_record),
        planning_check(client, execution_record),
        execution_check(client, execution_record),
    )
    print(f"意圖對齊：{'✓' if intent_result.get('aligned') else '✗'}")
    if intent_result.get("gaps"):
        for g in intent_result["gaps"]:
            print(f"  差距：{g}")
    print(f"規劃品質：{planning_result.get('plan_quality', 'N/A')}")
    print(f"執行品質：{execution_result.get('tool_usage_quality', 'N/A')}")

    # ── 步驟 4：映射到五個維度 ──
    print(f"[4/6] 映射到五個維度...")
    dimension_map = await map_to_dimensions(
        client, intent_result, planning_result, execution_result
    )
    print(f"映射結果：")
    for dim, info in dimension_map.items():
        print(f"  {dim}: {info.get('direction', 'N/A')}")

    # ── 步驟 5-6：更新 + 驗證（含重試） ──
    max_retries = 2
    update_result = None
    passed = False

    for attempt in range(max_retries + 1):
        print(f"\n[5/6] 更新 skill（嘗試 {attempt + 1}/{max_retries + 1}）...")
        update_result = await update_skills(client, task_type, dimension_map)
        print(f"修改維度：{update_result.get('modified_dimensions', [])}")

        print(f"[6/6] 驗證更新...")
        verify_result = await verify(client, update_result, dimension_map)
        passed = verify_result.get("passed", False)
        print(f"驗證結果：{'✓ 通過' if passed else f'✗ 失敗 — {verify_result.get("reason", "")}'}")

        if passed:
            break

        if attempt < max_retries:
            print("驗證未通過，重新執行 update_skills...")

    # ── 結果處理 ──
    if passed:
        diagnosis = dimension_map
        apply_update(task_type, update_result["updated_skills"], diagnosis)
        save_history(task_type, diagnosis, update_result)
        print(f"\nSkill 指導已更新並儲存至 skills/{task_type}/")
        return dimension_map, update_result
    else:
        print(f"\n⚠ Skill 指導未更新（驗證未通過，已重試 {max_retries} 次）")
        return dimension_map, update_result
