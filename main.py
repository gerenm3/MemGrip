"""
MemGrip - Entry Point
Basic chat loop with Ollama backend.
Memory layer will be integrated in Week 2-3.
"""

import mcp_client
import asyncio
import ollama
import config
import json
import re
from buffer import ConversationBuffer
from summary import ConversationSummary
from vector import ConversationVector
from dataclasses import dataclass, field
from execution import ExecutionManager, ExecutionUnit

class orchestrator:
    def __init__(self, trace_logger, optimization_advisor):
        self.buffer = ConversationBuffer()
        self.summary = ConversationSummary()
        self.vector = ConversationVector()
        self.client = ollama.AsyncClient()
        self.execution = ExecutionManager(mcp_client=mcp_client)
        self.trace_logger = trace_logger
        self.optimization_advisor = optimization_advisor

        self.patterns = self._pattern_load()

    async def orchestrator_main(self):
        # 1. 啟動時的物理準備
        await self._init_tools()
        print(f"MemGrip — type 'exit' to quit\n")

        while True:
            try:
                user_input = input("You: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting.")
                break

            if not user_input: continue
            if user_input.lower() in ("exit", "quit"): break
            
            # 2. 分流階段：判定意圖與 RAG 需求
            route_result = await self.route(user_input)
            intent = route_result['intent']
            need_rag = route_result['need_rag']

            # 3. 上下文準備：僅在需要時調用 Embedding 與 Vector 檢索
            rag_content = ""

            if need_rag: 
                query_vector = await self._call_embedding(config.EMBEDDING_MODEL_NAME, user_input)
                search_results = self.vector.search(query_vector, limit=1)
                rag_content = search_results[0] if search_results else ""

            # 4. intent分流階段
            reply = ""
            if intent == "tool": intent= "complex"
            match intent:
                case "simple":
                    messages = self._build_dialog_messages(config.SYSTEM_PROMPT, user_input, rag_content)
                    raw_reply = await self._call_model(config.MEDIUM_MODEL_NAME, messages, config.TEMPERATURE, config.MAX_TOKENS, config.THINK)
                    reply = raw_reply[0] if isinstance(raw_reply, tuple) else raw_reply

                case "tool":
                    prep = await self._prepare_tool_execution(user_input, rag_content)
                    srv = prep['target_server']
                    tools = self.server_schemas.get(srv, [])
                    reply = await self.execution.execute_strategy_tool(
                        target_server=srv,
                        execution_intent=prep['refined_intent'], 
                        tools=tools,
                        call_model_func=self._call_model,  
                        build_msg_func=self._build_task_messages, 
                        execute_tool_func=self._execute_tool
                    )

                case "complex":
                    # --- 1. 任務澄清與戰略拆解 (L1) ---
                    messages = self._build_dialog_messages(config.CLARIFY_COMPLEX_PROMPT, user_input, rag_content)
                    clarify_json, _ = await self._call_model(config.LARGE_MODEL_NAME, messages, 0.1, 1200, False)
                    clarify_data = self._parse_json(clarify_json)

                    # 獲取單元清單 (Units)
                    messages = self._build_task_messages(config.DISASSEMBLY_PROMPT.format(tools=config.AVAILABLE_TOOLS), f"[TASK]{json.dumps(clarify_data)}[/TASK]")
                    units_raw, _ = await self._call_model(
                        config.LARGE_MODEL_NAME, 
                        messages, 
                        config.DISASSEMBLY_TEMPERATURE, 
                        config.DISASSEMBLY_MAX_TOKENS, 
                        config.DISASSEMBLY_THINK
                    )             
                    
                    print(units_raw)
                    
                    unit_list = self._parse_json_array(units_raw)
                    units = [ExecutionUnit(**u) for u in unit_list]
                    
                    global_bus = await self.execution.execute_strategy_complex(
                        units=units, 
                        server_schemas=self.server_schemas,
                        call_model_func=self._call_model,  
                        build_msg_func=self._build_task_messages, 
                        execute_tool_func=self._execute_tool
                    )


                    integration_input = f"[TASK]{json.dumps(clarify_data)}[/TASK]\n[UNIT_RESULTS]{json.dumps(global_bus)}[/UNIT_RESULTS]"
                    messages = self._build_task_messages(config.INTEGRATION_PROMPT, integration_input)
                    reply, _ = await self._call_model(
                        config.MEDIUM_MODEL_NAME,
                        messages,
                        config.INTEGRATION_TEMPERATURE,
                        config.INTEGRATION_MAX_TOKENS,
                        config.INTEGRATION_THINK
                    )
                    
                
            self.buffer.add("user", user_input)
            self.buffer.add("assistant", reply) 
            flushed = self.buffer.storage()
            if flushed: await self.summarize(flushed)  
            print(f"MemGrip: {reply}\n")

    async def _call_model(self, model: str, messages: list[dict], temperature: float, max_tokens: int, think: bool, tools: list = None):
        response = await self.client.chat(
            model=model,
            messages=messages,
            tools=tools,
            think=think,
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        )
        message = response.get("message", {})
        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])
        
        return content, tool_calls

    async def _call_embedding(self, model: str, input: str) -> list:
        response = await self.client.embed(
                model=model,
                input=input,
        )    
        return response["embeddings", []]
    
    # --- 底層通用核心 ---
    def _build_core_messages(self, system_prompt: str, user_content: str) -> list[dict]:
        """最底層的封裝，確保 role 結構統一"""
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

    # --- 1. 任務執行類 (Task Mode) ---
    def _build_task_messages(self, prompt: str, user_input: str) -> list[dict]:
        """
        適用：Router 判定、Execution (策略 B/C L3)
        特性：絕對去噪，不含 SUMMARY/BUFFER，確保模型注意力集中於指令與事實。
        """
        return self._build_core_messages(prompt, user_input)

    # --- 2. 交互對話類 (Dialog Mode) ---
    def _build_dialog_messages(self, prompt: str, user_input: str, rag_context: str = None) -> list[dict]:
        """
        適用：策略 A (一般對話)、策略 C (L1/L2 規劃)
        特性：注入長期(SUMMARY)與短期(BUFFER)記憶，維持對話連貫性與人設。
        """
        system_content = prompt
        system_content += f"\n[SUMMARY]{self.summary.get_summary()}[/SUMMARY]"
        
        buffer_text = self.buffer.serialize()
        if buffer_text:
            system_content += f"\n[BUFFER]{buffer_text}[/BUFFER]"
            
        if rag_context:
            system_content += f"\n[RAG]{rag_context}[/RAG]"

        user_input = f"[CURRENT_INPUT]\n{user_input}\n[/CURRENT_INPUT]"
        return self._build_core_messages(system_content, user_input)

    # --- 3. 數據審查類 (Meta Mode) ---
    def _build_meta_messages(self, prompt: str, blocks: dict) -> list[dict]:
        """
        適用：Summary 更新、狀態 Check、自我審查
        特性：將數據區塊標籤化後置於 User role，讓模型對資料進行處理。
        """
        formatted_text = "".join([f"[{tag}]{val}[/{tag}]" for tag, val in blocks.items()])
        return self._build_core_messages(prompt, formatted_text)

    async def route(self, user_input: str) -> dict:
        """
        分流核心：兩次請求以確保模型判斷準確率。
        """
        # 1. 模式比對 (Pattern Match)
        matched = self._pattern_match(user_input)
        if matched: return matched

        # 2. 第一次請求：判定 Intent (策略 A/B/C)
        intent_json = await self._get_router_decision(
            config.ROUTE_INTENT_PROMPT, 
            user_input
        )
        intent = intent_json.get("intent", "complex")

        # 3. 第二次請求：判定 RAG 需求
        rag_json = await self._get_router_decision(
            config.ROUTE_RAG_PROMPT, 
            user_input
        )
        need_rag = rag_json.get("need_rag", True)

        # 4. 數據正規化與回傳
        if isinstance(need_rag, str):
            need_rag = need_rag.lower() == "true"
            
        print(f"[DEBUG] Router Result -> Intent: {intent}, RAG: {need_rag}")
        return {"intent": intent, "need_rag": bool(need_rag)}

    # --- 私有輔助工具：處理原子判斷與 JSON 解析 ---
    async def _get_router_decision(self, prompt: str, user_input: str) -> dict:
        """
        執行單次路由判定並解析 JSON。
        """
        # 使用去噪建構器
        messages = self._build_task_messages(prompt, user_input)
        
        # 調用封裝後的模型接口 (複用連接)
        content, _ = await self._call_model(
            model=config.ROUTER_MODEL_NAME,
            messages=messages,
            temperature=config.ROUTE_TEMPERATURE,
            max_tokens=config.ROUTE_MAX_TOKENS,
            think=False
        )
        
        try:
            match = re.search(r'\{.*?\}', content, re.DOTALL)
            return json.loads(match.group()) if match else {}
        except (json.JSONDecodeError, AttributeError):
            return {}

    async def _prepare_tool_execution(self, user_input: str, rag_context: str = None) -> dict:
        """由 9B 模型執行：伺服器定位與意圖提煉 (去噪)"""

        # 呼叫 9B 等級的模型 (MEDIUM_MODEL_NAME)
        messages = self._build_dialog_messages(config.CLARIFY_TOOL_PROMPT, user_input, rag_context)
        content, _ = await self._call_model(
            config.MEDIUM_MODEL_NAME,
            messages, 0.1, 300, True
        )

        intent_data = self._parse_json(content)
        refined_intent = intent_data.get("refined_intent", user_input)
        entities = intent_data.get("entities", [])
        print(f"[DEBUG] Step 1 (Intent) -> {refined_intent} | Entities: {entities}")

        router_prompt = config.PROBE_ROUTER_PROMPT.format(
            server_list=list(self.server_schemas.keys())
        )
        router_input = f"執行意圖：{refined_intent}\n涉及實體：{entities}"

        router_msgs = self._build_task_messages(router_prompt, router_input)
        
        router_raw, _ = await self._call_model(
            config.MEDIUM_MODEL_NAME, router_msgs, 0.1, 200, False
        )
        target_server = router_raw.strip()
        
        print(f"[DEBUG] Step 2 (Router) -> {target_server}")

        return {
            "target_server": target_server,
            "refined_intent": refined_intent
        }

    def _parse_json(self, text: str) -> dict:
        """
        通用的 JSON 解析輔助函數。
        能自動過濾模型輸出的 Markdown 標籤，確保字典正確提取。
        """
        import re
        import json
        try:
            # 使用正則表達式抓取大括號內的內容，支援跨行
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {}
        except Exception as e:
            print(f"[Warning] JSON 解析失敗: {e}")
            print(f"[Warning] 原始文本: {text}")
            return {}

    def _pattern_load(self):
        with open(config.PATTENRS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        patterns = [
            {"regex": item[0], "intent": item[1], "need_rag": item[2]}
            for item in raw
        ]
        return patterns

    def _pattern_match(self, user_input: str) ->dict:
        output = {"intent": "", "need_rag": False}
        count = 0
        for pattern in self.patterns:
            if re.search(pattern['regex'], user_input):
                count+=1
                if count>1:
                    break
                output['intent'] = pattern['intent']
                output['need_rag'] = pattern['need_rag']

        if count != 1: output = None
        return output
    
    async def summarize(self, flushed: list) -> None:
        """
        記憶壓縮與重要性檢查：將過期緩衝轉化為長期記憶與向量索引。
        """
        # 1. 緩存寫入與初步摘要構建
        self.summary.receive_cache(flushed)
        
        # 格式化對話清單供 Meta 模式使用
        turns = [f"{'用戶' if r['role'] == 'user' else '助理'}：{r['content']}" for r in flushed]
        
        # 使用整合後的 Meta 建構器 (行政模式)
        summary_msgs = self._build_meta_messages(config.SUMMARY_PROMPT, {
            "OLD_SUMMARY": self.summary.get_summary(),
            "CONVERSATION": "\n".join(turns)
        })
        
        # 執行摘要生成 (取 content, 忽略 tool_calls)
        summary_text, _ = await self._call_model(
            config.MEDIUM_MODEL_NAME, summary_msgs, 
            config.SUMMARY_TEMPERATURE, config.SUMMARY_MAX_TOKENS, False
        )
        
        # 更新目前摘要狀態
        self.summary.receive_summary(summary_text)

        # 2. 向量化與重複性檢查
        embedded = await self._call_embedding(config.EMBEDDING_MODEL_NAME, summary_text)
        
        # 相似度閾值過濾：若內容與現有向量過於接近則跳過，避免資料冗餘
        if self.vector.compare(embedded) > config.SIMILARITY_THRESHOLD:
            return

        # 3. 重要性判定 (Importance Check)
        check_msgs = self._build_meta_messages(config.IMPORTANCE_PROMPT, {
            "SUMMARY": self.summary.get_summary()
        })
        
        check_result, _ = await self._call_model(
            config.MEDIUM_MODEL_NAME,
            check_msgs, 
            config.SUMMARY_TEMPERATURE,
            config.SUMMARY_MAX_TOKENS,
            False
        )
        
        # 正則提取分數
        match = re.search(r'\d+\.?\d*', check_result)
        if not match: 
            return
            
        # 重要性低於閾值則不進入向量數據庫 (長期存儲)
        if float(match.group()) < config.IMPORTANCE_THRESHOLD:
            return
        
        # 最終持久化存儲
        self.vector.add(summary_text, flushed, embedded)
    
    async def _init_tools(self):
        """
        初始化工具清單：將 MCP 格式轉換為 Ollama 格式並快取。
        """
        self.tool_registry = {}
        self.server_schemas = {}
        
        # 遍歷所有註冊的 MCP 伺服器
        for server_name in mcp_client.SERVER_REGISTRY.keys():
            try:
                # 獲取該伺服器的原始工具清單
                tools = await mcp_client.get_tools(server_name) 
                
                # 轉換並注入描述
                processed_schemas = []
                for tool in tools:
                    schema = self._mcp_tool_to_ollama(tool)
                    
                    if tool.name == "write_file":
                        schema["function"]["description"] += " (警告：此操作為完全覆寫，僅適用於需要完全取代內容的場景。其他情況優先使用 edit_file。)"
                    
                    processed_schemas.append(schema)
                    self.tool_registry[tool.name] = server_name

                self.server_schemas[server_name] = processed_schemas
                    
            except Exception as e:
                print(f"[Warning] 伺服器 {server_name} 工具初始化失敗: {e}")

    def _mcp_tool_to_ollama(self, mcp_tool) -> dict:
        """將 MCP Tool 物件轉換為 Ollama 要求的 JSON Schema 格式[cite: 1]"""
        return {
            "type": "function",
            "function": {
                "name": mcp_tool.name,
                "description": mcp_tool.description,
                "parameters": mcp_tool.inputSchema
            }
        }

    async def _execute_tool(self, tool_name: str, tool_args: dict) -> str:
        """
        執行工具：根據工具名稱路由至對應的 MCP 伺服器。
        """
        server_name = self.tool_registry.get(tool_name)
        
        if not server_name:
            return f"[Error] 未知工具：{tool_name}"
        
        # 透過 MCP Client 進行跨進程/跨網路的物理調用
        # 注意：這裡的 tool_args 應已在外部經過 _clean_tool_args 處理
        try:
            # 確保傳入的是處理過的實體 MCP 結果
            return await mcp_client.call_tool(server_name, tool_name, tool_args)
        except Exception as e:
            return f"[Error] 工具執行失敗: {str(e)}"


    def _parse_json_array(self, text: str) -> list:
        """從模型回覆中提取 JSON 陣列 [ ... ]"""
        try:
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return []
        except Exception as e:
            print(f"[Parser Error] JSON Array 解析失敗: {e}")
            return []

    def _parse_json(self, text: str) -> dict:
        """從模型回覆中提取 JSON 物件 { ... }"""
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {}
        except Exception as e:
            print(f"[Parser Error] JSON Object 解析失敗: {e}")
            return {}


if __name__ == "__main__":
    o = orchestrator(trace_logger=None, optimization_advisor=None)
    asyncio.run(o.orchestrator_main())