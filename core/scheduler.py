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
    result = []

    while queue:
        uid = queue.pop(0)
        result.append(unit_map[uid])

        for u in units:
            if uid in u.depends_on:
                in_degree[u.unit_id] -= 1
                if in_degree[u.unit_id] == 0:
                    queue.append(u.unit_id)

    # 若有循環依賴，回傳剩下的 units
    if len(result) < len(units):
        remaining = [u for u in units if u not in result]
        result.extend(remaining)

    return result


def apply_pruning(units: List[Unit], results: Dict[str, UnitResult]) -> Dict[str, UnitResult]:
    """連鎖剪枝：Unit FAILED → 依賴它的下游 Unit 標記 SKIPPED

    觸發時機：每個 Unit 到達終止狀態（FAILED）後立即調用。

    Args:
        units: 所有 Unit 列表（用於查詢依賴關係）
        results: {unit_id: UnitResult}

    Returns:
        更新後的 results
    """
    unit_map = {u.unit_id: u for u in units}
    changed = True

    while changed:
        changed = False
        for uid, result in results.items():
            if result.status != UnitStatus.FAILED:
                continue

            # 找所有依賴此 failed unit 的下游 units
            for u in units:
                if uid in u.depends_on:
                    other_result = results.get(u.unit_id)
                    if other_result and other_result.status == UnitStatus.SUCCESS:
                        # 把 SUCCESS 改成 SKIPPED
                        results[u.unit_id] = UnitResult(
                            unit_id=u.unit_id,
                            status=UnitStatus.SKIPPED,
                            error=f"依賴的 Unit {uid} 失敗，跳過執行"
                        )
                        changed = True

    return results
