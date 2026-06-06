"""signal_collector — 收集任務執行指標並寫入 signal_log.jsonl.

符合 logging 規範
"""

import json
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from clients.model_client import call_model
from core.json_utils import parse_first_json
from skills.skill_manager import SkillManager
from skills.trace_reader import build_execution_record
from core.health import log_action

logger = logging.getLogger(__name__)

# Constants
TZ_TAIPEI = timedelta(hours=8)
REPLAN_THRESHOLD = 2
VERIFIER_PASS_THRESHOLD = 0.8
RANDOM_AUDIT_PROBABILITY = 0.05
DEFAULT_LAYER3_TEMPERATURE = 0

# Layer 3 品質問題類型
_L3_ISSUE_TYPES = [
    "shallow_reasoning",
    "missing_dimension",
    "premature_conclusion",
    "unsupported_claim",
    "over_decomposition",
    "under_decomposition",
]


def collect(session_id: str, task_type: str, task_record: dict | None = None) -> dict | None:
    """從 task_record 收集指標，寫入 signal_log.jsonl.

    若提供 task_record（來自 LVS process），直接使用其指標，
    避免讀取尚未寫入的 task_trace.jsonl。

    Args:
        session_id: 任務 session ID
        task_type: 任務類型
        task_record: 可選的 task record dict（包含聚合指標）

    Returns:
        寫入的 signal dict，若無資料則回傳 None
    """
    # 優先使用傳入的 task_record；若無則從 trace_reader 讀取
    if task_record:
        execution_data = task_record
    else:
        execution_data = build_execution_record(session_id)
        if execution_data is None:
            logger.warning("[signal_collector] 找不到 session %s 的執行記錄", session_id)
            return None

    # 取得當前 skill_version（局部實例，避免多 session 狀態共享）
    signal_manager = SkillManager()
    skill_version = signal_manager.get_version(task_type, "l1")

    signal = {
        "session_id": session_id,
        "task_type": task_type,
        "skill_version": skill_version,
        "ts": datetime.now(timezone(TZ_TAIPEI)).isoformat(),
        "timestamp": time.time(),
        # 聚合指標
        "unit_count": execution_data.get("unit_count", 0),
        "replan_count": execution_data.get("replan_count", 0),
        "failed_units": execution_data.get("failed_units", 0),
        "avg_loop_count": execution_data.get("avg_loop_count", 0),
        "constraint_satisfied_ratio": execution_data.get("constraint_satisfied_ratio", 1.0),
        "verifier_pass_ratio": execution_data.get("verifier_pass_ratio", 1.0),
    }

    # ── Layer 3 品質校正 ──
    layer3_data = evaluate_layer3(session_id, task_type, execution_data)
    if layer3_data is not None:
        signal["layer3"] = layer3_data
        logger.info("[signal_collector] layer3 評估完成: session=%s, triggered=%s, evaluations=%d",
                     session_id, layer3_data.get("trigger_reason"), len(layer3_data.get("evaluations", [])))

    # 寫入 signal_log
    signal_path = Path(config.SIGNAL_LOG_PATH)
    try:
        signal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(signal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(signal, ensure_ascii=False) + "\n")
        logger.info("[signal_collector] 寫入 signal_log: session=%s, version=%d", session_id, skill_version)
    except Exception as e:
        logger.error("[signal_collector] 寫入 signal_log.jsonl 失敗: %s", e, exc_info=True)

    return signal


def evaluate_layer3(
    session_id: str,
    task_type: str,
    execution_data: dict,
) -> Optional[dict]:
    """Layer 3 品質校正層：評估 unit 輸出的品質問題。

    觸發條件（二擇一）：
    - 異常觸發：replan_count > 2 或 failed_units > 0 或 verifier_pass_ratio < 0.8
    - 隨機審計：5% 機率

    評估基準：
    - expected_output（主要判斷基準）
    - assigned_constraints（補充上下文，有就附加）

    Args:
        session_id: 任務 session ID
        task_type: 任務類型
        execution_data: 執行資料（來自 build_execution_record）

    Returns:
        layer3 dict（含 triggered, trigger_reason, evaluations），
        若無實際輸出可評估或無觸發則回傳 None
    """
    replan_count = execution_data.get("replan_count", 0)
    failed_units = execution_data.get("failed_units", 0)
    verifier_pass_ratio = execution_data.get("verifier_pass_ratio", 1.0)

    # 觸發判定
    is_anomaly = (
        replan_count > REPLAN_THRESHOLD
        or failed_units > 0
        or verifier_pass_ratio < VERIFIER_PASS_THRESHOLD
    )
    is_random = random.random() < RANDOM_AUDIT_PROBABILITY

    triggered = is_anomaly or is_random
    trigger_reason = "anomaly" if is_anomaly else "random_audit"

    if triggered:
        log_action("signal_collector", "signal_triggered", "OK",
                   f"session={session_id} reason={trigger_reason} replan={replan_count} failed={failed_units} verifier={verifier_pass_ratio:.2f}")

    if not triggered:
        logger.debug(
            "[layer3] 未觸發 (replan=%d, failed=%d, verifier_ratio=%.2f)",
            replan_count, failed_units, verifier_pass_ratio,
        )
        return None

    logger.info(
        "[layer3] 觸發品質校正層: reason=%s, session=%s",
        trigger_reason, session_id,
    )

    # 取得 task-level clarifier_constraints（fallback 用）
    clarifier_constraints = _get_clarifier_constraints(session_id)

    # 取得 units 資料
    units = execution_data.get("units", [])
    if not units:
        logger.warning("[layer3] 無 unit 資料可評估")
        return None

    # 篩選要評估的 units
    if trigger_reason == "anomaly":
        # 異常觸發：failed units + 有 actual_output 的 units
        eval_units = [
            u for u in units
            if u.get("status") == "FAILED" or (u.get("actual_output", "") != "")
        ]
    else:
        # 隨機審計：所有有 actual_output 的 units
        eval_units = [
            u for u in units if u.get("actual_output", "") != ""
        ]

    if not eval_units:
        logger.info("[layer3] 無可評估的 unit（無 actual_output）")
        return None

    # 對每個 unit 獨立評估
    evaluations = []
    for unit in eval_units:
        unit_id = unit.get("unit_id", "")
        actual_output = unit.get("actual_output", "")

        # 跳過無 actual_output 的 unit
        if not actual_output:
            continue

        # 取得評估基準
        expected_output = unit.get("expected_output", "")
        assigned_constraints = unit.get("assigned_constraints", [])

        # 若 assigned_constraints 為空，使用 clarifier_constraints 作為補充
        constraint_context = assigned_constraints if assigned_constraints else clarifier_constraints

        # 呼叫 LLM 評估
        eval_result = _evaluate_unit_quality(
            expected_output=expected_output,
            actual_output=actual_output,
            constraints=constraint_context,
            unit_id=unit_id,
        )

        if eval_result is not None:
            eval_result["unit_id"] = unit_id
            evaluations.append(eval_result)

    if not evaluations:
        logger.info("[layer3] 無有效評估結果")
        return None

    layer3_data = {
        "triggered": True,
        "trigger_reason": trigger_reason,
        "evaluations": evaluations,
    }

    logger.info(
        "[layer3] 完成評估: session=%s, evaluations=%d",
        session_id, len(evaluations),
    )

    return layer3_data


def _get_clarifier_constraints(session_id: str) -> List[str]:
    """從 task_trace.jsonl 取得 session 的 clarifier_constraints."""
    task_trace_path = Path(config.TASK_TRACE_PATH)
    if not task_trace_path.exists():
        return []

    with task_trace_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("session_id") == session_id:
                    return rec.get("clarifier_constraints", [])
            except json.JSONDecodeError:
                continue

    return []


def _evaluate_unit_quality(
    expected_output: str,
    actual_output: str,
    constraints: List[str],
    unit_id: str,
) -> Optional[dict]:
    """使用 MEDIUM_MODEL 評估單一 unit 的品質問題。

    Args:
        expected_output: 預期輸出（主要判斷基準）
        actual_output: 實際輸出
        constraints: 約束條件（補充上下文）
        unit_id: unit 識別碼

    Returns:
        評估結果 dict，若解析失敗則回傳 None
    """
    prompt = _build_layer3_prompt(expected_output, actual_output, constraints)

    result = call_model(
        model=config.MEDIUM_MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=DEFAULT_LAYER3_TEMPERATURE,
        max_tokens=config.MAX_TOKENS,
        think=False,
        caller="signal_collector.layer3",
    )

    if not result.success:
        logger.error("[layer3] LLM 評估失敗 unit=%s: %s", unit_id, result.error)
        return None

    return _parse_layer3_response(result.data, unit_id)


def _build_layer3_prompt(
    expected_output: str,
    actual_output: str,
    constraints: List[str],
) -> str:
    """建構 Layer 3 評估提示詞."""
    constraints_text = ""
    if constraints:
        constraints_text = f"""\n\n約束條件（補充上下文）：
{json.dumps(constraints, ensure_ascii=False, indent=2)}"""

    return f"""你是一個品質評估系統。請根據以下資訊評估 unit 輸出的品質問題。

預期輸出（主要判斷基準）：
{expected_output}

實際輸出：
{actual_output}{constraints_text}

請評估實際輸出是否存在以下品質問題（從以下六種類型中選擇最符合的一種）：
- shallow_reasoning：推論過於淺薄，缺乏深度分析
- missing_dimension：遺漏了重要的評估面向或約束條件
- premature_conclusion：在資訊不足時就做出結論
- unsupported_claim：提出了缺乏證據支持的聲明
- over_decomposition：過度拆解，將簡單問題複雜化
- under_decomposition：拆解不足，忽略了應分離的面向

若實際輸出完全符合預期輸出且無品質問題，quality_issue 設為 false，其他欄位可設為 null。

若存在品質問題，quality_issue 設為 true，並根據嚴重程度評分（1-5）：
1 = 輕微，3 = 中等，5 = 嚴重

請輸出 JSON：
{{
  "quality_issue": true/false,
  "issue_type": "shallow_reasoning | missing_dimension | premature_conclusion | unsupported_claim | over_decomposition | under_decomposition",
  "severity": 1-5,
  "reason": "具體說明評估理由"
}}"""


def _parse_layer3_response(text: str, unit_id: str) -> Optional[dict]:
    """解析 LLM 回傳的 JSON 結果."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("`", 1)[0]

    try:
        parsed = parse_first_json(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("[layer3] 無法解析 unit=%s 的評估結果", unit_id)
        return None

    if parsed is None:
        logger.warning("[layer3] unit=%s 的評估結果為空", unit_id)
        return None

    # 驗證必要欄位
    issue_type = parsed.get("issue_type", "")
    if issue_type and issue_type not in _L3_ISSUE_TYPES:
        logger.warning(
            "[layer3] unit=%s 的 issue_type 不在允許列表中: %s",
            unit_id, issue_type,
        )
        return None

    severity = parsed.get("severity")
    if severity is not None:
        try:
            severity = int(severity)
            if severity < 1 or severity > 5:
                logger.warning("[layer3] unit=%s 的 severity 超出範圍: %d", unit_id, severity)
                return None
        except (TypeError, ValueError):
            logger.warning("[layer3] unit=%s 的 severity 無法轉換: %s", unit_id, severity)
            return None

    return {
        "quality_issue": bool(parsed.get("quality_issue", False)),
        "issue_type": issue_type if issue_type else None,
        "severity": severity,
        "reason": str(parsed.get("reason", "")),
    }