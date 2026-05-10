"""Orchestrator — 路由 + 流程協調"""

import asyncio
import config
import json
import re
import time
from typing import Dict, Any, List, Optional
from memory import ConversationBuffer, ConversationSummary, ConversationVector
from clients.model_client import OllamaClient
from clients.message_builder import MessageBuilder


class Orchestrator:
    """Orchestrator：路由 + 流程協調"""

    def __init__(self, trace_logger=None, optimization_advisor=None):
        self.buffer = ConversationBuffer()
        self.summary = ConversationSummary()
        self.vector = ConversationVector()
        self.client = OllamaClient()
        
        # Complex 流程用的內建 scheduler（用 memory_manager 取代）
        self._complex_units = {}  # unit_id → UnitInstance（複雜流程用）
        
        self.trace_logger = trace_logger
        self.optimization_advisor = optimization_advisor
        self.patterns = self._pattern_load()
        self.tool_registry = {}
        self.server_schemas = {}

    async def run(self):
        """主循環"""
        await self._init_tools()
        print(f"MemGrip — type 'exit' to quit\n")
        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                break

            # 分流階段
            route_result = await self.route(user_input)
            intent = route_result['intent']
            need_rag = route_result['need_rag']

            # 上下文準備
            rag_content = ""
            if need_rag:
                query_vector = await self._call_embedding(config.EMBEDDING_MODEL_NAME, user_input)
                search_results = self.vector.search(query_vector, top_k=1)
                rag_content = search_results[0] if search_results else ""

            # Intent 分流
            reply = ""
            if intent == "simple":
                messages = MessageBuilder.build_dialog(
                    config.SYSTEM_PROMPT, user_input,
                    self.summary.get_summary(), self.buffer.serialize(), rag_content
                )
                raw_reply = await self._call_model(
                    config.MEDIUM_MODEL_NAME, messages,
                    config.TEMPERATURE, config.MAX_TOKENS, config.THINK
                )
                reply = raw_reply[0] if isinstance(raw_reply, tuple) else raw_reply
            
            elif intent == "tool":
                reply = await self._execute_tool_intent(
                    user_input=user_input,
                    rag_content=rag_content,
                    server_schemas=self.server_schemas
                )
                
            elif intent == "complex":
                reply = await self._execute_complex(
                    user_input=user_input,
                    rag_content=rag_content,
                    server_schemas=self.server_schemas
                )

            self.buffer.add("user", user_input)
            self.buffer.add("assistant", reply)
            flushed = self.buffer.storage()
            if flushed:
                await self.summarize(flushed)
            print(f"MemGrip: {reply}\n")

    async def _call_model(self, model: str, messages: list, temperature: float, max_tokens: int, think: bool, tools: list = None):
        #print(f"\n[debug]------------------------------------------------------\n{model}")
        #print(f"\n[debug]------------------------------------------------------")
        #print(f"\n{messages}")
        #print(f"\n[debug]------------------------------------------------------")
        response = await self.client.client.chat(
            model=model,
            messages=messages,
            tools=tools,
            think=think,
            options={"temperature": temperature, "num_predict": max_tokens}
        )
        message = response.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])
        
        print(f"\n[debug]------------------------------------------------------")
        print(f"\n{content}")
        print(f"\n[debug]------------------------------------------------------")
        if tool_calls:
            print(f"\n[debug]------------------------------------------------------")
            print(f"\n{tool_calls}")
            print(f"\n[debug]------------------------------------------------------")
        return content, tool_calls

    async def _call_embedding(self, model: str, input_text: str) -> list:
        #print(f"\n[debug]呼叫模型------------\n{model}------------------------------\n{input_text}-----------------------\n")
        response = await self.client.client.embed(model=model, input=input_text)
        return response.get("embeddings", [])

    async def route(self, user_input: str) -> dict:
        """分流核心"""
        matched = self._pattern_match(user_input)
        if matched:
            return matched

        intent_json = await self._get_router_decision(config.ROUTE_INTENT_PROMPT, user_input)
        intent = intent_json.get("intent", "complex")

        rag_json = await self._get_router_decision(config.ROUTE_RAG_PROMPT, user_input)
        need_rag = rag_json.get("need_rag", True)

        if isinstance(need_rag, str):
            need_rag = need_rag.lower() == "true"

        print(f"[DEBUG] Router Result -> Intent: {intent}, RAG: {need_rag}")
        return {"intent": intent, "need_rag": bool(need_rag)}

    async def _get_router_decision(self, prompt: str, user_input: str) -> dict:
        messages = MessageBuilder.build_task(prompt, user_input)
        content, _ = await self._call_model(
            config.ROUTER_MODEL_NAME, messages,
            config.ROUTE_TEMPERATURE, config.ROUTE_MAX_TOKENS, False
        )
        try:
            match = re.search(r'\{.*?\}', content, re.DOTALL)
            return json.loads(match.group()) if match else {}
        except (json.JSONDecodeError, AttributeError):
            return {}

    async def _clarify(self, user_input: str) -> dict:
        """Clarify：將 user_input 轉成結構化欄位"""
        buffer_text = self.buffer.serialize() or ""
        summary_text = self.summary.get_summary() or ""

        input_parts = []
        if buffer_text:
            input_parts.append(f"[BUFFER]{buffer_text}[/BUFFER]")
        if summary_text:
            input_parts.append(f"[SUMMARY]{summary_text}[/SUMMARY]")
        input_parts.append(f"[USER_INPUT]{user_input}[/USER_INPUT]")
        input_text = "\n".join(input_parts)

        messages = MessageBuilder.build_task(config.CLARIFY_PROMPT, input_text)
        content, _ = await self._call_model(
            config.MEDIUM_MODEL_NAME, messages,
            config.CLARIFY_TEMPERATURE, config.CLARIFY_MAX_TOKENS, False
        )
        try:
            match = re.search(r'\{.*?\}', content, re.DOTALL)
            return json.loads(match.group()) if match else {}
        except (json.JSONDecodeError, AttributeError):
            return {"goal": user_input, "entities": [], "scope": "", "constraints": [], "rules": [], "success_criteria": "", "questions": []}

    async def _execute_complex(self, user_input: str, rag_content: str, server_schemas: dict) -> str:
        """Complex 流程：Clarify → L1 戰略拆解 → L2 戰術規劃 → 拓撲排序 → L3 執行 → 最終整合"""

        # 1. Clarify：將 user_input 轉成結構化欄位
        clarify_result = await self._clarify(user_input)
        clarify_goal = clarify_result.get("goal", user_input)
        clarify_entities = clarify_result.get("entities", [])
        clarify_scope = clarify_result.get("scope", "")
        clarify_constraints = clarify_result.get("constraints", [])
        clarify_rules = clarify_result.get("rules", [])
        clarify_success_criteria = clarify_result.get("success_criteria", "")
        clarify_questions = clarify_result.get("questions", [])

        # 若有需要澄清的問題，向用戶提問
        if clarify_questions:
            return "需要您進一步說明：\n" + "\n".join(f"- {q}" for q in clarify_questions)

        # 2. L1 戰略拆解：將任務拆成 Units
        from models.blueprints import Unit
        from core.planner import Planner
        from core.storage import UnitStore
        from core.executor import Executor
        from core.integrator import Integrator

        l1_prompt = config.DISASSEMBLY_PROMPT
        input_text = f"[GOAL]{clarify_goal}[/GOAL]\n"
        if clarify_scope:
            input_text += f"[SCOPE]{clarify_scope}[/SCOPE]\n"
        if clarify_constraints:
            input_text += f"[CONSTRAINTS]{json.dumps(clarify_constraints, ensure_ascii=False)}[/CONSTRAINTS]\n"
        if clarify_rules:
            input_text += f"[USER_RULES]{json.dumps(clarify_rules, ensure_ascii=False)}[/USER_RULES]\n"
        if clarify_success_criteria:
            input_text += f"[SUCCESS_CRITERIA]{clarify_success_criteria}[/SUCCESS_CRITERIA]\n"
        if clarify_entities:
            input_text += f"[ENTITIES]{json.dumps(clarify_entities, ensure_ascii=False)}[/ENTITIES]\n"
        input_text += f"[RAG]{rag_content if rag_content else '無'}[/RAG]"
        
        # 注入 {tools} 到 prompt 中（只需 server 名稱列表）
        server_names = list(server_schemas.keys())
        l1_prompt = l1_prompt.replace("{tools}", json.dumps(server_names, ensure_ascii=False, indent=2))

        messages = MessageBuilder.build_task(l1_prompt, input_text)
        
        content, _ = await self._call_model(
            config.LARGE_MODEL_NAME, messages,
            config.DISASSEMBLY_TEMPERATURE, config.DISASSEMBLY_MAX_TOKENS,
            config.DISASSEMBLY_THINK
        )

        # 解析 Units：先嘗試直接解析整段 content，失敗再用 bracket 提取
        units_data = None

        # 嘗試 1：直接解析整段 content
        if not units_data:
            try:
                units_data = json.loads(content)
            except json.JSONDecodeError:
                pass

        # 嘗試 2：找最外層的 [ ... ]（包含所有 nested structures）
        if not units_data:
            first_bracket = content.find('[')
            last_bracket = content.rfind(']')
            if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
                json_str = content[first_bracket:last_bracket+1]
                try:
                    units_data = json.loads(json_str)
                except json.JSONDecodeError as e:
                    units_data = None

        # 解析失敗：回傳 debug 日誌
        if not units_data:
            preview = content[:500].replace('\n', ' ').strip()
            return f"任務拆解 JSON 解析失敗。LLM 回傳內容前 500 字：{preview}"

        units = []
        for u in units_data:
            unit = Unit(
                unit_id=str(u.get("id", "")),
                goal=u.get("content", ""),
                expected_input=u.get("expected_input", []),
                expected_output=u.get("expected_output", []),
                depends_on=u.get("depends_on", []),
                mcp_server=u.get("mcp_server"),
                output_type=u.get("output_type", "INTERNAL")
            )
            units.append(unit)

        if not units:
            return "未產生任何執行單元。"

        # 2. 初始化 UnitStore
        unit_store = UnitStore()

        # 3. L3 執行所有 Units
        executor = Executor(
            call_model_func=self._call_model,
            execute_tool_func=self._execute_tool
        )
        results = await executor.execute_units(units, server_schemas, unit_store)

        # 4. 過濾只有 L1 指定的 GLOBAL units 給 Integrator
        global_unit_ids = {u.unit_id for u in units if u.output_type in ("CONTENT", "ACTION")}
        filtered_results = {uid: r for uid, r in results.items() if uid in global_unit_ids}

        # 5. 最終整合
        integrator = Integrator(call_model_func=self._call_model)
        reply = await integrator.integrate(user_input, filtered_results, units)

        return reply

    def _pattern_load(self):
        with open(config.PATTENRS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [{"regex": item[0], "intent": item[1], "need_rag": item[2]} for item in raw]

    def _pattern_match(self, user_input: str) -> Optional[dict]:
        matched_patterns = []
        for pattern in self.patterns:
            if re.search(pattern['regex'], user_input):
                matched_patterns.append(pattern)
        if len(matched_patterns) != 1:
            return None
        p = matched_patterns[0]
        return {"intent": p['intent'], "need_rag": p['need_rag']}

    async def _init_tools(self):
        """初始化工具清單 + 綁定執行層"""
        import tools.mcp_client as mcp_client
        self.tool_registry = {}
        self.server_schemas = {}
        for server_name in mcp_client.SERVER_REGISTRY.keys():
            try:
                tools = await mcp_client.get_tools(server_name)
                processed_schemas = []
                for tool in tools:
                    schema = self._mcp_tool_to_ollama(tool)
                    if tool.name == "write_file":
                        schema["function"]["description"] += " (警告：此操作為完全覆寫)"
                    processed_schemas.append(schema)
                    self.tool_registry[tool.name] = server_name
                self.server_schemas[server_name] = processed_schemas
            except Exception as e:
                print(f"[Warning] 伺服器 {server_name} 工具初始化失敗: {e}")

    def _mcp_tool_to_ollama(self, mcp_tool) -> dict:
        return {
            "type": "function",
            "function": {
                "name": mcp_tool.name,
                "description": mcp_tool.description,
                "parameters": mcp_tool.inputSchema
            }
        }

    async def _execute_tool(self, tool_name: str, tool_args: dict) -> str:
        """執行單一工具"""
        server_name = self.tool_registry.get(tool_name)
        if not server_name:
            return f"[Error] 找不到工具 {tool_name} 對應的伺服器"
        
        import tools.mcp_client as mcp_client
        return await mcp_client.call_tool(server_name, tool_name, tool_args)

    async def _execute_tool_intent(self, user_input: str, rag_content: str, server_schemas: dict) -> str:
        """Tool 意圖：Clarify → PROBE_ROUTER → Agentic Loop"""
        # 1. Clarify：只取 goal 和 questions
        clarify_result = await self._clarify(user_input)
        clarify_goal = clarify_result.get("goal", user_input)
        clarify_questions = clarify_result.get("questions", [])

        # 若有需要澄清的問題，向用戶提問
        if clarify_questions:
            return "需要您進一步說明：\n" + "\n".join(f"- {q}" for q in clarify_questions)

        # 2. PROBE_ROUTER：根據 clarify_goal 挑選最適合的 MCP server
        server_names = list(server_schemas.keys())
        probe_messages = MessageBuilder.build_task(
            config.PROBE_ROUTER_PROMPT.format(server_list=json.dumps(server_names, ensure_ascii=False, indent=2)),
            clarify_goal
        )
        probe_content, _ = await self._call_model(
            config.ROUTER_MODEL_NAME, probe_messages,
            config.ROUTE_TEMPERATURE, config.ROUTE_MAX_TOKENS, False
        )
        selected_server = probe_content.strip().strip('"').strip()
        
        # 若無法判斷，預設使用 file_rw
        if selected_server not in server_schemas:
            selected_server = "file_rw"
        
        # 只取選中的 server 的工具清單
        all_tools = server_schemas.get(selected_server, [])

        system_prompt = config.TOOL_EXECUTION_PROMPT.format(tools=json.dumps(all_tools, ensure_ascii=False, indent=2))
        context = f"[USER_INPUT]{clarify_goal}[/USER_INPUT]\n"
        if rag_content:
            context += f"[RAG]{rag_content}[/RAG]\n"

        conversation = [{"role": "system", "content": system_prompt}, {"role": "user", "content": context}]

        # 使用 L3 直接執行（agentic loop）
        max_iterations = 15
        for _ in range(max_iterations):
            content, tool_calls = await self._call_model(
                config.MEDIUM_MODEL_NAME,
                conversation,
                getattr(config, 'TOOL_EXECUTION_TEMPERATURE', 0.3),
                getattr(config, 'TOOL_EXECUTION_MAX_TOKENS', 8192),
                getattr(config, 'TOOL_EXECUTION_THINK', True),
                all_tools if all_tools else None
            )

            if tool_calls:
                # 1. 把模型的回應加回對話
                assistant_msg = {"role": "assistant", "content": content or ""}
                formatted_calls = []
                for tc in tool_calls:
                    if hasattr(tc, 'function'):
                        formatted_calls.append({
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        })
                    else:
                        formatted_calls.append(tc)
                assistant_msg["tool_calls"] = formatted_calls
                conversation.append(assistant_msg)

                # 2. 執行工具，回傳用 role: "tool"
                for tool_call in tool_calls:
                    if hasattr(tool_call, 'function'):
                        t_name = tool_call.function.name
                        t_args = tool_call.function.arguments
                    elif isinstance(tool_call, dict):
                        t_name = tool_call.get('function', {}).get('name', '')
                        t_args = tool_call.get('function', {}).get('arguments', {})
                    else:
                        continue

                    if isinstance(t_args, str):
                        try:
                            t_args = json.loads(t_args)
                        except (json.JSONDecodeError, TypeError):
                            t_args = {}

                    tool_result = await self._execute_tool(t_name, t_args)
                    conversation.append({
                        "role": "tool",
                        "content": str(tool_result),
                        "tool_name": t_name
                    })
                continue

            # 沒有工具調用，生成最終回覆
            reply_conv = conversation + [{
                "role": "system",
                "content": f"[GOAL]{user_input}[/GOAL]\n[EXECUTION_LOG]\n最後輸出結果給用戶。\n[/EXECUTION_LOG]\n請根據以上執行結果，生成一份自然、完整的回覆給用戶。回覆應清晰總結完成的工作，並直接回應用戶的需求。"
            }]
            final_reply, _ = await self._call_model(
                config.MEDIUM_MODEL_NAME,
                reply_conv,
                getattr(config, 'TOOL_EXECUTION_TEMPERATURE', 0.3),
                getattr(config, 'TOOL_EXECUTION_MAX_TOKENS', 8192),
                getattr(config, 'TOOL_EXECUTION_THINK', True)
            )
            return final_reply

        return "工具調用次數已達上限。"

    async def summarize(self, flushed: list) -> None:
        """記憶壓縮"""
        self.summary.receive_cache(flushed)
        turns = [f"{'用戶' if r['role'] == 'user' else '助理'}：{r['content']}" for r in flushed]
        summary_msgs = MessageBuilder.build_meta(config.SUMMARY_PROMPT, {
            "OLD_SUMMARY": self.summary.get_summary(),
            "CONVERSATION": "\n".join(turns)
        })
        summary_text, _ = await self._call_model(
            config.MEDIUM_MODEL_NAME, summary_msgs,
            config.SUMMARY_TEMPERATURE, config.SUMMARY_MAX_TOKENS, False
        )
        self.summary.receive_summary(summary_text)

        embedded = await self._call_embedding(config.EMBEDDING_MODEL_NAME, summary_text)
        if self.vector.compare(embedded) > config.SIMILARITY_THRESHOLD:
            return

        check_msgs = MessageBuilder.build_meta(config.IMPORTANCE_PROMPT, {
            "SUMMARY": self.summary.get_summary()
        })
        check_result, _ = await self._call_model(
            config.MEDIUM_MODEL_NAME, check_msgs,
            config.SUMMARY_TEMPERATURE, config.SUMMARY_MAX_TOKENS, False
        )
        match = re.search(r'\d+\.?\d*', check_result)
        if not match:
            return
        if float(match.group()) < config.IMPORTANCE_THRESHOLD:
            return
        self.vector.add(summary_text, flushed, embedded)
