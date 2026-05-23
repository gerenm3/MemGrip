"""Planner — L1 戰略拆解 + L2 戰術規劃"""

import json
import re
from typing import Any, Dict, List, Optional
from models.blueprints import Unit, Step
import config
from clients.message_builder import MessageBuilder


class Planner:
    def __init__(self, call_model_func: Any = None) -> None:
        self.call_model_func = call_model_func

    @staticmethod
    def _parse_json_response(content: str) -> Optional[List]:
        """解析 LLM 回傳的 JSON 內容，支援 Array / Object / 多個並排 Object。"""
        array_match = re.search(r"\[.*\]", content, re.DOTALL)
        obj_match = re.search(r"\{.*\}", content, re.DOTALL)

        if array_match:
            content_to_parse = array_match.group()
        elif obj_match:
            candidate = obj_match.group()
            brace_blocks = []
            depth = 0
            start: Optional[int] = None
            for i, ch in enumerate(candidate):
                if ch == "{":
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and start is not None:
                        brace_blocks.append(candidate[start : i + 1])
                        start = None
            content_to_parse = (
                "[" + ", ".join(brace_blocks) + "]"
                if len(brace_blocks) >= 2
                else f"[{candidate}]"
            )
        else:
            return None

        try:
            return json.loads(content_to_parse)
        except json.JSONDecodeError:
            return None

    async def _call_llm(
        self,
        prompt: str,
        input_text: str,
        model: str,
        temperature: float,
        max_tokens: int,
        think: bool,
        caller: str,
        tools: Optional[List[Dict]] = None,
        unit_id: Optional[str] = None,
    ) -> str:
        """呼叫 LLM 並回傳 content"""
        messages = MessageBuilder.build_task(prompt, input_text)
        content, _ = await self.call_model_func(
            model, messages, temperature, max_tokens, think, tools=tools, caller=caller, unit_id=unit_id
        )
        return content

    def _build_disassembly_input(self, goal: str, entities: List[str], scope: str, constraints: List[str], success_criteria: str) -> str:
        """建構拆解任務的輸入文字"""
        input_parts = [
            f"[GOAL]{goal}[/GOAL]",
            f"[ENTITIES]{', '.join(entities)}[/ENTITIES]" if entities else "[ENTITIES]無[/ENTITIES]",
            f"[SCOPE]{scope}[/SCOPE]",
            f"[CONSTRAINTS]{', '.join(constraints)}[/CONSTRAINTS]" if constraints else "[CONSTRAINTS]無[/CONSTRAINTS]",
            f"[SUCCESS_CRITERIA]{success_criteria}[/SUCCESS_CRITERIA]",
        ]
        return "\n".join(input_parts)

    def _parse_units(self, content: str) -> List[Unit]:
        """將 JSON 文字解析為 Unit 列表"""
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if not match:
            return []
        try:
            units_data = json.loads(match.group())
        except json.JSONDecodeError:
            return []
        return [
            Unit(
                unit_id=str(u.get("id", "")),
                goal=u.get("content", ""),
                expected_input=u.get("expected_input", []),
                expected_output=u.get("expected_output", []),
                depends_on=u.get("depends_on", []),
                mcp_server=u.get("mcp_server"),
                output_type=u.get("output_type", "INTERNAL"),
            )
            for u in units_data
        ]

    async def disassemble(
        self,
        goal: str,
        entities: List[str],
        scope: str,
        constraints: List[str],
        success_criteria: str,
        tools: str = "",
        skill_guide: str = "",
    ) -> List[Unit]:
        """L1：將任務拆成 Units"""
        prompt = config.DISASSEMBLY_PROMPT
        if tools or skill_guide:
            prompt = prompt.format(tools=tools, skill_guide=skill_guide)

        input_text = self._build_disassembly_input(goal, entities, scope, constraints, success_criteria)
        content = await self._call_llm(
            prompt, input_text,
            config.LARGE_MODEL_NAME,
            config.DISASSEMBLY_TEMPERATURE,
            config.DISASSEMBLY_MAX_TOKENS,
            config.DISASSEMBLY_THINK,
            caller="planner_l1",
        )
        return self._parse_units(content)

    def _build_step_input(
        self,
        unit: Unit,
        successful_steps: Optional[List[tuple]] = None,
        failed_step_info: Optional[dict] = None,
    ) -> str:
        """建構步驟規劃的輸入文字"""
        goal_for_l2 = re.sub(
            r"<unit:(\d+)>",
            lambda m: f"上游單元 {m.group(1)} 的輸出",
            unit.goal,
        )
        input_parts = [
            f"單元目標：{goal_for_l2}",
            f"預期輸入：{unit.expected_input}",
            f"預期輸出：{unit.expected_output}",
        ]
        if successful_steps:
            input_parts.append(
                "\n已成功步驟：\n" + "\n".join(f"  step_id={sid}: {sgoal}" for sid, sgoal in successful_steps)
            )
        if failed_step_info:
            input_parts.append(
                "\n前次失敗步驟：\n"
                + f"  step_id={failed_step_info.get('step_id', '')}\n"
                + f"  goal: {failed_step_info.get('goal', '')}\n"
                + f"  content: {failed_step_info.get('content', '')}"
            )
        return "\n".join(input_parts)

    def _parse_steps(self, steps_data: List, tool_map: Dict[str, Dict]) -> List[Step]:
        """將 JSON 資料解析為 Step 列表"""
        return [
            Step(
                step_id=str(s.get("id", "")),
                goal=s.get("content", ""),
                tool=tool_map.get(s.get("tools")),
                depends_on=s.get("depends_on", []),
                upstream_depends=s.get("upstream_depends", []),
                output_type=s.get("output_type", "INTERNAL"),
            )
            for s in steps_data
        ]

    async def plan_unit(
        self,
        unit: Unit,
        tools_list: List[Dict],
        successful_steps: Optional[List[tuple]] = None,
        failed_step_info: Optional[dict] = None,
    ) -> List[Step]:
        """L2：對單一 Unit 規劃 Steps"""
        prompt = config.STEP_PLAN_PROMPT
        input_text = self._build_step_input(unit, successful_steps, failed_step_info)

        slim_tools = [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"]
            }
            for t in tools_list
            if t.get("type") == "function"
        ]
        tools_json = json.dumps(slim_tools, ensure_ascii=False, indent=2)
        context = f"[UNIT]{unit.goal}[/UNIT]\n[TOOLS]{tools_json}[/TOOLS]"

        content = await self._call_llm(
            prompt, context,
            config.LARGE_MODEL_NAME,
            config.STEP_TEMPERATURE,
            config.STEP_MAX_TOKENS,
            config.STEP_THINK,
            caller="planner_l2",
            unit_id=unit.unit_id,
        )

        steps_data = self._parse_json_response(content)
        if steps_data is None:
            return []

        tool_map = {
            t["function"]["name"]: t
            for t in tools_list
            if t.get("type") == "function"
        } if tools_list else {}

        return self._parse_steps(steps_data, tool_map)
