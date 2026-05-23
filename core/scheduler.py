"""Scheduler — 拓撲排序 + 連鎖剪枝"""

from typing import List, Dict
from models.blueprints import Unit, UnitResult, UnitStatus


def topological_sort(units: List[Unit]) -> List[Unit]:
    """根據 depends_on 計算拓撲排序

    Args:
        units: Unit 列表

    Returns:
        拓撲排序後的 Unit 列表
    """
    unit_map = {u.unit_id: u for u in units}
    in_degree = {u.unit_id: len(u.depends_on) for u in units}
    queue = [uid for uid, deg in in_degree.items() if deg == 0]
    result_ids: set[str] = set()
    result: List[Unit] = []

    while queue:
        uid = queue.pop(0)
        result.append(unit_map[uid])
        result_ids.add(uid)

        for u in units:
            if uid in u.depends_on:
                in_degree[u.unit_id] -= 1
                if in_degree[u.unit_id] == 0:
                    queue.append(u.unit_id)

    # 若有循環依賴，回傳剩下的 units
    if len(result) < len(units):
        result.extend(u for u in units if u not in result)

    return result


def _is_terminal(result: UnitResult) -> bool:
    """檢查 UnitResult 是否已到達終止狀態（FAILED 或 SKIPPED）"""
    return result.status in (UnitStatus.FAILED, UnitStatus.SKIPPED)


def _mark_skipped(results: Dict[str, UnitResult], unit_id: str, failed_id: str) -> None:
    """將 unit 標記為 SKIPPED"""
    results[unit_id] = UnitResult(
        unit_id=unit_id,
        status=UnitStatus.SKIPPED,
        error=f"依賴的 Unit {failed_id} 失敗，跳過執行",
    )


def apply_pruning(units: List[Unit], results: Dict[str, UnitResult]) -> Dict[str, UnitResult]:
    """連鎖剪枝：Unit FAILED → 依賴它的下游 Unit 標記 SKIPPED

    觸發時機：每個 Unit 到達終止狀態（FAILED）後立即調用。

    Args:
        units: 所有 Unit 列表（用於查詢依賴關係）
        results: {unit_id: UnitResult}

    Returns:
        更新後的 results
    """
    # 預先建立 dep_id → 下游 units 的映射
    downstream_map: dict[str, list[Unit]] = {}
    for u in units:
        for dep_id in u.depends_on:
            downstream_map.setdefault(str(dep_id), []).append(u)

    # 找出所有已到達終止狀態的 unit
    terminal_units = [rid for rid, r in results.items() if _is_terminal(r)]

    # BFS 追蹤連鎖影響
    to_skip: set[str] = set()
    queue: list[str] = list(terminal_units)
    while queue:
        current_id = queue.pop(0)
        for downstream in downstream_map.get(current_id, []):
            did = downstream.unit_id
            if did not in to_skip and did not in results:
                to_skip.add(did)
                _mark_skipped(results, did, current_id)
                queue.append(did)

    return results
