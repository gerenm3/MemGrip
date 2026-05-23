import config


def estimate_tokens(text: str) -> int:
    """估算 token 數量：中文字 2 token，其他字元 1/3 token"""
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    others = len(text) - chinese
    return chinese * 2 + others // 3


class ConversationBuffer:
    """對話緩衝區：管理 context 與 flushed 訊息"""

    def __init__(self) -> None:
        self.context: list[dict] = []
        self.flushed: list[dict] = []
        self.token_limit = config.BUFFER_MAX_TOKENS

    def add(self, role: str, content: str) -> None:
        self.context.append({"role": role, "content": content})
        self.check()

    def check(self) -> None:
        while len(self.context) > 2:
            if self.token_limit < sum(estimate_tokens(m["content"]) for m in self.context):
                if self.context[0]["role"] == "user":
                    self.flushed.append(self.context.pop(0))
                    self.flushed.append(self.context.pop(0))
                else:
                    self.flushed.append(self.context.pop(0))
            else:
                break

    def storage(self) -> list[dict]:
        flushed = list(self.flushed)
        self.flushed.clear()
        return flushed

    def serialize(self) -> str:
        return "\n".join(
            f"{'用戶' if m['role'] == 'user' else '助理'}：{m['content']}"
            for m in self.context
        )

    def get(self) -> list[dict]:
        return list(self.context)
