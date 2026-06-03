"""v2 buffer — 對話緩衝區管理.

依據 §3.13 (Memory Layer) + §5.4 (摘要分流) 定義：
- ConversationBuffer：對話緩衝區管理
- Token 估算公式：CJK 字元 ×2、其他字元 ÷3（§3.13 保留）
- Buffer check() 以 `len(context) > 2` 為 guard（§3.13 保留）
"""

from typing import Dict, List

import config


def estimate_tokens(text: str) -> int:
    """估算 token 數量：CJK 字元 2 token，其他字元 1/3 token。

    涵蓋範圍：CJK 基本區 (\u4e00-\u9fff) + CJK 擴展區 A (\u3400-\u4DBF)。
    注意：擴展區 B~G、日文漢字、韓文漢字不涵蓋，會算作一般字元。
    """
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4DBF')
    others = len(text) - chinese
    return chinese * 2 + others // 3


class ConversationBuffer:
    """對話緩衝區：管理 context 與 flushed 訊息"""

    def __init__(self) -> None:
        self.context: List[Dict[str, str]] = []
        self.flushed: List[Dict[str, str]] = []
        self._current_tokens: int = 0
        self.token_limit = config.BUFFER_MAX_TOKENS

    def add(self, role: str, content: str) -> None:
        added_tokens = estimate_tokens(content)
        self._current_tokens += added_tokens
        self.context.append({"role": role, "content": content})
        self.check()

    def check(self) -> None:
        """將超額的舊對話移至 flushed。

        若最後一筆不是 assistant（即只有 user 尚未收到回覆），保留第一輪不 flush，
        避免 flush 出「半輪」對話對。
        """
        while len(self.context) > 2 and self._current_tokens > self.token_limit:
            if self.context[-1]["role"] != "assistant":
                break
            first = self.context.pop(0)
            second = self.context.pop(0)
            self._current_tokens -= estimate_tokens(first["content"])
            self._current_tokens -= estimate_tokens(second["content"])
            self.flushed.append(first)
            self.flushed.append(second)

    def extract_flushed(self) -> List[Dict[str, str]]:
        """回傳已 flush 的訊息並清空 flushed。"""
        flushed = list(self.flushed)
        self.flushed.clear()
        return flushed

    def serialize(self) -> str:
        return "\n".join(
            f"{'用戶' if m['role'] == 'user' else '助理'}：{m['content']}"
            for m in self.context
        )

    def get(self) -> List[Dict[str, str]]:
        return list(self.context)
