"""Planner — L1 戰略拆解 + L2 戰術規劃"""

import json
import re
from typing import List, Dict, Any, Optional
from models.blueprints import Unit, Step
import config
from clients.message_builder import MessageBuilder


class Planner:
    def __init__(self, call_model_func=None):
        self.call_model_func = call_model_func

    async def disassemble(self, goal: str, entities: list, scope: str,
                          constraints: list, success_criteria: str) -> List[Unit]:
        """L1：將任務拆成 Units

        Args:
            goal: 任務目標
            entities: 操作實體列表
            scope: 範圍
            constraints: 約束條件列表
            success_criteria: 成功標準

        Returns:
            Unit 列表
        """
        prompt = config.DISASSEMBLY_PROMPT

        # 建構輸入內容
        input_text = f"[GOAL]{goal}[/GOAL]\n"
        input_text += f"[ENTITIES]{', '.join(entities) if entities else '無'}[/ENTITIES]\n"
        input_text += f"[SCOPE]{scope}[/SCOPE]\n"
        input_text += f"[CONSTRAINTS]{', '.join(constraints) if constraints else '無'}[/CONSTRAINTS]\n"
        input_text += f"[SUCCESS_CRITERIA]{success_criteria}[/SUCCESS_CRITERIA]"

        messages = MessageBuilder.build_task(prompt, input_text)

        content, _ = await self.call_model_func(
            config.LARGE_MODEL_NAME, messages,
            config.DISASSEMBLY_TEMPERATURE, config.DISASSEMBLY_MAX_TOKENS,
            config.DISASSEMBLY_THINK
        )

        # 解析 JSON 陣列：使用貪婪匹配從第一個 [ 到最後一個 ]
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if not match:
            return []

        try:
            units_data = json.loads(match.group())
        except json.JSONDecodeError:
            return []

        units = []
        for u in units_data:
            units.append(Unit(
                unit_id=str(u.get("id", "")),
                goal=u.get("content", ""),
                expected_input=u.get("expected_input", []),
                expected_output=u.get("expected_output", []),
                depends_on=u.get("depends_on", []),
                mcp_server=u.get("mcp_server"),
                output_type=u.get("output_type", "INTERNAL")
            ))
        return units

    async def plan_unit(self, unit: Unit, tools_list: list,
                        successful_steps: list = None) -> List[Step]:
        """L2：對單一 Unit 規劃 Steps

        Args:
            unit: 要規劃的 Unit
            tools_list: L1 分配的 MCP Server 對應的 tool function 列表
            successful_steps: 已成功 Steps 的 [(step_id, goal), ...]，用於重新規劃

        Returns:
            Step 列表
        """
        prompt = config.STEP_PLAN_PROMPT

        # 建構單元描述：把 <unit:id> 替換成語意描述，避免 L2 把 unit id 誤植到 step depends_on
        goal_for_l2 = re.sub(
            r'<unit:(\d+)>',
            lambda m: f"上游單元 {m.group(1)} 的輸出",
            unit.goal
        )
        input_text = f"單元目標：{goal_for_l2}\n"
        input_text += f"預期輸入：{unit.expected_input}\n"
        input_text += f"預期輸出：{unit.expected_output}\n"

        # 如果有已成功步驟，加入重新規劃資訊
        if successful_steps:
            input_text += "\n已成功步驟：\n"
            for sid, sgoal in successful_steps:
                input_text += f"  step_id={sid}: {sgoal}\n"

        # 注入工具列表
        tools_json = json.dumps(tools_list, ensure_ascii=False, indent=2)
        context = f"[UNIT]{input_text}[/UNIT]\n[TOOLS]{tools_json}[/TOOLS]"

        messages = MessageBuilder.build_task(prompt, context)

        content, _ = await self.call_model_func(
            config.LARGE_MODEL_NAME, messages,
            config.STEP_TEMPERATURE, config.STEP_MAX_TOKENS,
            config.STEP_THINK
        )

        # 解析 JSON：支持 Array 或 Object（自動包成 Array）容錯
        array_match = re.search(r'\[.*\]', content, re.DOTALL)
        obj_match = re.search(r'\{.*\}', content, re.DOTALL)

        if array_match:
            content_to_parse = array_match.group()
        elif obj_match:
            # LLM 輸出 Object 時自動包成 Array
            content_to_parse = f"[{obj_match.group()}]"
        else:
            return []

        try:
            steps_data = json.loads(content_to_parse)
        except json.JSONDecodeError:
            return []

        steps = []
        for s in steps_data:
            method_name = s.get("tools", None)

            # 從 tools_list 找到 method 對應的完整 schema
            step_tool = None
            if method_name and tools_list:
                for tool in tools_list:
                    if (tool.get("type") == "function" and
                        tool["function"]["name"] == method_name):
                        step_tool = tool  # 完整 schema
                        break

            steps.append(Step(
                step_id=str(s.get("id", "")),
                goal=s.get("content", ""),
                tool=step_tool,  # 完整工具 schema 或 None
                depends_on=s.get("depends_on", []),
                output_type=s.get("output_type", "INTERNAL")
            ))
        return steps