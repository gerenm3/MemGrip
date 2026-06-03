"""v2 scheduler — 拓撲排序 + 調度.

依據 §3.5 (Scheduler) 定義：
- class Scheduler，供 Orchestrator 透過 DI 注入
- schedule(units, unit_steps) -> Result
- 回傳 {"execution_order", "unit_step_orders", "cyclic_units"}
- 符合 v2 logging 規範
"""

import logging
from collections import deque
from typing import Dict, List, Tuple

from core.health import log_action
from models.blueprints import Unit, Step, Result

logger = logging.getLogger(__name__)


def validate_dag(units: List[Unit]) -> Result:
    """驗證 Unit 列表構成合法的 DAG。

    驗證規則：
    1. 所有 depends_on 的 id 必須存在於 units 中
    2. 依賴圖不能有循環
    3. CONTENT 單元不能依賴 ACTION 單元
    4. depends_on 為空的單元必須至少有一個

    Args:
        units: Unit 列表

    Returns:
        Result(success=True) 若通過
        Result(success=False, error="錯誤列表") 若失敗
    """
    errors: List[str] = []
    if not units:
        return Result(success=True)

    unit_ids = {u.unit_id for u in units}
    unit_map = {u.unit_id: u for u in units}

    # 規則 1: 所有 depends_on 的 id 必須存在
    for u in units:
        for dep_id in u.depends_on:
            dep_str = str(dep_id)
            if dep_str not in unit_ids:
                errors.append(
                    f"Unit '{u.unit_id}' 依賴不存在的 Unit '{dep_str}'"
                )

    # 規則 2: 不能有循環（使用 Kahn's algorithm 檢查）
    in_degree = {u.unit_id: 0 for u in units}
    dependents: Dict[str, List[str]] = {}
    for u in units:
        for dep_id in u.depends_on:
            dep_str = str(dep_id)
            if dep_str in unit_ids:
                in_degree[u.unit_id] += 1
                dependents.setdefault(dep_str, []).append(u.unit_id)

    queue = deque(uid for uid, deg in in_degree.items() if deg == 0)
    visited_count = 0
    while queue:
        uid = queue.popleft()
        visited_count += 1
        for dep_uid in dependents.get(uid, []):
            in_degree[dep_uid] -= 1
            if in_degree[dep_uid] == 0:
                queue.append(dep_uid)

    if visited_count != len(units):
        cyclic_ids = [uid for uid, deg in in_degree.items() if deg > 0]
        errors.append(f"依賴圖存在循環: {cyclic_ids}")

    # 規則 3: CONTENT 單元不能依賴 ACTION 單元
    action_units = {u.unit_id for u in units if u.output_type == "ACTION"}
    for u in units:
        if u.output_type == "CONTENT":
            for dep_id in u.depends_on:
                dep_str = str(dep_id)
                if dep_str in action_units:
                    errors.append(
                        f"CONTENT Unit '{u.unit_id}' 不能依賴 ACTION Unit '{dep_str}'"
                    )

    # 規則 4: 至少有一個 root node（depends_on 為空）
    root_units = [u for u in units if not u.depends_on]
    if not root_units:
        errors.append("DAG 中沒有任何 root node（所有 Unit 都有依賴）")

    if errors:
        log_action("scheduler", "dag_validate_failed", "DEGRADED", "; ".join(errors), "DAG 驗證失敗")
        return Result(success=False, error="; ".join(errors))
    log_action("scheduler", "dag_validate_ok", "OK", str(len(units)))
    return Result(success=True)


def validate_steps(steps: List[Step]) -> Result:
    """驗證 Step 列表的合法性。

    驗證規則：
    1. steps 列表不能為空
    2. 至少一個 step 的 output_type == "GLOBAL"

    Args:
        steps: Step 列表

    Returns:
        Result(success=True) 若通過
        Result(success=False, error="具體錯誤原因") 若失敗
    """
    if not steps:
        return Result(success=False, error="steps 列表不能為空")

    has_global = any(s.output_type == "GLOBAL" for s in steps)
    if not has_global:
        return Result(success=False, error="至少需要一個 output_type 為 GLOBAL 的 Step")

    return Result(success=True)


class Scheduler:
    """負責 Unit 與 Step 的拓撲排序及循環依賴檢測."""

    def schedule(
        self,
        units: List[Unit],
        unit_steps: Dict[str, List[Step]],
    ) -> Result:
        """對 Units 與 Steps 分別做拓撲排序，回傳執行順序.

        Args:
            units: Unit 列表
            unit_steps: {unit_id: [Step, ...]} 映射

        Returns:
            Result(data={"execution_order": List[Unit], "unit_step_orders": Dict[str, List[Step]], "cyclic_units": List[Unit]})
        """
        execution_order, cyclic_units = self._topological_sort(units)

        unit_step_orders: Dict[str, List[Step]] = {}
        for unit_id, steps in unit_steps.items():
            sorted_steps, step_cycles = self._topological_sort_steps(steps)
            unit_step_orders[unit_id] = sorted_steps
            if step_cycles:
                logger.warning("[scheduler] unit %s 的步驟有循環依賴: %s", unit_id, [s.step_id for s in step_cycles])

        if cyclic_units:
            cyclic_ids = [u.unit_id for u in cyclic_units]
            log_action("scheduler", "cyclic_detected", "DEGRADED",
                       str(cyclic_ids), "偵測到循環依賴的 Unit")
        log_action("scheduler", "schedule_complete", "OK", str(len(execution_order)))

        data = {
            "execution_order": execution_order,
            "unit_step_orders": unit_step_orders,
            "cyclic_units": cyclic_units,
        }
        return Result(success=True, data=data)

    def _topological_sort(self, units: List[Unit]) -> Tuple[List[Unit], List[Unit]]:
        """根據 depends_on 計算拓撲排序.

        Args:
            units: Unit 列表

        Returns:
            (sorted_units, cyclic_units)
        """
        if not units:
            return ([], [])

        unit_ids = {u.unit_id for u in units}

        unit_map: Dict[str, Unit] = {}
        unit_deps: Dict[str, List[str]] = {}
        for u in units:
            str_deps = []
            for d in u.depends_on:
                d_str = str(d)
                if d_str not in unit_ids:
                    logger.warning(
                        "[topological_sort] Unit %s 依賴不存在的 unit: %s",
                        u.unit_id, d_str,
                    )
                else:
                    str_deps.append(d_str)
            unit_map[u.unit_id] = u
            unit_deps[u.unit_id] = str_deps

        dependents: Dict[str, List[str]] = {}
        for u in units:
            for d in unit_deps[u.unit_id]:
                dependents.setdefault(d, []).append(u.unit_id)

        in_degree = {u.unit_id: len(unit_deps[u.unit_id]) for u in units}
        queue = deque(uid for uid, deg in in_degree.items() if deg == 0)
        result: List[Unit] = []

        while queue:
            uid = queue.popleft()
            result.append(unit_map[uid])
            for dependent_id in dependents.get(uid, []):
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        # 對 residual units 再做一次拓撲排序
        residual_ids = {u.unit_id for u in units if u.unit_id not in {r.unit_id for r in result}}
        if residual_ids:
            resolvable, still_cyclic = self._separate_cyclic_from_dependent(
                [unit_map[rid] for rid in residual_ids],
                unit_deps,
                residual_ids,
            )
            result.extend(resolvable)
            if still_cyclic:
                cyclic_ids = [u.unit_id for u in still_cyclic]
                logger.warning("[topological_sort] 偵測到循環依賴：%s", cyclic_ids)
            return (result, still_cyclic)

        return (result, [])

    def _separate_cyclic_from_dependent(
        self,
        residual_units: List[Unit],
        unit_deps: Dict[str, List[str]],
        residual_ids: set,
    ) -> Tuple[List[Unit], List[Unit]]:
        """在 residual units 中再做一次拓撲排序."""
        if not residual_units:
            return ([], [])

        in_degree: Dict[str, int] = {u.unit_id: 0 for u in residual_units}
        for u in residual_units:
            for d in unit_deps[u.unit_id]:
                if d in residual_ids:
                    in_degree[u.unit_id] += 1

        dependents: Dict[str, List[str]] = {}
        for u in residual_units:
            for d in unit_deps[u.unit_id]:
                if d in residual_ids:
                    dependents.setdefault(d, []).append(u.unit_id)

        queue = deque(uid for uid, deg in in_degree.items() if deg == 0)
        resolvable: List[Unit] = []
        unit_map = {u.unit_id: u for u in residual_units}

        while queue:
            uid = queue.popleft()
            resolvable.append(unit_map[uid])
            for dependent_id in dependents.get(uid, []):
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        still_cyclic = [u for u in residual_units if u not in resolvable]
        return (resolvable, still_cyclic)

    def _topological_sort_steps(self, steps: List[Step]) -> Tuple[List[Step], List[Step]]:
        """對 Steps 做拓撲排序.

        Args:
            steps: Step 列表

        Returns:
            (sorted_steps, cyclic_steps)
        """
        if not steps:
            return ([], [])

        step_ids = {s.step_id for s in steps}
        step_map = {s.step_id: s for s in steps}
        step_deps: Dict[str, List[str]] = {}
        for s in steps:
            str_deps = []
            for d in s.depends_on:
                d_str = str(d)
                if d_str in step_ids:
                    str_deps.append(d_str)
            step_deps[s.step_id] = str_deps

        dependents: Dict[str, List[str]] = {}
        for s in steps:
            for d in step_deps[s.step_id]:
                dependents.setdefault(d, []).append(s.step_id)

        in_degree = {s.step_id: len(step_deps[s.step_id]) for s in steps}
        queue = deque(sid for sid, deg in in_degree.items() if deg == 0)
        result: List[Step] = []

        while queue:
            sid = queue.popleft()
            result.append(step_map[sid])
            for dependent_id in dependents.get(sid, []):
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        still_cyclic = [s for s in steps if s not in result]
        return (result, still_cyclic)
