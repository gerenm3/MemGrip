"""Executor — L3 執行 + Agentic Loop"""

import json
import re
import config
from typing import List, Dict, Any, Optional
from models.blueprints import Unit, Step, StepResult, StepStatus, UnitResult, UnitStatus
from core.planner import Planner
from core.storage import UnitStore, StepStore
from clients.message_builder import MessageBuilder


class Executor:
    """L3 執行器：負責 Unit 內 Step 的執行與 Agentic Loop"""

    def __init__(self, call_model_func=None, execute_tool_func=None):
        self.call_model_func = call_model_func
        self.execute_tool_func = execute_tool_func
        self.planner = Planner(call_model_func=call_model_func)

    async def execute_units(self, units: List[Unit], server_schemas: dict,
                            unit_store: UnitStore) -> Dict[str, UnitResult]:
        """按拓撲順序執行所有 Units

        流程：
        1. L2 規劃：逐個規劃所有 Units 的 Steps
        2. L3 執行：全部規劃完成後統一執行

        Args:
            units: Unit 列表
            server_schemas: {server_name: [tool_schemas]}
            unit_store: UnitStore 實例

        Returns:
            {unit_id: UnitResult}
        """
        from core.scheduler import topological_sort, apply_pruning

        sorted_units = topological_sort(units)
        results: Dict[str, UnitResult] = {}
        
        # ==================== 第一階段：L2 規劃所有 Units 的 Steps ====================
        # 逐個規劃所有 Units 的 Steps，但不執行
        unit_steps: Dict[str, List[Step]] = {}  # unit_id → Steps
        unit_tools: Dict[str, list] = {}  # unit_id → tools_list
        
        for unit in sorted_units:
            # 檢查是否應被剪枝
            if self._should_skip(unit, results):
                unit_store.set_status(unit.unit_id, UnitStatus.SKIPPED)
                unit_store.set_error(unit.unit_id, f"依賴的 Unit 失敗，跳過執行")
                results[unit.unit_id] = UnitResult(
                    unit_id=unit.unit_id,
                    status=UnitStatus.SKIPPED,
                    error=f"依賴的 Unit 失敗，跳過執行"
                )
                continue

            tools_list = self._get_tools_for_server(unit.mcp_server, server_schemas)
            unit_tools[unit.unit_id] = tools_list
            
            # 規劃 Steps（由 L2 負責分配 output_type，executor 不做決策）
            steps = await self.planner.plan_unit(unit, tools_list)
            if not steps:
                steps = [Step(step_id="1", goal=unit.goal)]
            
            unit_steps[unit.unit_id] = steps

        # ==================== 第二階段：L3 統一執行所有 Units ====================
        for unit in sorted_units:
            # 檢查是否應被剪枝
            if self._should_skip(unit, results):
                continue

            # 取得上游 Unit 的輸出
            upstream_outputs = self._collect_upstream_outputs(unit, results)
            steps = unit_steps.get(unit.unit_id, [])
            tools_list = unit_tools.get(unit.unit_id, [])
            
            if not steps:
                steps = [Step(step_id="1", goal=unit.goal)]

            # 執行 Unit 內的所有 Steps
            step_store = StepStore(unit.unit_id)
            final_replan_count = 0
            
            current_step_idx = 0
            successful_steps = []
            
            while current_step_idx < len(steps):
                step = steps[current_step_idx]
                step_store.set_goal(step.step_id, step.goal)

                # 檢查是否依賴的 Step 輸出已就緒 — sid 可能是 int，轉 str
                deps_met = True
                invalid_deps = []
                valid_depends_on = []
                for sid in step.depends_on:
                    sid_str = str(sid)
                    dep_status = step_store.get_status(sid_str)
                    if dep_status is None:
                        # 依賴的 Step 不存在於當前 Unit 的 step_store 中
                        # 這通常表示 L2 規劃產生了無效的 depends_on（例如錯誤地引用了其他 Unit 的 ID）
                        invalid_deps.append(sid_str)
                        deps_met = False
                    elif dep_status != StepStatus.SUCCESS:
                        deps_met = False
                    else:
                        valid_depends_on.append(sid_str)
                
                if invalid_deps:
                    print(f"[WARNING] Unit {unit.unit_id} Step {step.step_id}: 無效依賴 Step {invalid_deps}（不存在於 step_store 中，L2 規劃可能出錯）。自動清除無效依賴，改為依賴：{valid_depends_on}")
                    # 清除無效依賴，讓 Step 能正常執行（不依賴不存在的前置 Step）
                    step.depends_on = valid_depends_on
                    deps_met = len(valid_depends_on) == 0  # 如果 cleared 後仍有效依賴，繼續等
                
                if not deps_met:
                    current_step_idx += 1
                    continue

                # 執行 Step（L3 + Agentic Loop）
                step_result = await self._execute_step(
                    step, unit, step_store, upstream_outputs
                )

                if step_result.status == StepStatus.FAILED:
                    if final_replan_count < config.MAX_REPLAN_ATTEMPTS:
                        successful_steps = step_store.get_successful_steps()
                        new_steps = await self.planner.plan_unit(
                            unit, tools_list, successful_steps
                        )
                        if new_steps:
                            steps = new_steps
                            current_step_idx = None
                            for i, s in enumerate(steps):
                                if s.step_id == step.step_id:
                                    current_step_idx = i
                                    break
                            if current_step_idx is None:
                                current_step_idx = len(steps) - 1
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

            # Unit 到達終止狀態
            if final_replan_count >= config.MAX_REPLAN_ATTEMPTS:
                last_step_id = steps[-1].step_id if steps else "unknown"
                unit_store.set_status(unit.unit_id, UnitStatus.FAILED)
                unit_store.set_error(
                    unit.unit_id,
                    f"Step 執行失敗，超出重新規劃上限 ({config.MAX_REPLAN_ATTEMPTS} 次)"
                )
                results[unit.unit_id] = UnitResult(
                    unit_id=unit.unit_id,
                    status=UnitStatus.FAILED,
                    error=f"Step 執行失敗，超出重新規劃上限"
                )
            else:
                # ==== 收集所有 GLOBAL step 的輸出（多個 GLOBAL 是合法的） ====
                global_outputs = []
                all_step_types = []  # 記錄所有 step 的 output_type 用於 debug
                for s in steps:
                    output_type = getattr(s, 'output_type', None)
                    all_step_types.append(f"step={s.step_id}, output_type={output_type}")
                    if output_type == 'GLOBAL':
                        output = step_store.get_output(s.step_id)
                        print(f"[DEBUG Executor] Unit {unit.unit_id} step {s.step_id} is GLOBAL, output_len={len(output) if output else 0}")
                        if output:
                            global_outputs.append(output)
                
                print(f"[DEBUG Executor] Unit {unit.unit_id} 所有 step 的 output_type: {all_step_types}")
                print(f"[DEBUG Executor] Unit {unit.unit_id} global_outputs 數量: {len(global_outputs)}")
                
                if not global_outputs:
                    # ACTION 類型不需要 GLOBAL 輸出（output 是「已完成」狀態）
                    if getattr(unit, 'output_type', None) == 'ACTION':
                        pass  # 繼續到 line 212 處理
                    else:
                        # L2 沒有分配任何 GLOBAL step → 回報錯誤
                        failed_step_reason = []
                        if not any(getattr(s, 'output_type', None) == 'GLOBAL' for s in steps):
                            failed_step_reason.append("沒有步驟的 output_type 為 GLOBAL")
                        else:
                            failed_step_reason.append("有 GLOBAL step 但輸出為空")
                            for s in steps:
                                if getattr(s, 'output_type', None) == 'GLOBAL':
                                    out = step_store.get_output(s.step_id)
                                    failed_step_reason.append(f"  step={s.step_id}, output={'[空]' if not out else '[有內容]'}")
                        
                        print(f"[WARNING] Unit {unit.unit_id} global_outputs 檢查失敗: {'; '.join(failed_step_reason)}")
                        unit_store.set_status(unit.unit_id, UnitStatus.FAILED)
                        unit_store.set_error(
                            unit.unit_id,
                            f"L2 規劃遺漏: {'; '.join(failed_step_reason)}"
                        )
                        results[unit.unit_id] = UnitResult(
                            unit_id=unit.unit_id,
                            status=UnitStatus.FAILED,
                            error=f"L2 規劃遺漏: {'; '.join(failed_step_reason)}"
                        )
                        continue

                # ==== global_outputs 檢查通過，收集最終輸出 ====
                output = "\n\n".join(global_outputs)

                print(f"[DEBUG] unit {unit.unit_id} output_type={getattr(unit, 'output_type', 'NOT FOUND')}")

                if getattr(unit, 'output_type', None) == 'ACTION':
                    clean_goal = re.sub(r'<unit:(\d+)>', lambda m: f"單元 {m.group(1)}", unit.goal)
                    unit_output = f"{clean_goal}：已完成"
                else:
                    unit_output = output

                print(f"[DEBUG] unit {unit.unit_id} unit_output={unit_output[:50]}")

                unit_store.set_status(unit.unit_id, UnitStatus.SUCCESS)
                unit_store.set_output(unit.unit_id, output)
                results[unit.unit_id] = UnitResult(
                    unit_id=unit.unit_id,
                    status=UnitStatus.SUCCESS,
                    output=unit_output
                )
       
            results = apply_pruning(units, results)

        return results
    
    async def _execute_step(self, step: Step, unit: Unit,
                            step_store: StepStore,
                            upstream_outputs: dict) -> StepResult:
        """執行單一 Step（L3 + Agentic Loop）

        對話結構隔離：
        - system message：只有指令
        - user messages：只有資料

        Args:
            step: 要執行的 Step
            unit: Step 所屬的 Unit
            step_store: Step 的儲存
            upstream_outputs: 上游 Unit 的輸出 {unit_id: output}

        Returns:
            StepResult
        """
        # 1. 解析 step_goal：替換 <unit:id> 為可讀標籤
        step_goal = step.goal
        for uid in upstream_outputs:
            uid_str = str(uid) if not isinstance(uid, str) else uid
            step_goal = step_goal.replace(f"<unit:{uid_str}>", f"[Unit {uid_str} 的輸出]")

        # 2. 建構 tool_instruction
        tool_instruction = ""
        if step.tool:
            tool_name = step.tool.get("function", {}).get("name", "unknown") if isinstance(step.tool, dict) else step.tool
            tool_instruction = f"使用工具 {tool_name}，調用後將回傳內容直接輸出。"
        else:
            tool_instruction = "本步驟為純推理，不得調用任何工具。"

        # 3. system message：只有指令


        # 4. user messages：只有資料（按順序）
        user_messages = []

        # 4a. 上游 Unit 輸出
        for uid, output in upstream_outputs.items():
            user_messages.append({
                "role": "user",
                "content": f"[來自 Unit {uid}]\n{output}"
            })

        # 4b. 前置 Step 輸出（只在有 depends_on 時注入）
        if step.depends_on:
            for dep_id in step.depends_on:
                output = step_store.get_output(str(dep_id))
                if output:
                    user_messages.append({
                        "role": "user",
                        "content": f"[來自 Step {dep_id}]\n{output}"
                    })

        # 4c. 允許目錄（只在有 mcp_server 時注入）
        environment = ""
        if unit.mcp_server:
            env_info = config.TOOL_ENVIRONMENT.get(unit.mcp_server, {})
            instruction = env_info.get("instruction", "")
            if instruction:
                environment = instruction
            elif env_info:
                environment = "\n".join(f"{k}：{v}" for k, v in env_info.items())
        print(f"[DEBUG] unit {unit.unit_id} mcp_server={unit.mcp_server} environment={repr(environment)}")
        system_content = config.STEP_EXECUTE_PROMPT.format(
            step_goal=step_goal,
            tool_instruction=tool_instruction,
            environment=environment
        )

        # 4d. 若全部為空，注入「無前置資料」佔位
        if not user_messages:
            user_messages.append({
                "role": "user",
                "content": "[輸入資料]\n（無前置資料）"
            })

        # 5. Agentic Loop
        conversation = [
            {"role": "system", "content": system_content}
        ] + user_messages

        # 追蹤成功的 tool results（用於最終合併到 output）
        successful_tool_results = []

        max_iterations = 20
        for _ in range(max_iterations):
            # 如果有工具，注入工具定義
            tools = None
            if step.tool:
                if isinstance(step.tool, dict):
                    tools = [step.tool]
                else:
                    # fallback：如果 step.tool 是字串（舊資料或預設值）
                    tools = [{"type": "function", "function": {
                        "name": step.tool,
                        "description": f"執行步驟 {step.step_id}",
                        "parameters": {"type": "object", "properties": {}}
                    }}]

            content, tool_calls = await self.call_model_func(
                config.MEDIUM_MODEL_NAME, conversation,
                config.STEP_EXECUTE_TEMPERATURE, config.STEP_EXECUTE_MAX_TOKENS,
                config.STEP_EXECUTE_THINK, tools
            )

            # 處理工具調用
            if tool_calls:
                # 建構 assistant message（含 tool_calls）
                assistant_msg = {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": []
                }
                tool_result_msgs = []

                for tool_call in tool_calls:
                    if hasattr(tool_call, 'function'):
                        t_name = tool_call.function.name
                        t_args_raw = tool_call.function.arguments
                    else:
                        t_name = tool_call.get("function", {}).get("name", "")
                        t_args_raw = tool_call.get("function", {}).get("arguments", {})

                    if isinstance(t_args_raw, str):
                        try:
                            t_args = json.loads(t_args_raw)
                        except json.JSONDecodeError:
                            t_args = {}
                    elif isinstance(t_args_raw, dict):
                        t_args = t_args_raw
                    else:
                        t_args = {}

                    assistant_msg["tool_calls"].append({
                        "function": {"name": t_name, "arguments": t_args}
                    })

                    # 執行工具
                    tool_result = await self.execute_tool_func(t_name, t_args)

                    # 過濾錯誤結果
                    if not self._is_error_result(tool_result):
                        successful_tool_results.append(f"[{t_name}]\n{tool_result}")

                    tool_result_msgs.append({
                        "role": "tool",
                        "content": f"[工具回傳]\n{tool_result}",
                        "tool_name": t_name
                    })

                # 在 conversation 中追加 assistant + 所有 tool results
                conversation.append(assistant_msg)
                conversation.extend(tool_result_msgs)

                # 繼續下一輪迭代
                continue

            # 沒有工具調用：返回最終結果
            break

        # 6. 合併 tool results 到 output
        if successful_tool_results:
            output = content + "\n\n[TOOL_RESULTS]\n" + "\n\n".join(successful_tool_results)
        else:
            output = content

        return StepResult(
            step_id=step.step_id,
            status=StepStatus.SUCCESS,
            output=output
        )

    @staticmethod
    def _is_error_result(result: str) -> bool:
        """檢查 tool result 是否為錯誤訊息"""
        if not result:
            return True
        result_lower = result.lower()
        error_keywords = [
            'access denied', 'permission denied', 'file not found',
            'error:', 'traceback', 'denied'
        ]
        return any(kw in result_lower for kw in error_keywords)

    def _should_skip(self, unit: Unit, results: dict) -> bool:
        """檢查 Unit 是否應被剪枝"""
        for dep_id in unit.depends_on:
            # 確保 dep_id 是 str 型別（L1 Disassembly 的 JSON 可能产出 int）
            dep_key = str(dep_id) if not isinstance(dep_id, str) else dep_id
            result = results.get(dep_key)
            if result and result.status in (UnitStatus.FAILED, UnitStatus.SKIPPED):
                #print(f"[DEBUG Executor] Unit {unit.unit_id} 依賴 {dep_id}({dep_key}) 狀態={result.status}, 剪枝")
                return True
        return False

    def _collect_upstream_outputs(self, unit: Unit, results: dict) -> dict:
        """收集上游 Unit 的輸出"""
        outputs = {}
        for dep_id in unit.depends_on:
            # 確保 dep_id 是 str 型別（L1 Disassembly 的 JSON 可能产出 int）
            dep_key = str(dep_id) if not isinstance(dep_id, str) else dep_id
            result = results.get(dep_key)
            if result and result.status == UnitStatus.SUCCESS:
                outputs[dep_key] = result.output
                #print(f"[DEBUG Executor] Unit {unit.unit_id} 收集上游 Unit {dep_key} 輸出: {result.output[:100]}...")
        if not outputs:
            pass
            #print(f"[DEBUG Executor] Unit {unit.unit_id} 的 depends_on={unit.depends_on}, upstream_outputs=空, 所有 depends_on 類型={[type(d) for d in unit.depends_on]}")
        return outputs

    def _get_tools_for_server(self, server_name: Optional[str],
                              server_schemas: dict) -> list:
        """取得指定 MCP Server 的 tool function 列表"""
        if not server_name:
            return []
        return server_schemas.get(server_name, [])
