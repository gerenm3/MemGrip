"""v2 message_builder — 訊息建構器.

依據 §2.1 (Client Layer) 定義：
- 純工具類，不涉及 I/O
- 靜態方法，不包 Result
"""

from typing import Dict, List, Optional


class MessageBuilder:
    """統一的訊息建構器"""

    @staticmethod
    def build_core(system_prompt: str, user_content: str) -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

    @staticmethod
    def build_task(prompt: str, user_input: str) -> List[Dict[str, str]]:
        """任務執行類：絕對去噪，不含 SUMMARY/BUFFER。

        system role = prompt，user role = user_input，不注入任何記憶區塊。
        """
        return MessageBuilder.build_core(prompt, user_input)

    @staticmethod
    def build_dialog(
        prompt: str,
        user_input: str,
        summary_text: str = "",
        buffer_text: str = "",
        rag_context: str = ""
    ) -> List[Dict[str, str]]:
        """交互對話類：注入長期/短期記憶。

        memory tags（[SUMMARY]/[BUFFER]/[RAG]）合併至 system role content，
        user input 以 [USER_INPUT] tag 包裹，置於 user role content。
        各區塊以雙換行分隔，避免 prompt 內換行與 tag 分隔線混淆。
        """
        parts = [prompt]
        if summary_text:
            parts.append(f"\n\n[SUMMARY]{summary_text}[/SUMMARY]")
        if buffer_text:
            parts.append(f"\n\n[BUFFER]{buffer_text}[/BUFFER]")
        if rag_context:
            parts.append(f"\n\n[RAG]{rag_context}[/RAG]")
        user_input = f"[USER_INPUT]\n{user_input}\n[/USER_INPUT]"
        return MessageBuilder.build_core("\n\n".join(parts), user_input)

    @staticmethod
    def build_meta(prompt: str, blocks: Dict[str, str]) -> List[Dict[str, str]]:
        """數據審查類：將數據區塊標籤化。

        blocks 為 Dict[str, str]，key 為 tag 名稱，value 為內容。
        各區塊以雙換行分隔，使 LLM 能清楚區隔不同區塊。
        """
        formatted_text = "\n\n".join(f"[{tag}]{val}[/{tag}]" for tag, val in blocks.items())
        return MessageBuilder.build_core(prompt, formatted_text)
