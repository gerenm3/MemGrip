class ConversationSummary:
    def __init__(self):
        self.summary: str = ""
        self.temp_cache: list[dict] = []

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