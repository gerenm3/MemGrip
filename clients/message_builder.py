"""MessageBuilder — 訊息建構器"""

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
        """任務執行類：絕對去噪，不含 SUMMARY/BUFFER"""
        return MessageBuilder.build_core(prompt, user_input)

    @staticmethod
    def build_dialog(
        prompt: str,
        user_input: str,
        summary_text: str = "",
        buffer_text: str = "",
        rag_context: str = ""
    ) -> List[Dict[str, str]]:
        """交互對話類：注入長期/短期記憶"""
        system_content = prompt
        if summary_text:
            system_content += f"\n[SUMMARY]{summary_text}[/SUMMARY]"
        if buffer_text:
            system_content += f"\n[BUFFER]{buffer_text}[/BUFFER]"
        if rag_context:
            system_content += f"\n[RAG]{rag_context}[/RAG]"
        user_input = f"[CURRENT_INPUT]\n{user_input}\n[/CURRENT_INPUT]"
        return MessageBuilder.build_core(system_content, user_input)

    @staticmethod
    def build_meta(prompt: str, blocks: Dict[str, str]) -> List[Dict[str, str]]:
        """數據審查類：將數據區塊標籤化"""
        formatted_text = "".join(f"[{tag}]{val}[/{tag}]" for tag, val in blocks.items())
        return MessageBuilder.build_core(prompt, formatted_text)
