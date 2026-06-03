"""v2 disassembler — L1 戰略拆解.

依據 §3.3 (Planner) 定義：
- 只負責 disassemble(clarify_result: dict) -> Result(data=List[Unit])
- 使用 LARGE_MODEL_NAME
- 將 clarify_result 的 success_criteria 轉化為每個 Unit 的 expected_output
- 符合 v2 logging 規範
"""

import asyncio
import logging
import re
from typing import Any, Awaitable, Callable, List, Optional

import config
from clients.message_builder import MessageBuilder
from core.health import log_action
from core.json_utils import parse_first_json
from core.prompts import DISASSEMBLY_SYSTEM_PROMPT
from models.blueprints import Unit, Result

def _build_role(role_key: str, task_role: str = None) -> str:
    """組合 BASE_ROLE 與 task_role（目前 task_role 傳 None）"""
    role = config.BASE_ROLES.get(role_key, "")
    if task_role:
        role += f"\n{task_role}"
    return role

logger = logging.getLogger(__name__)


DISASSEMBLY_USER_EXTRA = """
## Constraints 分配
以下為本次任務的 constraints 清單：
{constraints_list}

 分配規則：
- 在規劃每個 unit 時，從上方 constraints 清單中選出與此 unit 職責語意相關的條目
- Local constraint（執行時需主動滿足）：分配給執行該操作的 unit
- Global constraint（跨 unit 的整體要求）：分配給最終整合輸出的 unit
- 一條 constraint 可以分配給多個 unit
- 只從清單中選取原文，不自創名稱
- 與所有 constraints 無關的 unit，assigned_constraints 可為空

## 輸出格式
必須輸出合法的 JSON 陣列，以 [ 開頭，以 ] 結尾。禁止輸出 markdown code block。
id：單元編號
content：目標、對象；不得包含工具名稱；引用其他單元輸出時用「上游的 XXX」描述，禁止使用 <unit:X> 標記
expected_input：此單元需要的輸入（語意描述）
expected_output：此單元產出的結果（語意描述）
mcp_server：使用的 MCP Server 名稱；無需工具則為 null
depends_on：必須先完成的單元 id 列表（純數字，如 [1, 2]，禁止使用 <unit:X> 等標記格式）
output_type：INTERNAL / CONTENT / ACTION
  - INTERNAL：輸出只供下游單元使用
  - CONTENT：任務明確要求將結果直接呈現給用戶
  - ACTION：對外部環境的寫入或發送操作，不包含讀取
assigned_constraints：分配給此單元的 constraints 清單（字串陣列，從上方 Constraints 中選取相關的）
[
  {{
    "id": 1,
    "content": "單元描述",
    "expected_input": "輸入描述",
    "expected_output": "輸出描述",
    "mcp_server": "server_name 或 null",
    "depends_on": [],
    "output_type": "INTERNAL",
    "assigned_constraints": []
  }}
]"""


class Disassembler:
    """L1 戰略拆解器：將 clarify 結果拆成 Units"""

    def __init__(self, call_model_func: Callable[..., Awaitable[Result]]) -> None:
        self.call_model_func = call_model_func
        if not callable(call_model_func):
            raise TypeError("call_model_func must be callable")

    async def disassemble(
        self,
        clarify_result: dict,
        available_servers: Optional[List[str]] = None,
        skill_guide: str = "",
        feedback: str = "",
    ) -> Result:
        """將 clarify 結果拆解為 Unit 列表.

        Args:
            clarify_result: Clarifier 回傳的結構化 dict
            available_servers: 可用的 MCP Server 名稱列表
            skill_guide: Skill Guide 文字
            feedback: 上次規劃的驗證錯誤回饋，供 LLM 修正

        Returns:
            Result(data=List[Unit])
        """
        goal = clarify_result.get("goal", "")
        entities = clarify_result.get("entities", [])
        scope = clarify_result.get("scope", "")
        constraints = clarify_result.get("constraints", [])
        success_criteria = clarify_result.get("success_criteria", [])

        # System prompt (fixed) — only role + skill_guide + rules
        role = _build_role("disassembly")
        system_prompt = DISASSEMBLY_SYSTEM_PROMPT.format(
            role=role, skill_guide=skill_guide
        )

        # User message (dynamic) — task data + constraints assignment + output format
        server_info = ", ".join(available_servers) if available_servers else "無"
        user_message = f"## 可用 MCP Server\n{server_info}\n\n## 任務\n"
        user_message += self._build_input(goal, entities, scope, constraints, success_criteria)

        # Constraints assignment + output format moved to user prompt
        constraints_list = "\n".join(f"- {c}" for c in constraints) if constraints else "（無 constraints）"
        user_message += "\n\n" + DISASSEMBLY_USER_EXTRA.format(constraints_list=constraints_list)

        if feedback:
            user_message += f"\n\n## 上次規劃驗證失敗，請修正以下問題\n{feedback}"

        messages = MessageBuilder.build_task(system_prompt, user_message)

        try:
            result = await asyncio.wait_for(
                self.call_model_func(
                    config.LARGE_MODEL_NAME,
                    messages,
                    config.DISASSEMBLY_TEMPERATURE,
                    config.DISASSEMBLY_MAX_TOKENS,
                    config.DISASSEMBLY_THINK,
                    caller="disassembler",
                ),
                timeout=config.LLM_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("[Disassembler] LLM call timed out (%ds)", config.LLM_TIMEOUT)
            log_action("disassembler", "llm_timeout", "FAILED", f"timeout={config.LLM_TIMEOUT}s", "L1 拆解逾時")
            return Result(success=False, error=f"LLM 呼叫逾時 ({config.LLM_TIMEOUT}s)")
        except Exception as e:
            logger.error("[Disassembler] LLM call failed: %s", e, exc_info=True)
            log_action("disassembler", "llm_call_failed", "FAILED", str(e), "L1 拆解失敗")
            return Result(success=False, error=str(e))

        content = result.data or ""
        units = self._parse_units(content)
        if not units:
            log_action("disassembler", "disassemble_parse_empty", "FAILED",
                       "content parsed to empty", "任務解析失敗")
            logger.warning("[Disassembler] 解析結果為空")
            return Result(success=False, error="任務拆解結果為空")

        log_action("disassembler", "disassemble_success", "OK", str(len(units)))
        return Result(success=True, data=units)

    @staticmethod
    def _build_input(
        goal: str,
        entities: List[str],
        scope: str,
        constraints: List[str],
        success_criteria: Any,
    ) -> str:
        """建構拆解任務的輸入文字
        
        Note: success_criteria 可能為 str 或 List[str]，需兼容兩種型別。
        """
        # Handle entities
        if entities:
            entities_str = ', '.join(entities)
        else:
            entities_str = '無'
        
        # Handle constraints
        if constraints:
            constraints_str = ', '.join(constraints)
        else:
            constraints_str = '無'
        
        # Handle success_criteria (fix: may be str or List[str])
        if isinstance(success_criteria, str):
            sc_str = success_criteria
        elif isinstance(success_criteria, list) and len(success_criteria) > 0:
            sc_str = ', '.join(success_criteria)
        else:
            sc_str = '無'
        
        input_parts = [
            f"[GOAL]{goal}[/GOAL]",
            f"[ENTITIES]{entities_str}[/ENTITIES]",
            f"[SCOPE]{scope}[/SCOPE]",
            f"[CONSTRAINTS]{constraints_str}[/CONSTRAINTS]",
            f"[SUCCESS_CRITERIA]{sc_str}[/SUCCESS_CRITERIA]",
        ]
        return "\n".join(input_parts)

    @staticmethod
    def _parse_units(content: str) -> List[Unit]:
        """將 JSON 文字解析為 Unit 列表"""
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if not match:
            return []
        units_data = parse_first_json(match.group())
        if not isinstance(units_data, list):
            return []
        result: List[Unit] = []
        for u in units_data:
            if not isinstance(u, dict):
                continue
            raw_id = u.get("id")
            unit_id = str(raw_id) if raw_id is not None else ""
            result.append(Unit(
                unit_id=unit_id,
                goal=u.get("content", ""),
                expected_input=u.get("expected_input", ""),
                expected_output=u.get("expected_output", ""),
                depends_on=[str(x) for x in u.get("depends_on", [])],
                mcp_server=u.get("mcp_server"),
                output_type=u.get("output_type", "INTERNAL"),
                assigned_constraints=u.get("assigned_constraints", []),
            ))
        return result