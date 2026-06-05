"""v2 step_planner — L2 戰術規劃.

依據 §3.3 (Planner) 定義：
- 只負責 plan_unit(unit, available_tools) -> Result(data=List[Step])
- 使用 LARGE_MODEL_NAME
- 符合 v2 logging 規範
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import config
from clients.message_builder import MessageBuilder
from core.health import log_action
from core.json_utils import parse_all_jsons
from core.prompts import STEP_PLAN_SYSTEM_PROMPT
from models.blueprints import Unit, Step, Result

logger = logging.getLogger(__name__)

# -------------- Step Plan User Prompt Extra --------------
STEP_PLAN_USER_EXTRA = """
## 輸出格式
只輸出 JSON 陣列，不要其他文字。
id：步驟編號
content：此步驟的具體目標，只描述這一步要做什麼，不包含整個單元的目標
expected_input：此步驟需要的輸入（語意描述）
expected_output：此步驟產出的結果（語意描述）
tools：使用的工具函數名稱；純推理步驟為 null
depends_on：必須先完成的步驟 id 列表
upstream_depends：從上方 ## 上游單元 中選取此步驟真正需要的純數字 unit id（如 [1, 2]），禁止使用 "unit:X" 等標記格式；不需要則填 []
output_type：INTERNAL / GLOBAL。被後續步驟依賴的為 INTERNAL；作為此單元最終輸出的為 GLOBAL。至少一個 GLOBAL。
[
  {{
    "id": 1,
    "content": "步驟描述",
    "expected_input": "輸入描述",
    "expected_output": "輸出描述",
    "tools": "tool_function_name 或 null",
    "depends_on": [],
    "upstream_depends": [],
    "output_type": "INTERNAL"
  }}
]"""


class StepPlanner:
    """L2 戰術規劃器：為單一 Unit 規劃 Steps"""

    def __init__(self, call_model_func: Any) -> None:
        self.call_model_func = call_model_func
        if not callable(call_model_func):
            raise TypeError("call_model_func must be callable")

    async def plan_unit(
        self,
        unit: Unit,
        available_tools: List[Dict],
        successful_steps: Optional[List[Step]] = None,
        failed_step_info: Optional[dict] = None,
        skill_guide: str = "",
        upstream_units: str = "無",
    ) -> Result:
        """為單一 Unit 規劃 Steps.

        Args:
            unit: 要規劃的 Unit
            available_tools: 可用的 tool schema 列表
            successful_steps: 已成功的步驟（replan 時用）
            failed_step_info: 失敗步驟資訊（replan 時用）
            skill_guide: Skill Guide 文字，注入 system prompt
            upstream_units: 上游單元資訊（格式：unit:{id} → {expected_output}）

        Returns:
            Result(data=List[Step])
        """
        slim_tools, tool_map = self._extract_function_tools(available_tools)
        tool_names = [t["name"] for t in slim_tools]
        tool_info = "\n".join(f"- {n}" for n in tool_names) if tool_names else "無"

        # System prompt (fixed) — only role + skill_guide + rules
        role = config.BASE_ROLES.get("step_plan", "")
        system_prompt = STEP_PLAN_SYSTEM_PROMPT.format(role=role, skill_guide=skill_guide)

        # User message (dynamic) — task data + output format
        unit_info = self._build_input(unit, successful_steps, failed_step_info)
        user_message = f"## 可用工具\n{tool_info}\n\n## 上游單元\n{upstream_units}\n\n## 當前單元\n{unit_info}"
        user_message += "\n\n" + STEP_PLAN_USER_EXTRA

        messages = MessageBuilder.build_task(system_prompt, user_message)

        try:
            result = await asyncio.wait_for(
                self.call_model_func(
                    config.MODEL_LARGE,
                    messages,
                    config.STEP_TEMPERATURE,
                    config.STEP_MAX_TOKENS,
                    config.STEP_THINK,
                    caller="step_planner",
                ),
                timeout=config.LLM_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("[StepPlanner] LLM call timed out (%ds)", config.LLM_TIMEOUT)
            log_action("step_planner", "llm_timeout", "FAILED", f"timeout={config.LLM_TIMEOUT}s", "L2 規劃逾時")
            return Result(success=False, error=f"LLM 呼叫逾時 ({config.LLM_TIMEOUT}s)")
        except Exception as e:
            logger.error("[StepPlanner] LLM call failed: %s", e, exc_info=True)
            log_action("step_planner", "llm_call_failed", "FAILED", str(e), "L2 規劃失敗")
            return Result(success=False, error=str(e))

        content = result.data or ""
        steps_data = parse_all_jsons(content)
        if not steps_data:
            log_action("step_planner", "plan_unit_parse_empty", "FAILED",
                       f"unit_id={unit.unit_id}, content_length={len(content)}",
                       "L2 步驟解析失敗")
            return Result(success=False, error="步驟規劃結果為空")

        if len(steps_data) == 1 and isinstance(steps_data[0], list):
            steps_data = steps_data[0]

        steps = self._parse_steps(steps_data, tool_map)
        log_action("step_planner", "plan_success", "OK",
                   f"unit_id={unit.unit_id}, steps={len(steps)}")
        return Result(success=True, data=steps)

    @staticmethod
    def _build_input(
        unit: Unit,
        successful_steps: Optional[List[Step]] = None,
        failed_step_info: Optional[dict] = None,
    ) -> str:
        """建構步驟規劃的輸入文字"""
        input_parts = [
            f"單元目標：{unit.goal}",
            f"預期輸入：{unit.expected_input}",
            f"預期輸出：{unit.expected_output}",
        ]
        if successful_steps:
            input_parts.append(
                "\n已成功步驟：\n" + "\n".join(f"  step_id={s.step_id}: {s.goal}" for s in successful_steps)
            )
        if failed_step_info:
            input_parts.append(
                "\n前次失敗步驟：\n"
                + f"  step_id={failed_step_info.get('step_id', '')}\n"
                + f"  goal: {failed_step_info.get('goal', '')}\n"
                + f"  content: {failed_step_info.get('content', '')}"
            )
            # 注入 Verifier 的 gaps (具體差距清單)
            gaps = failed_step_info.get("gaps", [])
            if gaps:
                input_parts.append(
                    "\n驗證差距：\n" + "\n".join(f"  - {g}" for g in gaps)
                )
            # 注入 Verifier 的 constraint_checks (逐條約束驗證結果)
            checks = failed_step_info.get("constraint_checks", [])
            if checks:
                input_parts.append(
                    "\n約束檢查結果：\n" + "\n".join(f"  - {c}" for c in checks)
                )
        return "\n".join(input_parts)

    @staticmethod
    def _extract_function_tools(tools_list: List[Dict]) -> tuple:
        """從 tools_list 中篩選出 function 類型的工具."""
        slim_tools = []
        tool_map = {}
        for t in tools_list:
            if t.get("type") != "function":
                continue
            func = t.get("function")
            if not isinstance(func, dict):
                continue
            name = func.get("name")
            if not name:
                continue
            slim_tools.append({
                "name": name,
                "description": func.get("description", ""),
            })
            if name in tool_map:
                logger.warning("[StepPlanner] 重複 tool name 被覆蓋: %s", name)
            tool_map[name] = t
        return slim_tools, tool_map

    @staticmethod
    def _parse_steps(steps_data: List, tool_map: Dict[str, Dict]) -> List[Step]:
        """將 JSON 資料解析為 Step 列表"""
        steps: List[Step] = []
        for s in steps_data:
            if not isinstance(s, dict):
                continue
            tool_name = s.get("tools")
            tool = tool_map.get(tool_name) if tool_name else None
            if tool_name and tool is None:
                logger.warning(
                    "[StepPlanner] LLM 使用了未註冊的工具: %s (step_id=%s)",
                    tool_name, s.get("id", "?")
                )
                log_action("step_planner", "parse_steps_unknown_tool", "DEGRADED",
                           f"tool={tool_name}, step_id={s.get('id', '?')}",
                           "LLM 使用未註冊工具")
            # 解析 depends_on: 確保每個元素為 str
            raw_deps = s.get("depends_on", [])
            depends_on = [str(d) for d in raw_deps]

            # 解析 upstream_depends: 去除 "unit:" 前綴，只保留純 unit id
            raw_upstream = s.get("upstream_depends", [])
            upstream_depends = []
            for ud in raw_upstream:
                ud_str = str(ud)
                if ud_str.startswith("unit:"):
                    ud_str = ud_str[5:]
                upstream_depends.append(ud_str)

            steps.append(Step(
                step_id=str(s.get("id", "")),
                goal=s.get("content", ""),
                tool=tool,
                depends_on=depends_on,
                upstream_depends=upstream_depends,
                output_type=s.get("output_type", "INTERNAL"),
            ))
        return steps