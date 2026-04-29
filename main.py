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

class orchestrator:
    def __init__(self, trace_logger, optimization_advisor):
        self.buffer = ConversationBuffer()
        self.summary = ConversationSummary()
        self.vector = ConversationVector()

        self.unit_manager = ExecutionManager()
        self.trace_logger = trace_logger
        self.optimization_advisor = optimization_advisor

        self.patterns = self._pattern_load()

    async def orchestrator_main(self):
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
                print("Exiting.")
                break
            intent = await self.route(user_input)
            rag_content = ""
            reply = ""
            if intent['need_rag']: 
                rag_content = self.vector.search(await self._call_embedding(config.EMBEDDING_MODEL_NAME, user_input), 1)[0]

            if intent['intent'] == "tool":
                intent['intent'] = "complex"

            match intent['intent']:
                case "simple":
                    messages = self._build_messages(config.SYSTEM_PROMPT, user_input, rag_content)
                    reply = await self._call_model(config.MEDIUM_MODEL_NAME, messages, config.TEMPERATURE, config.MAX_TOKENS, config.THINK)

                case "complex":
                    try:
                        # 規劃階段（大模型）
                        messages = self._build_messages(config.CLARIFY_PROMPT, user_input, rag_content)
                        task_description = await self._call_model(
                            config.LARGE_MODEL_NAME, messages,
                            config.TEMPERATURE, config.MAX_TOKENS, config.THINK
                        )
                        print(f"[DEBUG] task_description: {task_description}")

                        messages = self._build_execution_messages(config.DISASSEMBLY_PROMPT, task_description, config.AVAILABLE_TOOLS, {})
                        disassembly_reply = await self._call_model(
                            config.LARGE_MODEL_NAME, messages,
                            config.DISASSEMBLY_TEMPERATURE, config.DISASSEMBLY_MAX_TOKENS, config.DISASSEMBLY_THINK
                        )
                        
                        print(f"[DEBUG] disassembly_reply: {disassembly_reply}")
                        units = parse_json_array(disassembly_reply)
                        print(f"[DEBUG] parsed units: {units}")

                        if units:
                            for unit in units:
                                self.unit_manager.add_unit(unit)

                            for next_unit in self.unit_manager.tasklist:
                                inputs = {}
                                step_tool_names = []
                                for server_name in next_unit.tools:
                                    for tool_schema in self.server_schemas.get(server_name, []):
                                        func_name = tool_schema["function"]["name"]
                                        func_desc = tool_schema["function"]["description"]
                                        step_tool_names.append(json.dumps(tool_schema["function"], ensure_ascii=False))

                                env_info = self._build_environment_info(next_unit.tools)
                                messages = self._build_execution_messages(config.STEP_PROMPT, next_unit.content, step_tool_names, inputs, env_info)
                                
                                #print(f"[DEBUG] step_plan_messages unit {next_unit.id}: {json.dumps(messages, ensure_ascii=False)}")

                                step_plan_reply = await self._call_model(
                                    config.LARGE_MODEL_NAME, messages,
                                    config.STEP_TEMPERATURE, config.STEP_MAX_TOKENS, config.STEP_THINK,
                                )
                                
                                print(f"[DEBUG] step_plan_reply: {step_plan_reply}")

                                steps = parse_json_array(step_plan_reply)

                                available_tools = set()
                                for server_name in next_unit.tools:
                                    for tool_schema in self.server_schemas.get(server_name, []):
                                        available_tools.add(tool_schema["function"]["name"])

                                def valid_steps(s):
                                    return s and all(
                                        tool in available_tools
                                        for step in s
                                        for tool in step.get("tools", [])
                                    )

                                if not valid_steps(steps):
                                    step_plan_reply = await self._call_model(
                                        config.LARGE_MODEL_NAME, messages,
                                        config.STEP_TEMPERATURE, config.STEP_MAX_TOKENS, config.STEP_THINK,
                                    )
                                    steps = parse_json_array(step_plan_reply)

                                if steps and valid_steps(steps):
                                    valid_keys = {"id", "content", "tools", "depends_on", "requires", "output_type"}
                                    next_unit.steps = [Execution(**{k: v for k, v in step.items() if k in valid_keys}) for step in steps]
                                else:
                                    raise Exception(f"step plan failed: unit {next_unit.id} returned empty plan")


                            # 執行階段（中模型）
                            for unit in self.unit_manager.tasklist:
                                step_manager = ExecutionManager()
                                inputs = self.unit_manager.get_inputs(unit.requires)

                                for step in unit.steps:
                                    step_manager.add_unit(vars(step))

                                for next_step in step_manager.tasklist:
                                    step_inputs = step_manager.get_inputs(next_step.requires)
                                    all_inputs = {**inputs, **step_inputs}

                                    server_names = [self.tool_registry.get(func) for func in next_step.tools if self.tool_registry.get(func)]

                                    env_info = self._build_environment_info(server_names)
                                    messages = self._build_execution_messages(
                                        config.STEP_EXECUTE_PROMPT,
                                        next_step.content,
                                        next_step.tools,
                                        all_inputs,
                                        env_info
                                    )

                                    step_tools = []
                                    for func_name in next_step.tools:
                                        server_name = self.tool_registry.get(func_name)
                                        if server_name:
                                            matching = [t for t in self.server_schemas[server_name] if t["function"]["name"] == func_name]
                                            step_tools.extend(matching)

                                    if next_step.tools and not step_tools:
                                        raise Exception(f"tool matching failed: step {next_step.id} requested {next_step.tools} but none found in registry")
                                    #print(f"messages: {messages}\n")
                                    #print(f"step_tools:{step_tools}\n")
                                    step_reply = await self._call_model(
                                        config.MEDIUM_MODEL_NAME, messages,
                                        config.STEP_EXECUTE_TEMPERATURE, config.STEP_EXECUTE_MAX_TOKENS, config.STEP_EXECUTE_THINK,
                                        tools=step_tools if step_tools else None
                                    )
                                    step_manager.complete(next_step.id, output=step_reply)


                                if len(step_manager.results) == 1:
                                    unit_output = list(step_manager.results.values())[0]["output"]
                                else:
                                    step_integration_messages = self._build_integration_messages(
                                        config.STEP_INTEGRATION_PROMPT, unit.content, step_manager.results
                                    )
                                    unit_output = await self._call_model(
                                        config.MEDIUM_MODEL_NAME, step_integration_messages,
                                        config.INTEGRATION_TEMPERATURE, config.INTEGRATION_MAX_TOKENS, config.INTEGRATION_THINK
                                    )

                                self.unit_manager.complete(unit.id, output=unit_output)

                                print(f"[DEBUG] unit {unit.id} output: {repr(unit_output)}")

                            # 單元層 INTEGRATION
                            messages = self._build_integration_messages(
                                config.INTEGRATION_PROMPT, task_description, self.unit_manager.results
                            )
                            reply = await self._call_model(
                                config.MEDIUM_MODEL_NAME, messages,
                                config.INTEGRATION_TEMPERATURE, config.INTEGRATION_MAX_TOKENS, config.INTEGRATION_THINK
                            )
                            self.unit_manager.clear()
                            if not reply:
                                raise Exception("complex flow failed: empty reply")

                    except Exception as e:
                        reply = f"[Error] complex flow failed: {e}"

                case "tool":
                    pass
            
            flushed = self.buffer.storage()
            if flushed: await self.summarize(flushed)
            self.buffer.add("user", user_input)
            self.buffer.add("assistant", reply)        
            print(f"MemGrip: {reply}\n")

    async def _call_model(self, model: str, messages: list[dict], temperature: float, max_tokens: int, think: bool, tools: list = None) -> str:
        client = ollama.AsyncClient()
        response = await client.chat(
                model=model,
                messages=messages,
                think=think,
                tools=tools,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                }
            )
        
        #print(f"[DEBUG] tool_calls: {response['message'].get('tool_calls')}")

        if response["message"].get("tool_calls"):
            tool_call = response["message"]["tool_calls"][0]
            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"]["arguments"]
            #print(f"[DEBUG] 執行工具: {tool_name}, 參數: {tool_args}")

            tool_result = await self._execute_tool(tool_name, tool_args)
            print(f"[DEBUG] 工具結果: {tool_result}")
            return tool_result
        
        return response["message"]["content"]

    async def _call_embedding(self, model: str, input: str) -> list:
        client = ollama.AsyncClient()
        response = await client.embed(
                model=model,
                input=input,
        )    
        return response["embeddings"]
    
    def _build_messages(self, prompt: str, user_input: str, rag_context: str = None) -> list[dict]:
        system_content = prompt
        system_content += f"\n[SUMMARY]{self.summary.get_summary()}[/SUMMARY]"

        buffer_text = self.buffer.serialize()
        if buffer_text:
            system_content += f"\n[BUFFER]{buffer_text}[/BUFFER]"

        if rag_context:
            system_content += f"\n[RAG]{rag_context}[/RAG]"

        messages = [{"role": "system", "content": system_content}]
        messages.append({"role": "user", "content": user_input})
        return messages
    
    def _build_summary_messages(self, prompt: str, flushed: list[dict]) -> list[dict]:
        messages = [{"role": "system", "content": prompt}]
        turns = []
        for r in flushed:
            role = "用戶" if r["role"] == "user" else "助理"
            turns.append(f"{role}：{r['content']}")
        text = "\n".join(turns)
        text = f"[OLD SUMMARY]{self.summary.get_summary()}[/OLD SUMMARY][CONVERSATION]{text}[/CONVERSATION]"
        messages.append({"role": "user", "content": text})
        return messages

    def _build_check_messages(self, prompt: str)-> list[dict]:
        messages = [{"role": "system", "content": prompt}]
        text =  "[SUMMARY]" + self.summary.get_summary() + "[/SUMMARY]"
        messages.append({"role": "user", "content": text})
        return messages

    def _build_routing_messages(self, prompt: str, user_input: str) -> list[dict]:
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content": user_input}]
        return messages

    def _build_execution_messages(self, prompt: str, content: str, tools: list, inputs: dict, env_info: str = "") -> list[dict]:
        #messages = [{"role": "system", "content": prompt.format(tools="\n".join(f"- {t}" for t in tools))}]
        messages = [{"role": "system", "content": prompt.format(tools="\n".join(tools))}]
        user_content = ""
        if env_info:
            user_content += f"[ENVIRONMENT]{env_info}[/ENVIRONMENT]"
        user_content += "[INTENT]" + content + "[/INTENT]"
        for req_id, output in inputs.items():
            user_content += f"[DATA id={req_id}]" + output + f"[/DATA]"
        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_integration_messages(self, prompt: str, task_description: str, results: dict) -> list[dict]:
        messages = [{"role": "system", "content": prompt}]
        unit_outputs = list(results.values())
        content = "[TASK]" + task_description + "[/TASK]"
        content += "\n[OUTPUTS]" + json.dumps(unit_outputs, ensure_ascii=False) + "[/OUTPUTS]"
        messages.append({"role": "user", "content": content})
        return messages

    def _build_environment_info(self, server_names: list = None) -> str:
        env = config.TOOL_ENVIRONMENT if server_names is None else {k: v for k, v in config.TOOL_ENVIRONMENT.items() if k in server_names}
        lines = []
        for tool, info in env.items():
            details = ", ".join(f"{k}：{v}" for k, v in info.items() if k != "description")
            line = f"{tool}: {info['description']}"
            if details:
                line += f"（{details}）"
            lines.append(line)
        return "\n".join(lines)

    async def route(self, user_input: str) -> dict:
        matched = self._pattern_match(user_input)
        if matched: return matched

        # 第一次呼叫：判斷 intent
        messages = self._build_routing_messages(config.ROUTE_INTENT_PROMPT, user_input)
        intent_result = await self._call_model(config.ROUTER_MODEL_NAME, messages, config.ROUTE_TEMPERATURE, config.ROUTE_MAX_TOKENS, False)
        
        # 第二次呼叫：判斷 need_rag
        messages = self._build_routing_messages(config.ROUTE_RAG_PROMPT, user_input)
        rag_result = await self._call_model(config.ROUTER_MODEL_NAME, messages, config.ROUTE_TEMPERATURE, config.ROUTE_MAX_TOKENS, False)
        
        try:
            intent_match = re.search(r'\{.*?\}', intent_result, re.DOTALL)
            rag_match = re.search(r'\{.*?\}', rag_result, re.DOTALL)

            intent_data = json.loads(intent_match.group()) if intent_match else {}
            rag_data = json.loads(rag_match.group()) if rag_match else {}

            intent = intent_data.get("intent", "complex")

            need_rag_raw = rag_data.get("need_rag", True)
            if isinstance(need_rag_raw, str):
                need_rag = need_rag_raw.lower() == "true"
            else:
                need_rag = bool(need_rag_raw)
            print(f"[DEBUG] intent: {intent}")
            return {"intent": intent, "need_rag": need_rag}

        except (json.JSONDecodeError, AttributeError, TypeError):
            return {"intent": "complex", "need_rag": True}
        

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
        self.summary.receive_cache(flushed)
        messages = self._build_summary_messages(config.SUMMARY_PROMPT, flushed)
        summary = (await self._call_model(config.MEDIUM_MODEL_NAME, messages, config.SUMMARY_TEMPERATURE, config.SUMMARY_MAX_TOKENS, False))
        self.summary.receive_summary(summary)
        embedded = await self._call_embedding(config.EMBEDDING_MODEL_NAME, summary)
        if self.vector.compare(embedded) > config.SIMILARITY_THRESHOLD:return
        messages = self._build_check_messages(config.IMPORTANCE_PROMPT)
        text = await self._call_model(config.MEDIUM_MODEL_NAME, messages, config.SUMMARY_TEMPERATURE, config.SUMMARY_MAX_TOKENS, False)
        match = re.search(r'\d+\.?\d*', text)
        if not match:return
        if float(match.group()) < config.IMPORTANCE_THRESHOLD:return
        self.vector.add(summary, flushed, embedded)

    async def _init_tools(self):
        self.tool_registry = {}
        self.server_schemas = {}
        
        for server_name in mcp_client.SERVER_REGISTRY:
            tools = await mcp_client.get_tools(server_name)
            self.server_schemas[server_name] = [self._mcp_tool_to_ollama(tool) for tool in tools]
            for tool in tools:
                self.tool_registry[tool.name] = server_name

    def _mcp_tool_to_ollama(self, tool) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        }

    async def _execute_tool(self, tool_name: str, tool_args: dict) -> str:
        server_name = self.tool_registry.get(tool_name)
        if not server_name:
            return f"[Error] 未知工具：{tool_name}"
        return await mcp_client.call_tool(server_name, tool_name, tool_args)


def parse_json_array(text: str):
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if not match:
        return None
    raw = match.group()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fixed = raw.replace('\n', '\\n').replace('\t', '\\t')
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return None

@dataclass
class Execution:
    id: int
    content: str
    tools: list  
    depends_on: list
    requires: list
    output_type: str

@dataclass
class ExecutionUnit:
    id: int
    content: str
    tools: list
    depends_on: list
    requires: list
    output_type: str
    steps: list = field(default_factory=list)

class ExecutionManager:
    def __init__(self):
        self.tasklist: list[ExecutionUnit] = []
        self.results = {}
        self.outputs = {}

    def add_unit(self, input: dict):
        valid_keys = {"id", "content", "tools", "depends_on", "requires", "output_type"}
        filtered = {k: v for k, v in input.items() if k in valid_keys}
        self.tasklist.append(ExecutionUnit(**filtered))
    
    def get_unit_content(self, id: int) -> str:
        for unit in self.tasklist:
            if unit.id == id:
                return unit.content
        return ""
    
    def get_inputs(self, requires: list) -> dict:
        return {req_id: self.outputs[req_id] for req_id in requires if req_id in self.outputs}

    def complete(self, id: int, output: str = "", results: dict = None):
        for unit in self.tasklist:
            if unit.id == id:
                if results:
                    if unit.output_type == "GLOBAL":
                        self.results.update(results)
                    else:
                        for k, v in results.items():
                            self.outputs[k] = v["output"]
                else:
                    if unit.output_type == "GLOBAL":
                        self.results[id] = {"content": unit.content, "output": output}
                    else:
                        self.outputs[id] = output
                break
    
    def clear(self):
        self.tasklist.clear()
        self.results.clear()
        self.outputs.clear()


if __name__ == "__main__":
    o = orchestrator(trace_logger=None, optimization_advisor=None)
    asyncio.run(o.orchestrator_main())