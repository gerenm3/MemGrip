class ConversationSummary:
    def __init__(self):
        self.summary: str = ""
        self.temp_cache: list[dict] = ""

    def build_summary_messages(self, prompt: str, flushed: list[dict])-> list[dict]:
        messages = [{"role": "system", "content": prompt}]
        turns = []
        for r in flushed:
            turns.append(f"{r['role']}: {r['content']}")
        text = "\n---\n".join(turns)
        text =  "[OLD SUMMARY]" + self.summary + "[/OLD SUMMARY]" + "[CONVERSATION]" + text + "[/CONVERSATION]"
        messages.append({"role": "user", "content": text})
        return messages

    def build_check_messages(self, prompt: str)-> list[dict]:
        messages = [{"role": "system", "content": prompt}]
        text =  "[SUMMARY]" + self.summary + "[/SUMMARY]"
        messages.append({"role": "user", "content": text})
        return messages

    def receive_summary(self, text):
        self.summary = text

    def get_summary(self):
        return self.summary
    
    def receive_cache(self, flushed: list):
        self.temp_cache.extend(flushed)
    
    def get_cache(self):
        return self.temp_cache
    
    def flush_cache(self):
        temp_cache = list(self.temp_cache)
        self.temp_cache.clear()
        return temp_cache