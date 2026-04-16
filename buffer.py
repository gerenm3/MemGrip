import config

def estimate_tokens(text):
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    others = len(text) - chinese

    return chinese * 2 + others // 3

class ConversationBuffer:
    def __init__(self):
        self.context: list[dict] = []
        self.flushed: list[dict] = []
        self.token_limit = config.BUFFER_MAX_TOKENS

    def add(self, role, content):
        self.context.append({"role": role, "content": content})
        self.check()

    def check(self):
        while len(self.context) > 2:
            if (self.token_limit<sum(estimate_tokens(m["content"]) for m in self.context)):
                if self.context[0]["role"] == "user":
                    self.flushed.append(self.context.pop(0))
                    self.flushed.append(self.context.pop(0))
                else:
                    self.flushed.append(self.context.pop(0))
            else:
                break

    def storage(self):
        flushed = list(self.flushed)
        self.flushed.clear()
        
        return flushed

    def get(self):
        return list(self.context)
