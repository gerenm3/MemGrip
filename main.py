"""
MemGrip - Entry Point
Basic chat loop with Ollama backend.
Memory layer will be integrated in Week 2-3.
"""

import time
import ollama
import config
import json
import re
from buffer import ConversationBuffer
from summary import ConversationSummary
from vector import ConversationVector

class orchestrator:
    def __init__(self, task_manager, trace_logger, optimization_advisor):
        self.buffer = ConversationBuffer()
        self.summary = ConversationSummary()
        self.vector = ConversationVector()

        self.task_manager = task_manager
        self.trace_logger = trace_logger
        self.optimization_advisor = optimization_advisor

        self.patterns = self._pattern_load()

    def orchestrator_main(self):
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
        intent = self.route(user_input)
        if intent['need_rag']: 

            rag = self.vector.search(self._call_embedding(config.EMBEDDING_MODEL_NAME, user_input))
        

    def _call_model(self, model: str, messages: list[dict], temperature: float, max_tokens: int, think: bool) -> str:
        response = ollama.chat(
                model=model,
                messages=messages,
                think=think,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                }
            )
        return response["message"]["content"]

    def _call_embedding(self, model: str, input: str) -> list:
        response = ollama.embed(
                model=model,
                input=input,
        )    
        return response["embeddings"]
    
    def _build_messages(self, prompt: str, user_input: str, rag_context: str = None) -> list[dict]:
        if not rag_context: rag_context = ""
        messages = [{"role": "system", "content": "[PROMPT]" + prompt + "[/PROMPT]" + "[MEMORY]" + self.summary.get() + rag_context + "[/MEMORY]"}]
        messages.extend(self.buffer.get())
        messages.append({"role": "user", "content": user_input})
        return messages
    
    def _build_routing_messages(self, prompt: str, user_input: str) -> list[dict]:
        messages = [{"role": "system", "content": "[PROMPT]" + prompt + "[/PROMPT]"}, {"role": "user", "content": user_input}]
        return messages


    def route(self, user_input: str) -> dict:
        matched = self._pattern_match(user_input)
        if matched: return matched

        messages = self._build_routing_messages(config.ROUTE_PROMPT, user_input)
        routed = self._call_model(config.ROUTER_MODEL_NAME, messages , config.ROUTE_TEMPERATURE, config.ROUTE_MAX_TOKENS, False)
        
        try:
            match = re.search(r'\{.*\}', routed, re.DOTALL)
            if match:
                return json.loads(match.group())
        except:
            pass
        return {"intent": "complex", "need_rag": False}
        

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
    
    def summarize(self, flushed: list) -> None:
        self.summary.receive_cache(flushed)
        messages = self.summary.build_summary_messages(config.SUMMARY_PROMPT, flushed)
        summary = (self._call_model(config.MEDIUM_MODEL_NAME, messages, config.SUMMARY_TEMPERATURE, config.SUMMARY_MAX_TOKENS, False))
        self.summary.receive_summary(summary)
        embedded = self._call_embedding(config.EMBEDDING_MODEL_NAME, summary)
        if self.vector.compare(embedded) > config.SIMILARITY_THRESHOLD:return
        messages = self.summary.build_check_messages(config.IMPORTANCE_PROMPT)
        text = self._call_model(config.MEDIUM_MODEL_NAME, messages, config.SUMMARY_TEMPERATURE, config.SUMMARY_MAX_TOKENS, False)
        match = re.search(r'\d+\.?\d*', text)
        if not match:return
        if float(match.group()) < config.IMPORTANCE_THRESHOLD:return
        self.vector.add(summary, flushed, embedded)


"""
def build_messages(system_prompt: str, buffer: list, summary: str, user_input: str) -> list:
    messages = [{"role": "system", "content": "[PROMPT]" + system_prompt + "[/PROMPT]" + "[MEMORY]" + summary + "[/MEMORY]"}]
    messages.extend(buffer)
    messages.append({"role": "user", "content": user_input})
    return messages


def chat_loop():
    print(f"MemGrip ({config.MODEL_NAME}) — type 'exit' to quit\n")

    buffer = ConversationBuffer()
    summary = ConversationSummary()

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

        messages = build_messages(config.SYSTEM_PROMPT, buffer.get(), summary.get(), user_input)
        t1 = time.time()
        try:
            response = ollama.chat(
                model=config.MODEL_NAME,
                messages=messages,
                think=False,
                options={
                    "temperature": config.TEMPERATURE,
                    "num_predict": config.MAX_TOKENS,
                }
            )
            reply = response["message"]["content"]
        except Exception as e:
            print(f"[Error] {e}")
            continue
        t2 = time.time()
        print('time elapsed: ' + str(t2-t1) + ' seconds')
        buffer.add("user", user_input)
        buffer.add("assistant", reply)
        summary.retrieval(buffer.storage())
        print(f"MemGrip: {reply}\n")



"""
if __name__ == "__main__":
    pass