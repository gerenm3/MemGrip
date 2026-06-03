"""v2 executor — L3 執行.

依據 §3.6 (Executor) 定義：
- 只負責 execute(step, upstream_outputs) -> Result
- 使用 MEDIUM_MODEL_NAME
- 不做 replan，不做驗證
- 符合 v2 logging 規範
"""

import asyncio
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional

import config
from clients.message_builder import MessageBuilder
from core.health import log_action
from core.json_utils import parse_first_json
from core.prompts import STEP_EXECUTE_PROMPT
from models.blueprints import Step, Result

logger = logging.getLogger(__name__)


class Executor:
    """L3 執行器：負責執行單一 Step"""

    def __init__(
        self,
        call_model_func: Optional[Callable[..., Awaitable[Result]]] = None,
        execute_tool_func: Optional[Callable[..., Awaitable[Result]]] = None,
    ) -> None:
        self.call_model_func = call_model_func
        self.execute_tool_func = execute_tool_func

    async def execute(
        self,
        step: Step,
        upstream_outputs: Dict[str, str],
        environment: str = "",
    ) -> Result:
        """執行單一 Step（含 Agentic Loop).

        Args:
            step: 要執行的 Step
            upstream_outputs: 上游輸出 {id: output}
            environment: 環境資訊（如工作目錄路徑），注入 system prompt

        Returns:
            Result(data={"output": str, "loop_count": int})
        """
        log_action("executor", "step_start", "OK", step.step_id)

        # 前置條件檢查：upstream_depends 對應的上游單元輸出是否缺失
        upstream_output_keys = set(upstream_outputs.keys())
        for udep in step.upstream_depends:
            udep_str = str(udep) if not isinstance(udep, str) else udep
            if udep_str not in upstream_output_keys:
                logger.warning("[Executor] step=%s 上游單元輸出缺失: %s", step.step_id, udep_str)
                log_action("executor", "step_failed", "FAILED", step.step_id + ": 上游單元輸出缺失", "前置條件檢查失敗")
                return Result(success=False, error=f"上游單元輸出缺失: {udep_str}")

        # 前置條件檢查：depends_on 對應的前置步驟輸出是否缺失
        for dep_id in step.depends_on:
            dep_str = str(dep_id) if not isinstance(dep_id, str) else dep_id
            if dep_str not in upstream_output_keys:
                logger.warning("[Executor] step=%s 前置步驟輸出缺失: %s", step.step_id, dep_str)
                log_action("executor", "step_failed", "FAILED", step.step_id + ": 前置步驟輸出缺失", "前置條件檢查失敗")
                return Result(success=False, error=f"前置步驟輸出缺失: {dep_str}")

        resolved_goal = self._resolve_unit_placeholders(step.goal, upstream_outputs)
        tool_instruction = self._build_tool_instruction(step)
        role = config.BASE_ROLES.get("step_execute", "")
        system_content = STEP_EXECUTE_PROMPT.format(
            role=role,
            step_goal=resolved_goal,
            tool_instruction=tool_instruction,
            environment=environment,
        )

        user_messages = self._build_user_messages(upstream_outputs)
        conversation = [{"role": "system", "content": system_content}] + user_messages
        tools_arg = [step.tool] if step.tool is not None else None

        max_iterations = getattr(config, 'STEP_EXECUTE_MAX_ITERATIONS', 5)
        loop_count = 0
        successful_tool_results: List[str] = []
        tool_errors: List[str] = []

        for _ in range(max_iterations):
            loop_count += 1

            try:
                result = await asyncio.wait_for(
                    self.call_model_func(
                        config.MEDIUM_MODEL_NAME,
                        conversation,
                        config.STEP_EXECUTE_TEMPERATURE,
                        config.STEP_EXECUTE_MAX_TOKENS,
                        config.STEP_EXECUTE_THINK,
                        tools=tools_arg,
                        caller="executor",
                    ),
                    timeout=config.LLM_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error("[Executor] LLM call timed out (%ds)", config.LLM_TIMEOUT)
                log_action("executor", "step_failed", "FAILED", step.step_id + ": LLM 呼叫逾時", "Step 執行逾時")
                return Result(success=False, error=f"LLM 呼叫逾時 ({config.LLM_TIMEOUT}s)")
            except Exception as e:
                logger.error("[Executor] LLM call failed: %s", e, exc_info=True)
                log_action("executor", "step_failed", "FAILED", step.step_id + ": " + str(e), "Step 執行失敗")
                return Result(success=False, error=str(e))

            content = result.data or ""
            tool_calls = result.tool_calls or []

            if not tool_calls:
                # 模型沒有回傳 tool calls，結束 loop
                break

            # 執行 tool calls
            if self.execute_tool_func:
                for tc in tool_calls:
                    parsed = self._format_tool_call(tc)
                    if parsed is None:
                        continue
                    t_name = parsed["name"]
                    t_args = self._parse_tool_arguments(parsed["arguments"])

                    assistant_msg: dict = {
                        "role": "assistant",
                        "content": content or "",
                        "tool_calls": [{"function": {"name": t_name, "arguments": t_args}}],
                    }

                    tool_result = await self.execute_tool_func(t_name, t_args)
                    if tool_result:
                        if not getattr(tool_result, 'success', True):
                            tool_errors.append(f"工具 {t_name} 失敗: {getattr(tool_result, 'error', '未知錯誤')}")
                        content_str = tool_result.data if hasattr(tool_result, 'data') else str(tool_result)
                        successful_tool_results.append(f"[{t_name}]\n{content_str}")

                    tool_msg = {
                        "role": "tool",
                        "content": f"[工具回傳]\n{content_str}",
                        "tool_name": t_name,
                    }

                    conversation.append(assistant_msg)
                    conversation.append(tool_msg)

        # 檢查是否達到迭代上限且有工具錯誤
        if loop_count >= max_iterations and tool_errors:
            error_parts = []
            if tool_errors:
                error_parts.append("工具錯誤：" + "; ".join(tool_errors))
            log_action("executor", "step_failed", "FAILED", step.step_id + ": 工具執行錯誤", "Agentic loop 達上限")
            return Result(success=False, error="\n".join(error_parts) or "執行達上限")

        # 組合最終輸出
        output = content
        if successful_tool_results:
            output = content + "\n\n" + "\n\n".join(successful_tool_results)

        # 清洗工具回傳內容本身可能含有的系統標記
        output = re.sub(r'\[[\w]+\]\n(?!\n)', '', output)

        # 清理多餘空白行
        while '\n\n\n' in output:
            output = output.replace('\n\n\n', '\n\n')
        output = output.strip()

        log_action("executor", "step_success", "OK", step.step_id)
        return Result(success=True, data={"output": output, "loop_count": loop_count})

    @staticmethod
    def _resolve_unit_placeholders(goal: str, upstream_outputs: Dict[str, str]) -> str:
        """將 goal 中的 <unit:id> 標記替換為可讀標籤.

        對 upstream_outputs 中存在的 unit id 使用「單元 N」替換；
        對不存在的 unit id 替換為「上游單元 N 未執行，無可用輸出」。
        與 V1 的 _resolve_unit_placeholders 保持一致行為。
        """
        # 先處理已存在的 upstream outputs
        for uid in upstream_outputs:
            uid_str = str(uid) if not isinstance(uid, str) else uid
            placeholder = f"<unit:{uid_str}>"
            goal = goal.replace(placeholder, f"單元 {uid_str}")
        # 再處理殘留的 <unit:N>（上游未執行）
        def _replace_missing(m: re.Match) -> str:
            nid = m.group(1)
            if str(nid) in upstream_outputs:
                return f"單元 {nid}"
            return f"上游單元 {nid} 未執行，無可用輸出"
        goal = re.sub(r'<unit:(\d+)>', _replace_missing, goal)
        return goal

    @staticmethod
    def _build_tool_instruction(step: Step) -> str:
        """建構 tool instruction，包含工具的完整描述與參數說明.
        
        將工具的 name、description、parameters 注入 system prompt，
        確保模型理解工具的使用方法，即使 tools 參數未完全生效也能正確調用。
        """
        if not step.tool:
            return "本步驟為純推理，不得調用任何工具。"
        
        if isinstance(step.tool, dict):
            func = step.tool.get("function", {})
            if isinstance(func, dict):
                tool_name = func.get("name", "unknown")
                tool_desc = func.get("description", "")
                tool_params = func.get("parameters", {})
                
                instruction_parts = [
                    f"使用工具 {tool_name}，調用後將回傳內容直接輸出。",
                ]
                
                if tool_desc:
                    instruction_parts.append(f"工具說明: {tool_desc}")
                
                if tool_params:
                    instruction_parts.append(f"工具參數結構: {tool_params}")
                
                return "\n".join(instruction_parts)
        
        # 若 step.tool 不是 dict 格式，回傳基本指令
        return f"使用工具 {step.tool}，調用後將回傳內容直接輸出。"

    @staticmethod
    def _build_user_messages(upstream_outputs: Dict[str, str]) -> List[dict]:
        """建構 user messages：將所有 upstream outputs 合併為單一 message.

        upstream_outputs 為空時回傳空 list，不注入任何內容。
        """
        if not upstream_outputs:
            return []
        parts = []
        for uid, output in upstream_outputs.items():
            parts.append(f"[來自上游 {uid}]\n{output}")
        content = "\n\n".join(parts)
        return [{"role": "user", "content": f"[輸入資料]\n{content}"}]

    @staticmethod
    def _format_tool_call(tc: Any) -> Optional[dict]:
        """將 tool_call 轉換為統一的 {name, arguments} 格式."""
        if hasattr(tc, "function"):
            func = tc.function
            return {"name": func.name, "arguments": func.arguments}
        if isinstance(tc, dict):
            formatted = {
                "name": tc.get("function", {}).get("name", ""),
                "arguments": tc.get("function", {}).get("arguments", {}),
            }
            return formatted if formatted["name"] else None
        return None

    @staticmethod
    def _parse_tool_arguments(raw: Any) -> dict:
        """解析 tool arguments：支援 str (JSON) 或 dict."""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            parsed = parse_first_json(raw)
            if isinstance(parsed, dict):
                return parsed
        return {}