"""Signal-driven Optimizer — 3-step LLM flow.

依據 §3.12 (Optimizer) 定義：
- class Optimizer，供 Orchestrator 透過 DI 注入
- 3-step LLM flow：_analyze_signals → _update_skills → _verify
- verify 通過才寫入 current.json
- 不自行觸發，完全由 Orchestrator 控制
- 使用 logger 記錄，禁止 print()
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from clients.model_client import call_model
from core.json_utils import parse_first_json
from models.blueprints import Result
from skills.skill_manager import SkillManager

logger = logging.getLogger(__name__)

# 異常判定閾值
FAILED_UNITS_THRESHOLD = 0
REPLAN_COUNT_THRESHOLD = 2
AVG_LOOP_COUNT_THRESHOLD = 4
CONSTRAINT_SATISFIED_RATIO_THRESHOLD = 0.7

# Default constants
DEFAULT_VERIFY_TEMPERATURE = 0


class Optimizer:
    """Signal-driven Optimizer：3-step LLM flow.

    Steps:
        1. _analyze_signals — 讀取 signal_log.jsonl，統計偏差，映射到五維度
        2. _update_skills — 根據 dimension_map 最小修改 skill guide
        3. _verify — 檢查一致性、無矛盾、無極端化
    """

    def __init__(self) -> None:
        self._skill_manager = SkillManager()

    async def run_optimizer(
        self,
        session_id: str,
        task_type: Optional[str] = None,
        level: str = "l1",
    ) -> Result:
        """主入口：依序執行三個步驟，verify 通過才寫入.

        Args:
            session_id: 任務 session ID
            task_type: 任務類型（None 時從 trace 取得）
            level: 技能層級 "l1" 或 "l2"

        Returns:
            Result(data={"dimension_map": dict, "update_result": dict})
        """
        try:
            logger.info(
                "[optimizer] start: session=%s, task_type=%s, level=%s",
                session_id, task_type, level,
            )

            # 若 task_type 為 None，從 signal_log 取得最後一筆的 task_type
            if task_type is None:
                task_type = self._get_last_task_type()
                logger.info("[optimizer] 從 signal_log 取得 task_type=%s", task_type)

            # Step 1: 分析信號
            dimension_map = await self._analyze_signals(task_type, level)
            if dimension_map is None:
                return Result(
                    success=False,
                    error="analyze_signals 無效輸出",
                )

            # 載入當前 skill
            current_skills = self._skill_manager.load_skill(task_type, level)

            # Step 2: 更新 skill
            update_result = await self._update_skills(
                dimension_map, current_skills, task_type, level
            )
            if update_result is None:
                return Result(
                    success=False,
                    error="update_skills 無效輸出",
                )

            # Step 3: 驗證
            passed = await self._verify(update_result, dimension_map, current_skills)
            if not passed:
                logger.warning("[optimizer] verify 未通過，不寫入 skill")
                return Result(
                    success=True,
                    data={
                        "dimension_map": dimension_map,
                        "update_result": update_result,
                        "verified": False,
                    },
                )

            # 寫入 skill
            updated = update_result.get("updated_skills", {})
            self._skill_manager.apply_update(
                task_type, updated, dimension_map, level,
            )
            self._skill_manager.save_history(
                task_type, dimension_map, update_result, level,
            )
            logger.info(
                "[optimizer] skill updated: task_type=%s, level=%s, dims=%s",
                task_type, level, list(updated.keys()),
            )

            return Result(
                success=True,
                data={
                    "dimension_map": dimension_map,
                    "update_result": update_result,
                    "verified": True,
                },
            )

        except Exception as e:
            logger.error("[optimizer] run_optimizer failed: %s", e, exc_info=True)
            return Result(success=False, error=str(e))

    async def _analyze_signals(
        self,
        task_type: str,
        level: str,
    ) -> Optional[Dict]:
        """讀取 signal_log.jsonl，統計各 skill_version 指標偏差，映射到五維度.

        Args:
            task_type: 任務類型
            level: 技能層級

        Returns:
            dimension_map dict，key 為五維度名稱，value 為 {"problem": str, "direction": str}
        """
        signal_path = Path(config.SIGNAL_LOG_PATH)
        signals: List[Dict] = []

        if not signal_path.exists():
            logger.warning("[optimizer] signal_log 不存在: %s", signal_path)
            return None

        with open(signal_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    sig = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if sig.get("task_type") == task_type:
                    signals.append(sig)

        if not signals:
            logger.info("[optimizer] 無 %s 信號資料", task_type)
            return None

        # 統計摘要
        stats = self._compute_stats(signals)

        # 判斷哪些維度有問題
        abnormal_dims = self._detect_anomalies(stats)

        if not abnormal_dims:
            logger.info("[optimizer] 無異常維度，不需要優化")
            return None

        # LLM 映射到五維度
        dimension_map = await self._llm_map_dimensions(signals, stats, abnormal_dims)
        return dimension_map

    async def _update_skills(
        self,
        dimension_map: Dict,
        current_skills: Dict,
        task_type: str,
        level: str,
    ) -> Optional[Dict]:
        """根據 dimension_map 對 skill guide 做最小修改.

        Args:
            dimension_map: 維度映射，key 為維度名稱
            current_skills: 當前 skill guide
            task_type: 任務類型
            level: 技能層級

        Returns:
            update_result dict
        """
        dimensions_def = config.SKILL_DIMENSIONS

        # 過濾出有問題的維度
        problem_dims = {k: v for k, v in dimension_map.items()
                       if isinstance(v, dict) and v.get("problem")}

        if not problem_dims:
            logger.info("[optimizer] 無問題維度需要更新")
            return None

        prompt = f"""你是 skill guide 優化系統。

以下是五個維度的定義：
{json.dumps(dimensions_def, ensure_ascii=False, indent=2)}

以下是診斷出的問題維度及方向：
{json.dumps(problem_dims, ensure_ascii=False, indent=2)}

以下是目前的 skill guide：
{json.dumps(current_skills, ensure_ascii=False, indent=2)}

任務類型：{task_type}
技能層級：{level}

請根據診斷結果，對 skill guide 做最小修改：
- 只修改診斷結果中指出有問題的維度
- 保留原有結構，只在必要處增加、修改或刪除內容
- 不要重寫整份文件
- 若 task_type 為 general 或 global，規則必須是通用原則

輸出 JSON：
{{
  "modified_dimensions": ["被修改的維度"],
  "updated_skills": {{
    // 只包含被修改的維度及其完整更新後內容
  }},
  "change_summary": {{
    // 每個維度的修改說明
  }}
}}"""

        result = await call_model(
            model=config.LARGE_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=DEFAULT_VERIFY_TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
            think=True,
            caller="optimizer._update_skills",
        )

        if not result.success:
            logger.error("[optimizer] _update_skills LLM failed: %s", result.error)
            return None

        try:
            return self._extract_json(result.data)
        except Exception as e:
            logger.error("[optimizer] _update_skills parse failed: %s", e)
            return None

    async def _verify(
        self,
        update_result: Dict,
        dimension_map: Dict,
        current_skills: Dict,
    ) -> bool:
        """驗證更新的一致性、無矛盾、無極端化.

        Args:
            update_result: 更新結果
            dimension_map: 維度映射
            current_skills: 原 skill guide

        Returns:
            True 表示驗證通過
        """
        prompt = f"""你是 skill guide 驗證系統。

以下是診斷出的問題維度：
{json.dumps(dimension_map, ensure_ascii=False, indent=2)}

以下是本次更新內容：
{json.dumps(update_result.get("updated_skills", {}), ensure_ascii=False, indent=2)}

以下是原 skill guide：
{json.dumps(current_skills, ensure_ascii=False, indent=2)}

請逐一檢查：
1. 更新是否真正解決了診斷出的問題？
2. 更新內容是否與原 skill guide 矛盾？
3. 是否有極端化的傾向（如過度限制或過度放寬）？
4. 更新是否保持最小修改原則？

輸出 JSON：
{{
  "passed": true/false,
  "reason": "驗證理由"
}}"""

        result = await call_model(
            model=config.LARGE_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=DEFAULT_VERIFY_TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
            think=False,
            caller="optimizer._verify",
        )

        if not result.success:
            logger.error("[optimizer] _verify LLM failed: %s", result.error)
            return False

        try:
            parsed = self._extract_json(result.data)
            return bool(parsed.get("passed", False))
        except Exception as e:
            logger.error("[optimizer] _verify parse failed: %s", e)
            return False

    # -- 內部輔助方法 --

    def _get_last_task_type(self) -> str:
        """從 signal_log.jsonl 取得最後一筆的 task_type."""
        signal_path = Path(config.SIGNAL_LOG_PATH)
        if not signal_path.exists():
            return "general"
        try:
            with open(signal_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    sig = json.loads(line)
                    return sig.get("task_type", "general")
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.warning("[optimizer] _get_last_task_type failed: %s", e)
        return "general"

    def _compute_stats(self, signals: List[Dict]) -> Dict:
        """計算統計摘要."""
        n = len(signals)
        if n == 0:
            return {}

        return {
            "count": n,
            "avg_replan": sum(s.get("replan_count", 0) for s in signals) / n,
            "avg_failed_units": sum(s.get("failed_units", 0) for s in signals) / n,
            "avg_loop_count": sum(s.get("avg_loop_count", 0) for s in signals) / n,
            "avg_constraint_ratio": sum(s.get("constraint_satisfied_ratio", 1.0) for s in signals) / n,
            "avg_verifier_ratio": sum(s.get("verifier_pass_ratio", 1.0) for s in signals) / n,
            "avg_unit_count": sum(s.get("unit_count", 0) for s in signals) / n,
            "latest_version": signals[-1].get("skill_version", 0),
        }

    def _detect_anomalies(self, stats: Dict) -> List[str]:
        """根據閾值判定異常維度."""
        anomalies: List[str] = []

        if stats.get("avg_failed_units", 0) > FAILED_UNITS_THRESHOLD:
            anomalies.append("failed_units")
        if stats.get("avg_replan", 0) > REPLAN_COUNT_THRESHOLD:
            anomalies.append("replan_count")
        if stats.get("avg_loop_count", 0) > AVG_LOOP_COUNT_THRESHOLD:
            anomalies.append("avg_loop_count")
        if stats.get("avg_constraint_ratio", 1.0) < CONSTRAINT_SATISFIED_RATIO_THRESHOLD:
            anomalies.append("constraint_ratio")

        return anomalies

    async def _llm_map_dimensions(
        self,
        signals: List[Dict],
        stats: Dict,
        abnormal_dims: List[str],
    ) -> Optional[Dict]:
        """用 LLM 將異常映射到五個 skill 維度.

        Returns:
            dimension_map dict
        """
        dimensions_def = config.SKILL_DIMENSIONS

        # 提取最近 5 筆異常 signal 作為證據
        evidence = []
        for s in signals[-5:]:
            if (s.get("failed_units", 0) > FAILED_UNITS_THRESHOLD or
                s.get("replan_count", 0) > REPLAN_COUNT_THRESHOLD or
                s.get("avg_loop_count", 0) > AVG_LOOP_COUNT_THRESHOLD or
                s.get("constraint_satisfied_ratio", 1.0) < CONSTRAINT_SATISFIED_RATIO_THRESHOLD):
                evidence.append(s)

        prompt = f"""你是 skill 維度映射系統。

五個維度定義：
{json.dumps(dimensions_def, ensure_ascii=False, indent=2)}

統計摘要：
{json.dumps(stats, ensure_ascii=False, indent=2)}

異常維度：{abnormal_dims}

異常 session 證據（最近 5 筆）：
{json.dumps(evidence, ensure_ascii=False, indent=2)}

請將異常映射到五個 skill 維度。每個維度輸出：
- problem：問題描述
- direction：調整方向（如 direct → step_by_step）

只輸出 JSON：
{{
  "reasoning_resolution": {{"problem": "...", "direction": "..."}},
  "constraint_rigidity": {{"problem": "...", "direction": "..."}},
  "signal_noise_ratio": {{"problem": "...", "direction": "..."}},
  "boundary_anchoring": {{"problem": "...", "direction": "..."}},
  "uncertainty_handling": {{"problem": "...", "direction": "..."}}
}}"""

        result = await call_model(
            model=config.LARGE_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=DEFAULT_VERIFY_TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
            think=False,
            caller="optimizer._analyze_signals",
        )

        if not result.success:
            logger.error("[optimizer] _analyze_signals LLM failed: %s", result.error)
            return None

        try:
            return self._extract_json(result.data)
        except Exception as e:
            logger.error("[optimizer] _analyze_signals parse failed: %s", e)
            return None

    @staticmethod
    def _extract_json(text: str) -> Any:
        """從 LLM 輸出提取 JSON (使用 parse_first_json)."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("`", 1)[0]
        return parse_first_json(text)
