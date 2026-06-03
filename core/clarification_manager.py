"""clarification_manager — 多輪澄清管理器（狀態機）。

只負責澄清狀態管理，不執行 pipeline。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import config
from models.blueprints import ClarificationState

logger = logging.getLogger(__name__)


@dataclass
class ClarificationResult:
    """handle_clarification_response() 的回傳結構。"""
    completed: bool          # 澄清是否完成
    path: str                # "tool" | "complex" | "pending"
    clarify_data: dict       # 澄清後的資料
    domain: str              # 路由 domain
    buffer: str              # 記憶 buffer
    summary: str             # 記憶 summary
    rag: str                 # RAG 內容
    reply: Optional[str] = None  # 若澄清未完成，回傳給用戶的問題


class ClarificationManager:
    """多輪澄清管理器。

    Args:
        router: 意圖路由（用於 is_clarification）
        clarifier: 輸入澄清
        memory: 記憶管理
    """

    def __init__(
        self,
        router: Any,
        clarifier: Any,
        memory: Any,
    ) -> None:
        self.router = router
        self.clarifier = clarifier
        self.memory = memory

        # 多輪澄清狀態
        self._clarification_state: ClarificationState = ClarificationState.NORMAL  # "NORMAL" | "AWAITING_CLARIFICATION"
        self._pending_questions: List[str] = []
        self._pending_clarify_result: Optional[dict] = None
        self._pending_path: Optional[str] = None  # "tool" or "complex"
        self._pending_rag: str = ""
        self._pending_buffer: str = ""
        self._pending_summary: str = ""
        self._pending_domain: str = "general"
        self._clarification_rounds: int = 0
        self._clarification_history: List[str] = []
        self._original_user_input: str = ""

    # --------------
    # 公開 API
    # --------------

    @property
    def clarification_state(self) -> ClarificationState:
        return self._clarification_state

    @clarification_state.setter
    def clarification_state(self, value: ClarificationState) -> None:
        self._clarification_state = value

    @property
    def pending_clarify_result(self) -> Optional[dict]:
        return self._pending_clarify_result

    @pending_clarify_result.setter
    def pending_clarify_result(self, value: Optional[dict]) -> None:
        self._pending_clarify_result = value

    @property
    def clarification_rounds(self) -> int:
        return self._clarification_rounds

    @clarification_rounds.setter
    def clarification_rounds(self, value: int) -> None:
        self._clarification_rounds = value

    @property
    def clarification_history(self) -> List[str]:
        return self._clarification_history

    @clarification_history.setter
    def clarification_history(self, value: List[str]) -> None:
        self._clarification_history = value

    @property
    def original_user_input(self) -> str:
        return self._original_user_input

    @original_user_input.setter
    def original_user_input(self, value: str) -> None:
        self._original_user_input = value

    def start_clarification(
        self,
        questions: List[str],
        clarify_data: dict,
        path: str,
        buffer: str,
        summary: str,
        rag: str,
        domain: str = "general",
        original_user_input: str = "",
    ) -> None:
        """初始化一次新的澄清流程。"""
        self._clarification_state = ClarificationState.AWAITING_CLARIFICATION
        self._pending_questions = questions
        self._pending_clarify_result = clarify_data
        self._pending_path = path
        self._pending_rag = rag
        self._pending_buffer = buffer
        self._pending_summary = summary
        self._pending_domain = domain
        self._original_user_input = original_user_input
        self._clarification_rounds = 1
        self._clarification_history = []

    async def handle_clarification_response(self, user_input: str) -> ClarificationResult:
        """處理用戶對澄清問題的回答。

        回傳 ClarificationResult：
        - completed=False: 仍需澄清，reply 為待顯示的問題
        - completed=True: 澄清完成，caller 應根據 path 呼叫對應 pipeline
        """
        # 判斷是否為澄清回答
        clar_result = await self.router.is_clarification(
            user_input, self._pending_questions
        )

        is_clarification = False
        if clar_result.success and isinstance(clar_result.data, dict):
            is_clarification = clar_result.data.get("is_clarification", False)

        if is_clarification:
            # 記錄問答歷史
            for q in self._pending_questions:
                self._clarification_history.append(f"Q: {q}")
            self._clarification_history.append(f"A: {user_input}")

            # 增加澄清輪數
            self._clarification_rounds += 1

            # 檢查是否超過最大澄清輪數
            max_rounds = getattr(config, 'MAX_CLARIFY_ROUNDS', 2)
            if self._clarification_rounds > max_rounds:
                # 超出限制，強制結束澄清，用已有資料執行
                logger.warning(
                    "[ClarificationManager] 澄清輪數超限 (%d > %d)，強制執行",
                    self._clarification_rounds, max_rounds,
                )
                self._clarification_state = ClarificationState.NORMAL
                self._pending_questions = []
                self._clarification_rounds = 0
                self._clarification_history = []
                self._original_user_input = ""
                return await self._build_result(completed=True, reply=None)

            # 建構含問答歷史的輸入（包含原始輸入 + Q&A 歷史 + 用戶最新回答）
            enriched_input = self._original_user_input
            if self._clarification_history:
                enriched_input += "\n\n[Clarification History]\n"
                enriched_input += "\n".join(self._clarification_history)
            # 加入用戶的實際回答
            enriched_input += "\n\n[User's Latest Answer]\n" + user_input

            # 重新澄清
            clarify_result = await self.clarifier.clarify(
                enriched_input, self._pending_buffer, self._pending_summary, self._pending_rag
            )
            if clarify_result.success:
                new_data = clarify_result.data
                new_questions = new_data.get("questions", [])
                if new_questions:
                    self._pending_questions = new_questions
                    self._pending_clarify_result = new_data
                    logger.info("[ClarificationManager] 仍有問題需要澄清: %s", new_questions)
                    return await self._build_result(completed=False, reply="\n".join(f"- {q}" for q in new_questions))
                else:
                    # 澄清完成
                    self._clarification_state = ClarificationState.NORMAL
                    self._pending_clarify_result = new_data
                    self._pending_questions = []
                    self._clarification_rounds = 0
                    self._clarification_history = []
                    self._original_user_input = ""
                    return await self._build_result(completed=True, reply=None)
            else:
                logger.error("[ClarificationManager] 重新澄清失敗: %s", clarify_result.error)
                self._clarification_state = ClarificationState.NORMAL
                self._clarification_rounds = 0
                self._clarification_history = []
                self._original_user_input = ""
                return await self._build_result(completed=False, reply=None)
        else:
            # 用戶的回答不是針對澄清問題 → 視為「直接執行」
            logger.info(
                "[ClarificationManager] 用戶輸入非澄清回答，視為直接執行指令: %s",
                user_input[:50],
            )
            self._clarification_state = ClarificationState.NORMAL
            self._pending_questions = []
            self._clarification_rounds = 0
            self._clarification_history = []
            self._original_user_input = ""
            return await self._build_result(completed=True, reply=None)

    async def _build_result(self, completed: bool, reply: Optional[str]) -> ClarificationResult:
        """建構 ClarificationResult。"""
        if not self._pending_clarify_result:
            return ClarificationResult(
                completed=False,
                path="pending",
                clarify_data={},
                domain=self._pending_domain,
                buffer=self._pending_buffer,
                summary=self._pending_summary,
                rag=self._pending_rag,
                reply=reply,
            )
        clarified_goal = self._pending_clarify_result.get("goal", "")
        new_route = await self.router.route(clarified_goal)
        new_route_data = new_route.data if new_route.success else {}
        path = new_route_data.get("intent", self._pending_path or "tool")
        domain = new_route_data.get("domain", self._pending_domain)
        if path == "simple":
            path = "tool"
        return ClarificationResult(
            completed=completed,
            path=path,
            clarify_data=self._pending_clarify_result,
            domain=domain,
            buffer=self._pending_buffer,
            summary=self._pending_summary,
            rag=self._pending_rag,
            reply=reply,
        )