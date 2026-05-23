"""Executor — L3 執行 + Agentic Loop"""

import json
import re
import config
from typing import List, Dict, Any, Optional
from models.blueprints import Unit, Step, StepResult, StepStatus, UnitResult, UnitStatus
from core.storage import UnitStore, StepStore
from clients.message_builder import MessageBuilder


class Executor:
    """L3 執行器：負責 Unit 內 Step 的執行與 Agentic Loop"""

    def __init__(
        self,
        call_model_func: Any = None,
        planner: Any = None,
        execute_tool_func: Any = None,
        tool_manager: Any = None,
    ) -> None:
        self.call_model_func = call_model_func
        self.planner = planner
        self.execute_tool_func = execute_tool_func
        self.tool_manager = tool_manager

    @staticmethod
    def _format_tool_call(tc: Any) -> dict | None:
        """將 tool_call 轉換為統一的 {name, arguments} 格式。

        支援兩種輸入：
        - object with .function attribute
        - dict

        Returns:
            格式化後的 dict，解析失敗回傳 None
        """
        if hasattr(tc, "function"):
            func = tc.function
            return {"name": func.name, "arguments": func.arguments}
        if isinstance(tc, dict):
            return {
                "name": tc.get("function", {}).get("name", ""),
                "arguments": tc.get("function", {}).get("arguments", {}),
            }
        return None

    @staticmethod
    def _parse_tool_arguments(raw: Any) -> dict:
        """解析 tool arguments：支援 str (JSON) 或 dict."""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    async def execute_units(self, units: List[Unit], server_schemas: dict) -> Dict[str, UnitResult]:
        """按拓撲順序執行所有 Units

        流程：
        1. L2 規劃：逐個規劃所有 Units 的 Steps
        2. L3 執行：全部規劃完成後統一執行

        Args:
            units: Unit 列表
            server_schemas: {server_name: [tool_schemas]}

        Returns:
            {unit_id: UnitResult}
        """
        from core.scheduler import topological_sort, apply_pruning

        sorted_units = topological_sort(units)
        unit_store = UnitStore()
        results: Dict[str, UnitResult] = {}

        # ==== 第一階段：L2 規劃所有 Units 的 Steps ====
        unit_steps: Dict[str, List[Step]] = {}
        unit_tools: Dict[str, list] = {}

        for unit in sorted_units:
            if self._should_skip(unit, results):
                self._handle_skipped(unit, unit_store, results)
                continue

            tools_list = self._get_tools_for_server(unit.mcp_server, server_schemas)
            unit_tools[unit.unit_id] = tools_list

            steps = await self.planner.plan_unit(unit, tools_list)
            if not steps:
                if unit.mcp_server:
                    self._handle_planning_failure(unit, "L2 規劃失敗：有工具但 steps 解析為空", unit_store, results)
                    continue
                steps = [Step(step_id="1", goal=unit.goal)]

            unit_steps[unit.unit_id] = steps

        # ==== 第二階段：L3 統一執行所有 Units ====
        for unit in sorted_units:
            if self._should_skip(unit, results):
                continue

            upstream_outputs = self._collect_upstream_outputs(unit, results)
            steps = unit_steps.get(unit.unit_id, [])
            tools_list = unit_tools.get(unit.unit_id, [])

            if not steps:
                steps = [Step(step_id="1", goal=unit.goal)]

            step_store = StepStore(unit.unit_id)
            current_step_idx = 0

            replan_count, total_loop_count, step_loop_counts = await self._execute_unit_steps(
                unit, steps, tools_list, step_store, upstream_outputs, results, unit_store
            )

            # 將 loop info 寫入既有 result（不覆蓋 status/output/error）
            # 只有當 result 的 loop counts 為 0 時才寫入（如 _handle_planning_failure 的 FAILED result）
            if unit.unit_id in results:
                existing = results[unit.unit_id]
                if existing.total_loop_count == 0 and not existing.step_loop_counts:
                    existing.total_loop_count = total_loop_count
                    existing.step_loop_counts = list(step_loop_counts.values())

        results = apply_pruning(units, results)
        return results

    def _handle_skipped(self, unit: Unit, unit_store: UnitStore, results: Dict[str, UnitResult]) -> None:
        """處理被跳過的 Unit"""
        unit_store.set_status(unit.unit_id, UnitStatus.SKIPPED)
        unit_store.set_error(unit.unit_id, "依賴的 Unit 失敗，跳過執行")
        results[unit.unit_id] = UnitResult(
            unit_id=unit.unit_id,
            status=UnitStatus.SKIPPED,
            error="依賴的 Unit 失敗，跳過執行",
        )

    def _handle_planning_failure(
        self, unit: Unit, error_msg: str, unit_store: UnitStore, results: Dict[str, UnitResult]
    ) -> None:
        """處理 L2 規劃失敗"""
        unit_store.set_status(unit.unit_id, UnitStatus.FAILED)
        unit_store.set_error(unit.unit_id, error_msg)
        results[unit.unit_id] = UnitResult(
            unit_id=unit.unit_id,
            status=UnitStatus.FAILED,
            error=error_msg,
        )

    def _handle_no_global_output(self, unit: Unit, unit_store: UnitStore, results: Dict[str, UnitResult], total_loop_count: int = 0, step_loop_counts: list | None = None) -> None:
        """處理沒有 GLOBAL 輸出的情況"""
        unit_store.set_status(unit.unit_id, UnitStatus.FAILED)
        unit_store.set_error(unit.unit_id, "L2 規劃遺漏：沒有 GLOBAL/ACTION output")
        results[unit.unit_id] = UnitResult(
            unit_id=unit.unit_id,
            status=UnitStatus.FAILED,
            error="L2 規劃遺漏：沒有 GLOBAL/ACTION output",
            total_loop_count=total_loop_count,
            step_loop_counts=step_loop_counts or [],
        )

    async def _verify_unit_output(self, unit: Unit, actual_output: str) -> dict:
        """用 9B LLM 審核 unit 輸出是否符合 expected_output"""
        expected = unit.expected_output or ""
        expected_str = expected if expected else "(未指定)"

        messages = MessageBuilder.build_task(
            f"""你是一個輸出品質審核員。請判斷實際輸出是否符合預期意圖。

注意事項：
- 預期輸出是「語意描述」，不是精確格式要求
- 判斷標準是「實際輸出的內容是否符合預期描述的意圖」
- 不要進行字面比對

預期輸出描述：{expected_str}

實際輸出：{actual_output}

請輸出 JSON：{{"passed": true/false, "reason": "理由"}}""",
            "",
        )
        content, _ = await self.call_model_func(
            config.MEDIUM_MODEL_NAME,
            messages,
            0.0,
            256,
            False,
            caller="executor_verify",
        )
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"passed": False, "reason": "驗證輸出格式錯誤"}

    def _handle_success(self, unit: Unit, steps: List[Step], step_store: StepStore, unit_store: UnitStore, results: Dict[str, UnitResult]) -> None:
        """處理成功的 Unit"""
        global_outputs = [
            step_store.get_output(s.step_id)
            for s in steps
            if s.output_type == "GLOBAL" and step_store.get_output(s.step_id)
        ]
        output = "\n\n".join(global_outputs) if global_outputs else ""

        if unit.output_type == "ACTION":
            clean_goal = re.sub(r"<unit:(\d+)>", lambda m: f"單元 {m.group(1)}", unit.goal)
            unit_output = f"{clean_goal}：已完成"
        else:
            unit_output = output

        unit_store.set_status(unit.unit_id, UnitStatus.SUCCESS)
        unit_store.set_output(unit.unit_id, output)
        results[unit.unit_id] = UnitResult(
            unit_id=unit.unit_id,
            status=UnitStatus.SUCCESS,
            output=unit_output,
        )

    async def _execute_unit_steps(
        self,
        unit: Unit,
        steps: List[Step],
        tools_list: list,
        step_store: StepStore,
        upstream_outputs: dict,
        results: Dict[str, UnitResult],
        unit_store: UnitStore,
    ) -> tuple[int, int, dict]:
        """執行單一 Unit 的所有 Steps，回傳 (replan_count, total_loop_count, step_loop_counts)"""
        current_step_idx = next(
            (i for i, s in enumerate(steps) if s.step_id == steps[0].step_id),
            0,
        )
        final_replan_count = 0
        total_loop_count = 0
        step_loop_counts: dict = {}

        while current_step_idx < len(steps):
            step = steps[current_step_idx]
            step_store.set_goal(step.step_id, step.goal)

            deps_met, valid_depends_on = self._check_dependencies(step, step_store)

            if valid_depends_on:
                step.depends_on = valid_depends_on

            if not deps_met:
                current_step_idx += 1
                continue

            step_result = await self._execute_step(step, unit, step_store, upstream_outputs)

            # 追蹤該 step 的 loop_count
            step_loop_counts[step.step_id] = step_result.loop_count
            total_loop_count += step_result.loop_count

            if step_result.status == StepStatus.FAILED:
                if final_replan_count < config.MAX_REPLAN_ATTEMPTS:
                    successful_steps = step_store.get_successful_steps()
                    
                    # 收集失敗 step 的資訊，供 L2 重排時參考
                    failed_step_content = step_store.get_output(step.step_id) or step_result.error or ""
                    failed_step_info = {
                        "step_id": step.step_id,
                        "goal": step.goal,
                        "content": failed_step_content,
                    }
                    
                    new_steps = await self.planner.plan_unit(unit, tools_list, successful_steps, failed_step_info)
                    if new_steps:
                        steps[:] = new_steps
                        current_step_idx = next(
                            (i for i, s in enumerate(steps) if s.step_id == step.step_id),
                            len(steps) - 1,
                        )
                    else:
                        current_step_idx += 1
                    final_replan_count += 1
                else:
                    step_store.set_status(step.step_id, StepStatus.FAILED)
                    step_store.set_error(step.step_id, step_result.error)
                    break

            step_store.set_status(step.step_id, StepStatus.SUCCESS)
            step_store.set_output(step.step_id, step_result.output)
            current_step_idx += 1

        if final_replan_count >= config.MAX_REPLAN_ATTEMPTS:
            self._handle_planning_failure(
                unit,
                f"Step 執行失敗，超出重新規劃上限 ({config.MAX_REPLAN_ATTEMPTS} 次)",
                unit_store,
                results,
            )
        else:
            await self._check_global_output(unit, steps, step_store, unit_store, results, total_loop_count, dict(step_loop_counts))

        return (final_replan_count, total_loop_count, step_loop_counts)

    def _check_dependencies(self, step: Step, step_store: StepStore) -> tuple[bool, list]:
        """檢查依賴是否滿足"""
        deps_met = True
        valid_depends_on = []
        for sid in step.depends_on:
            sid_str = str(sid)
            dep_status = step_store.get_status(sid_str)
            if dep_status is None or dep_status != StepStatus.SUCCESS:
                deps_met = False
            else:
                valid_depends_on.append(sid_str)
        return deps_met, valid_depends_on

    async def _check_global_output(
        self, unit: Unit, steps: List[Step], step_store: StepStore, unit_store: UnitStore, results: Dict[str, UnitResult],
        total_loop_count: int = 0, step_loop_counts: dict | None = None
    ) -> None:
        """檢查 GLOBAL/ACTION output 是否存在，並驗證輸出"""
        has_global_or_action = any(
            s.output_type in ("GLOBAL", "ACTION") for s in steps
        )

        if not has_global_or_action:
            self._handle_no_global_output(unit, unit_store, results, total_loop_count, dict(step_loop_counts) if step_loop_counts else [])
            return

        global_outputs = [
            step_store.get_output(s.step_id)
            for s in steps
            if s.output_type in ("GLOBAL", "ACTION") and step_store.get_output(s.step_id)
        ]

        if not global_outputs:
            self._handle_no_global_output(unit, unit_store, results, total_loop_count, dict(step_loop_counts) if step_loop_counts else [])
        else:
            actual_output = "\n\n".join(global_outputs)

            # 用 9B LLM 審核輸出
            verification = await self._verify_unit_output(unit, actual_output)
            if verification.get("passed"):
                # 驗證通過，標記 SUCCESS
                unit_output = actual_output if unit.output_type != "ACTION" else f"{re.sub(r'<unit:(\d+)>', lambda m: f'單元 {m.group(1)}', unit.goal)}：已完成"
                unit_store.set_status(unit.unit_id, UnitStatus.SUCCESS)
                unit_store.set_output(unit.unit_id, actual_output)
                results[unit.unit_id] = UnitResult(
                    unit_id=unit.unit_id,
                    status=UnitStatus.SUCCESS,
                    output=unit_output,
                    total_loop_count=total_loop_count,
                    step_loop_counts=step_loop_counts or [],
                )
            else:
                # 驗證失敗，標記 FAILED
                reason = verification.get("reason", "審核未通過")
                unit_store.set_status(unit.unit_id, UnitStatus.FAILED)
                unit_store.set_error(unit.unit_id, f"輸出審核失敗：{reason}")
                results[unit.unit_id] = UnitResult(
                    unit_id=unit.unit_id,
                    status=UnitStatus.FAILED,
                    error=f"輸出審核失敗：{reason}",
                    total_loop_count=total_loop_count,
                    step_loop_counts=step_loop_counts or [],
                )

    def _finalize_unit(
        self, unit: Unit, steps: List[Step], unit_store: UnitStore, step_store: StepStore, results: Dict[str, UnitResult]
    ) -> int:
        """完成 Unit 執行，回傳 replan count（目前未使用）"""
        # 檢查是否有失敗的 step
        failed_steps = [s for s in steps if step_store.get_status(s.step_id) == StepStatus.FAILED]
        if len(failed_steps) > 0:
            # 假設有 replan 發生
            return len(failed_steps)
        return 0

    async def _execute_step(
        self,
        step: Step,
        unit: Unit,
        step_store: StepStore,
        upstream_outputs: dict,
    ) -> StepResult:
        """執行單一 Step（L3 + Agentic Loop）

        Args:
            step: 要執行的 Step
            unit: Step 所屬的 Unit
            step_store: Step 的儲存
            upstream_outputs: 上游 Unit 的輸出 {unit_id: output}

        Returns:
            StepResult
        """
        # 1. 解析 step_goal：替換 <unit:id> 為可讀標籤
        step_goal = self._resolve_unit_placeholders(step.goal, upstream_outputs)

        # 2. 建構 tool_instruction
        tool_instruction = self._build_tool_instruction(step)

        # 3. 建構 system content
        environment = self._build_environment(unit.mcp_server)
        system_content = config.STEP_EXECUTE_PROMPT.format(
            step_goal=step_goal,
            tool_instruction=tool_instruction,
            environment=environment,
        )

        # 4. 建構 user messages
        user_messages = self._build_user_messages(step, step_store, upstream_outputs)

        # 5. Agentic Loop
        conversation = [{"role": "system", "content": system_content}] + user_messages
        agentic_result, loop_count = await self._run_agentic_loop(step, conversation, unit.unit_id, step.step_id)

        return self._build_step_result(
            content=agentic_result.get("content", ""),
            tool_results=agentic_result.get("tool_results", []),
            loop_count=loop_count,
        )

    def _resolve_unit_placeholders(self, goal: str, upstream_outputs: dict) -> str:
        """將 <unit:id> 替換為可讀標籤"""
        for uid in upstream_outputs:
            uid_str = str(uid) if not isinstance(uid, str) else uid
            goal = goal.replace(f"<unit:{uid_str}>", f"[Unit {uid_str} 的輸出]")
        return goal

    def _build_tool_instruction(self, step: Step) -> str:
        """建構 tool instruction"""
        if step.tool:
            if isinstance(step.tool, dict):
                tool_name = step.tool.get("function", {}).get("name", "unknown")
            else:
                tool_name = str(step.tool)
            return f"使用工具 {tool_name}，調用後將回傳內容直接輸出。"
        return "本步驟為純推理，不得調用任何工具。"

    def _build_environment(self, server_name: Optional[str]) -> str:
        """建構環境資訊"""
        if not server_name or not self.tool_manager:
            return ""
        env_desc = self.tool_manager.tool_environments.get(server_name, "")
        return env_desc if env_desc else f"Server: {server_name}"

    @staticmethod
    def _normalize_uid(uid) -> str:
        """將 UID 正規化為純數字格式，同時支援 'unit:1' 和 '1' 兩種格式"""
        uid = str(uid)
        return uid.replace("unit:", "") if uid.startswith("unit:") else uid

    def _build_user_messages(self, step: Step, step_store: StepStore, upstream_outputs: dict) -> list[dict]:
        """建構 user messages"""
        normalized_depends = {self._normalize_uid(d) for d in step.upstream_depends} if step.upstream_depends else set()
        user_messages = [
            {"role": "user", "content": f"[來自 Unit {uid}]\n{output}"}
            for uid, output in upstream_outputs.items()
            if not step.upstream_depends or self._normalize_uid(uid) in normalized_depends
        ]

        if step.depends_on:
            user_messages += [
                {
                    "role": "user",
                    "content": f"[來自 Step {dep_id}]\n{step_store.get_output(str(dep_id))}",
                }
                for dep_id in step.depends_on
                if step_store.get_output(str(dep_id))
            ]

        if not user_messages:
            user_messages.append({"role": "user", "content": "[輸入資料]\n（無前置資料）"})

        return user_messages

    async def _run_agentic_loop(self, step: Step, conversation: list, unit_id: str, step_id: str) -> tuple[dict, int]:
        """執行 Agentic Loop，回傳 (result_dict, 實際迭代次數)"""
        successful_tool_results: list[str] = []
        max_iterations = 5
        iterations = 0

        for _ in range(max_iterations):
            iterations += 1
            tools = self._build_tools_for_step(step)
            content, tool_calls = await self.call_model_func(
                config.MEDIUM_MODEL_NAME,
                conversation,
                config.STEP_EXECUTE_TEMPERATURE,
                config.STEP_EXECUTE_MAX_TOKENS,
                config.STEP_EXECUTE_THINK,
                tools,
                caller="executor",
                unit_id=unit_id,
                step_id=step_id,
            )

            if tool_calls:
                assistant_msg: dict = {"role": "assistant", "content": content or "", "tool_calls": []}
                valid_tool_results = []
                valid_tool_calls = []

                for tool_call in tool_calls:
                    if (parsed := self._format_tool_call(tool_call)) is None:
                        continue

                    t_name = parsed["name"]
                    t_args = self._parse_tool_arguments(parsed["arguments"])

                    assistant_msg["tool_calls"].append({"function": {"name": t_name, "arguments": t_args}})
                    valid_tool_calls.append({"function": {"name": t_name, "arguments": t_args}})

                    tool_result = await self.execute_tool_func(t_name, t_args)
                    valid_tool_results.append(tool_result)

                    if not self._is_error_result(tool_result):
                        successful_tool_results.append(f"[{t_name}]\n{tool_result}")

                tool_result_msgs = [
                    {
                        "role": "tool",
                        "content": f"[工具回傳]\n{tr}",
                        "tool_name": vc["function"]["name"] if isinstance(vc, dict) and "function" in vc else "unknown",
                    }
                    for tr, vc in zip(valid_tool_results, valid_tool_calls)
                ]

                conversation.append(assistant_msg)
                conversation.extend(tool_result_msgs)
                continue

            break

        return ({"content": content, "tool_results": successful_tool_results}, iterations)

    def _build_tools_for_step(self, step: Step) -> list | None:
        """建構 Step 可用的 tools"""
        if not step.tool:
            return None
        if isinstance(step.tool, dict):
            return [step.tool]
        return [{"type": "function", "function": {
            "name": step.tool,
            "description": f"執行步驟 {step.step_id}",
            "parameters": {"type": "object", "properties": {}},
        }}]

    def _build_step_result(self, content: str, tool_results: list, loop_count: int = 0) -> StepResult:
        """建構 StepResult"""
        output = content + "\n\n[TOOL_RESULTS]\n" + "\n\n".join(tool_results) if tool_results else content
        return StepResult(step_id="", status=StepStatus.SUCCESS, output=output, loop_count=loop_count)

    @staticmethod
    def _is_error_result(result: str) -> bool:
        """檢查 tool result 是否為錯誤訊息（僅檢查 [TOOL_ERROR] 前綴）"""
        if not result:
            return True
        return result.startswith("[TOOL_ERROR]")

    def _should_skip(self, unit: Unit, results: dict) -> bool:
        """檢查 Unit 是否應被剪枝"""
        return any(
            (result := results.get(str(dep_id), None))
            and result.status in (UnitStatus.FAILED, UnitStatus.SKIPPED)
            for dep_id in unit.depends_on
        )

    def _collect_upstream_outputs(self, unit: Unit, results: dict) -> dict:
        """收集上游 Unit 的輸出"""
        outputs = {}
        for dep_id in unit.depends_on:
            dep_key = str(dep_id)
            result = results.get(dep_key)
            if result and result.status == UnitStatus.SUCCESS:
                outputs[dep_key] = result.output
        return outputs

    def _get_tools_for_server(self, server_name: Optional[str], server_schemas: dict) -> list:
        """取得指定 MCP Server 的 tool function 列表"""
        return server_schemas.get(server_name, []) if server_name else []
