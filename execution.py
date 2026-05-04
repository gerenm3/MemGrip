"""
MemGrip v5 - Execution Manager (Complex Flow)
蜂巢式隔離架構：每個 unit 是獨立蜂巢，資料只能透過 requires 接口流動。
"""
import re
import json
import asyncio
import mcp_client
import config
from dataclasses import dataclass, field


# ============================================================
# Data Structures
# ============================================================

@dataclass
class ExecutionUnit:
    id: int
    content: str
    tools: list
    depends_on: list
    requires: list
    output_type: str
    steps: list = field(default_factory=list)  # List[Execution]
    input: str = ""
    output: str = ""
    status: str = "pending"

@dataclass
class Execution:
    id: int           # L2 時為局部 id，全局化後為 "X-Y" 字串
    content: str
    tools: list
    depends_on: list
    requires: list
    output_type: str
    input: str = ""
    output: str = ""


# ============================================================
# Execution Manager
# ============================================================

class ExecutionManager:
    def __init__(self, mcp_client, medium_model=config.MEDIUM_MODEL_NAME, large_model=config.LARGE_MODEL_NAME):
        self.mcp = mcp_client
        self.local_model = medium_model
        self.cloud_model = large_model
        self.max_retries = config.MAX_RETRIES

    # ----------------------------------------------------------
    # 物理脫殼
    # ----------------------------------------------------------
    def _strip_tags(self, text: str) -> str:
        if not text: return ""
        text = re.sub(r'<[^>]+>', '', str(text))
        noise_list = ["(操作完畢，資料讀取結束)", "--- END OF DATA ---", "[數據探針]"]
        for noise in noise_list:
            text = text.replace(noise, "")
        return text.strip()

    # ----------------------------------------------------------
    # 感知環境
    # ----------------------------------------------------------
    async def _get_env_snapshot(self, server_name: str) -> str:
        reg_entry = mcp_client.SERVER_REGISTRY.get(server_name)
        if not reg_entry or "probe" not in reg_entry:
            return ""
        probe = reg_entry["probe"]
        try:
            raw_res = await self.mcp.call_tool(server_name, probe["tool"], probe["args"])
            return f"\n[ENVIRONMENT_STATE] <{server_name}>\n{raw_res}\n</{server_name}>\n"
        except Exception as e:
            print(f"[Orch Warning] 感知失敗 ({server_name}): {e}")
            return ""

    # ----------------------------------------------------------
    # 物理提煉層
    # ----------------------------------------------------------
    async def _distill_observation(self, mcp_result) -> str:
        if hasattr(mcp_result, 'content'):
            texts = [block.text for block in mcp_result.content if hasattr(block, 'text')]
            content = "\n".join(texts)
        else:
            content = str(mcp_result)
        if not content.strip():
            return "(系統訊息：該操作回傳內容為空。)"
        return f"{content}\n(操作完畢，資料讀取結束)"

    # ----------------------------------------------------------
    # 虛擬工具定義: finish_task
    # ----------------------------------------------------------
    def _get_finish_task_definition(self, preserve_raw=False) -> dict:
        if preserve_raw:
            func_desc = "【任務終結-資料傳遞模式】當你透過其他工具成功獲取目標資料後，必須呼叫此工具，將獲取到的內容原封不動地傳遞下去。"
            param_desc = "必須【一字不漏地完整複製】原始資料的完整內容。嚴禁任何摘要、省略、截斷或加上你自己的解釋。"
        else:
            func_desc = "【任務終結】當你獲得足夠資訊或確認任務無法完成時，必須呼叫此工具並提供 final_conclusion。"
            param_desc = "對任務結果的最終總結與分析"
        return {
            "type": "function",
            "function": {
                "name": "finish_task",
                "description": func_desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "final_conclusion": {"type": "string", "description": param_desc}
                    },
                    "required": ["final_conclusion"]
                }
            }
        }

    # ===========================================================
    # Tool Flow (策略 B) - 保持不變
    # ===========================================================
    async def execute_strategy_tool(self, target_server, execution_intent, tools, call_model_func, build_msg_func, execute_tool_func):
        env_snapshot = await self._get_env_snapshot(target_server)
        input_data = "[TASK]" + execution_intent + "[/TASK]" + "[SNAPSHOT]" + env_snapshot + "[/SNAPSHOT]"
        messages = build_msg_func(config.TOOL_EXECUTION_PROMPT, input_data)
        tools = tools + [self._get_finish_task_definition(preserve_raw=False)]

        for i in range(self.max_retries):
            content, tool_calls = await call_model_func(
                model=self.local_model,
                messages=messages,
                temperature=0.0,
                max_tokens=config.TOOL_EXECUTION_MAX_TOKENS,
                think=config.TOOL_EXECUTION_THINK,
                tools=tools
            )

            assistant_msg = {"role": "assistant", "content": content or ""}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    t.model_dump() if hasattr(t, 'model_dump') else t
                    for t in tool_calls
                ]
            messages.append(assistant_msg)

            if not tool_calls:
                messages.append({
                    "role": "user",
                    "content": "指令提醒：請直接調用工具執行，若已完成請調用 'finish_task'。不要只提供文字計畫。"
                })
                continue

            for tool in tool_calls:
                t_name = tool.function.name
                t_args = tool.function.arguments
                if t_name == "finish_task":
                    conclusion = t_args.get("final_conclusion", "模型未提供詳細結論。")
                    return self._strip_tags(conclusion)
                raw_obs = await execute_tool_func(t_name, t_args)
                clean_obs = await self._distill_observation(raw_obs)
                messages.append({"role": "tool", "content": clean_obs, "name": t_name})

            messages.append({
                "role": "system",
                "content": f"當前目標：{execution_intent}。若資訊已飽和，請調用 finish_task。"
            })

        return "達到最大遞迴步數限制。"

    # ===========================================================
    # Complex Flow (策略 C) - 蜂巢式隔離
    # ===========================================================
    async def execute_strategy_complex(self, units, server_schemas, call_model_func, build_msg_func, execute_tool_func):
        """
        三階段流水線：
        1. L2 全部規劃（大模型）
        2. 全局 ID 化
        3. L3 全部執行（中模型）+ 閉環修正
        """

        # ======= 階段一：L2 全部規劃 =======
        completed = set()
        while len(completed) < len(units):
            progress = False
            for unit in units:
                if unit.id in completed:
                    continue
                if not all(dep in completed for dep in unit.depends_on):
                    continue

                success = await self._plan_steps(unit, units, server_schemas, call_model_func, build_msg_func)
                if not success:
                    raise Exception(f"Unit {unit.id} 規劃階段失敗")

                completed.add(unit.id)
                progress = True
            if not progress:
                raise Exception("依賴死鎖")

        # ======= 階段二：全局 ID 化 =======
        for unit in units:
            self._globalize_steps(unit)

        print(units)

        # ======= 階段三：L3 全部執行 =======
        outputs = {}  # 全局 outputs dict
        completed_l3 = set()
        while len(completed_l3) < len(units):
            progress = False
            for unit in units:
                if unit.id in completed_l3:
                    continue
                if not all(dep in completed_l3 for dep in unit.depends_on):
                    continue

                # 建立虛擬 entry（跨 unit 資料注入）
                for req_id in unit.requires:
                    out_id = f"{req_id}-out"
                    req_unit = next((u for u in units if u.id == req_id), None)
                    if req_unit and req_unit.output and out_id not in outputs:
                        outputs[out_id] = req_unit.output

                # 環境快照
                env_snapshot = ""
                for server_name in unit.tools:
                    env_snapshot += await self._get_env_snapshot(server_name)

                # 閉環修正：L3 失敗 → 回 L2 重規劃（最多 2 次）
                error_msg = None
                for l2_retry in range(3):  # 首次 + 2 次重規劃
                    if l2_retry > 0:
                        # L2 重規劃
                        success = await self._plan_steps(
                            unit, units, server_schemas,
                            call_model_func, build_msg_func,
                            error_msg=error_msg
                        )
                        if not success:
                            raise Exception(f"Unit {unit.id} 重規劃失敗")
                        self._globalize_steps(unit)

                    isSuccessful, error_msg = await self._run_steps(
                        unit, outputs, server_schemas, env_snapshot,
                        call_model_func, build_msg_func, execute_tool_func
                    )
                    if isSuccessful:
                        break
                else:
                    raise Exception(f"Unit {unit.id} 閉環修正失敗：{error_msg}")

                # 取 GLOBAL step 結果作為 unit 輸出
                global_step = next((s for s in unit.steps if s.output_type == "GLOBAL"), None)
                if global_step and global_step.id in outputs:
                    unit.output = outputs[global_step.id]
                    outputs[f"{unit.id}-out"] = unit.output

                completed_l3.add(unit.id)
                progress = True
            if not progress:
                raise Exception("依賴死鎖")

        # ======= 結果整合 =======
        global_units = [u for u in units if u.output_type == "GLOBAL"]
        if len(global_units) == 1:
            return global_units[0].output
        else:
            return [{"unit_id": u.id, "task": u.content, "output": u.output} for u in global_units]

    # ----------------------------------------------------------
    # L2: 規劃單一 unit 的 steps
    # ----------------------------------------------------------
    async def _plan_steps(self, unit, units, server_schemas, call_model_func, build_msg_func, error_msg=None):
        """L2 規劃：大模型將 unit 轉換為原子步驟"""

        # 1. Probe
        env_snapshot = ""
        for server_name in unit.tools:
            env_snapshot += await self._get_env_snapshot(server_name)

        # 2. 工具列表（過濾 finish_task）
        tools = []
        for server_name in unit.tools:
            tools.extend(server_schemas.get(server_name, []))
        tools = [t for t in tools if t["function"]["name"] != "finish_task"]

        # 3. 上游 output 描述
        upstream_desc = ""
        for req_id in unit.requires:
            req_unit = next((u for u in units if u.id == req_id), None)
            if req_unit and req_unit.steps:
                last_step = req_unit.steps[-1]
                upstream_desc += f"Unit {req_id} 的輸出：{last_step.output}\n"

        input_desc = unit.input
        if upstream_desc:
            input_desc += f"\n來源格式：{upstream_desc}"

        # 4. 組裝 message
        input_data = (
            f"[TASK]{unit.content}[/TASK]"
            f"[INPUT]{input_desc}[/INPUT]"
            f"[OUTPUT]{unit.output}[/OUTPUT]"
            f"[ENVIRONMENT]{env_snapshot}[/ENVIRONMENT]"
            f"[TOOLS]{json.dumps(tools, ensure_ascii=False)}[/TOOLS]"
        )
        if error_msg:
            input_data += f"\n[ERROR]上次執行失敗原因：{error_msg}。請重新規劃步驟以避免相同問題。[/ERROR]"

        messages = build_msg_func(config.STEP_PLAN_PROMPT, input_data)

        # 5. 呼叫大模型 + 解析 + 驗證（retry 2 次）
        for attempt in range(2):
            steps_raw, _ = await call_model_func(
                model=self.cloud_model,
                messages=messages,
                temperature=config.STEP_TEMPERATURE,
                max_tokens=config.STEP_MAX_TOKENS,
                think=config.STEP_THINK,
            )
            print(steps_raw)

            # 解析 JSON（支援 array 和 object）
            try:
                match_arr = re.search(r'\[.*\]', steps_raw, re.DOTALL)
                match_obj = re.search(r'\{.*\}', steps_raw, re.DOTALL)
                if match_arr:
                    step_list = json.loads(match_arr.group())
                elif match_obj:
                    step_list = [json.loads(match_obj.group())]
                else:
                    step_list = []
            except json.JSONDecodeError:
                print(f"[Warning] L2 JSON 解析失敗")
                continue

            # 欄位驗證
            steps = []
            required_fields = {"id", "content", "tools", "depends_on", "requires", "output_type"}
            valid = True
            for step in step_list:
                if not required_fields.issubset(step.keys()):
                    print(f"[Warning] 欄位缺失: {required_fields - step.keys()}")
                    valid = False
                    break
                steps.append(Execution(**step))
            if not valid:
                continue

            # 工具驗證
            available_tools = {t["function"]["name"] for t in tools}
            valid_steps = steps and all(
                tool in available_tools
                for step in steps
                for tool in step.tools
            )
            if valid_steps:
                unit.steps = steps
                return True

        return False

    # ----------------------------------------------------------
    # 全局 ID 化
    # ----------------------------------------------------------
    def _globalize_steps(self, unit):
        """將局部 step ID 轉換為全局 ID（"X-Y" 格式）"""
        valid_ids = {str(s.id) for s in unit.steps}

        for step in unit.steps:
            old_id = str(step.id)
            new_id = f"{unit.id}-{old_id}"

            # 過濾無效引用 + 轉換 ID
            step.requires = [
                f"{unit.id}-{str(r)}" for r in step.requires
                if str(r) in valid_ids and str(r) != old_id
            ]
            step.depends_on = [
                f"{unit.id}-{str(d)}" for d in step.depends_on
                if str(d) in valid_ids and str(d) != old_id
            ]
            step.id = new_id

        # 跨 unit 資料注入：unit.requires 的外部資料注入所有 step
        # 不需要額外處理 — _run_steps 的雙通道注入會自動處理

    # ----------------------------------------------------------
    # L3: 執行單一 unit 的所有 steps（蜂巢）
    # ----------------------------------------------------------
    async def _run_steps(self, unit, outputs, server_schemas, env_snapshot, call_model_func, build_msg_func, execute_tool_func):
        """
        蜂巢執行：
        - step 可見資料 = unit.requires 注入的外部資料 + step.requires 的同 unit step 輸出
        - 工具 step → agentic loop（step_results 優先）
        - 推理 step → 單次呼叫
        """

        # 建立 unit 可用工具索引
        all_tools = {}
        for server_name in unit.tools:
            for schema in server_schemas.get(server_name, []):
                all_tools[schema["function"]["name"]] = schema

        for step in unit.steps:
            # === 資料注入（雙通道）===
            data_blocks = ""

            # 通道 1: 同 unit step 資料（step.requires）
            for req_id in step.requires:
                if req_id in outputs:
                    data_blocks += f"[DATA id={req_id}]{outputs[req_id]}[/DATA]\n"

            # 通道 2: 跨 unit 外部資料（unit.requires → 所有 step 共享）
            for req_id in unit.requires:
                out_id = f"{req_id}-out"
                if out_id in outputs:
                    data_blocks += f"[DATA id={out_id}]{outputs[out_id]}[/DATA]\n"

            # === 組裝輸入 ===
            input_data = (
                f"[TASK]{step.content}[/TASK]\n"
                f"[INPUT]{step.input}[/INPUT]\n"
                f"[OUTPUT]{step.output}[/OUTPUT]\n"
                f"[ENVIRONMENT]{env_snapshot}[/ENVIRONMENT]\n"
                f"{data_blocks}"
            )

            print(f"[DEBUG] step.id={step.id}, step.requires={step.requires}")
            print(f"[DEBUG] outputs keys={list(outputs.keys())}")
            print(f"\n[DEBUG] L3 input_data:---------------------------------------------------------------\n {input_data}\n[\\DEBUG]--------------------------------------------------------------\n")

            # === 分流執行 ===
            if step.tools:
                # ---- 工具步驟：Agentic Loop ----
                step_tools = [all_tools[name] for name in step.tools if name in all_tools]
                step_tools.append(self._get_finish_task_definition(preserve_raw=True))
                messages = build_msg_func(config.STEP_EXECUTE_PROMPT, input_data)

                finished = False
                step_results = []  # 存放所有工具原始回傳

                for i in range(self.max_retries):
                    content, tool_calls = await call_model_func(
                        model=self.local_model,
                        messages=messages,
                        temperature=config.STEP_EXECUTE_TEMPERATURE,
                        max_tokens=config.STEP_EXECUTE_MAX_TOKENS,
                        think=config.STEP_EXECUTE_THINK,
                        tools=step_tools
                    )
                    print(f"[DEBUG] Loop {i}: content={content[:100]}, tool_calls={tool_calls}")

                    assistant_msg = {"role": "assistant", "content": content or ""}
                    if tool_calls:
                        assistant_msg["tool_calls"] = [
                            t.model_dump() if hasattr(t, 'model_dump') else t
                            for t in tool_calls
                        ]
                    messages.append(assistant_msg)

                    if not tool_calls:
                        messages.append({
                            "role": "user",
                            "content": "指令提醒：請直接調用工具執行，若已完成請調用 'finish_task'。不要只提供文字計畫。"
                        })
                        continue

                    # 工具執行
                    for tool in tool_calls:
                        t_name = tool.function.name
                        t_args = tool.function.arguments

                        # 攔截 finish_task
                        if t_name == "finish_task":
                            # 優先使用工具原始回傳，避免模型摘要化
                            if step_results:
                                result = "\n".join(step_results)
                            else:
                                conclusion = t_args.get("final_conclusion", "模型未提供詳細結論。")
                                result = self._strip_tags(conclusion)
                            outputs[step.id] = result
                            step.output = result
                            finished = True
                            break

                        # 物理調用
                        raw_obs = await execute_tool_func(t_name, t_args)
                        clean_obs = await self._distill_observation(raw_obs)
                        step_results.append(clean_obs)  # 存入原始回傳
                        messages.append({"role": "tool", "content": clean_obs, "name": t_name})

                    if not finished:
                        messages.append({
                            "role": "system",
                            "content": f"當前目標：{step.content}。若資訊已飽和，請調用 finish_task。"
                        })
                    if finished:
                        break
                else:
                    return False, f"Step {step.id} 達到最大重試次數"

            else:
                # ---- 推理步驟：單次呼叫 ----
                messages = build_msg_func(config.STEP_EXECUTE_PROMPT, input_data)
                result, _ = await call_model_func(
                    model=self.local_model,
                    messages=messages,
                    temperature=config.STEP_EXECUTE_TEMPERATURE,
                    max_tokens=config.STEP_EXECUTE_MAX_TOKENS,
                    think=config.STEP_EXECUTE_THINK,
                    tools=None
                )
                result = self._strip_tags(result)
                outputs[step.id] = result
                step.output = result

        return True, None