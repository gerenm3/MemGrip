"""Storage — Unit 層級 + Step 層級存放空間"""

from typing import Dict, Optional, List, Tuple
from models.blueprints import UnitStatus, StepStatus


class UnitStore:
    """Unit 層級存放"""

    def __init__(self):
        self._status: Dict[str, UnitStatus] = {}
        self._output: Dict[str, str] = {}
        self._error: Dict[str, str] = {}

    def set_status(self, unit_id: str, status: UnitStatus):
        self._status[unit_id] = status

    def get_status(self, unit_id: str) -> Optional[UnitStatus]:
        return self._status.get(unit_id)

    def set_output(self, unit_id: str, output: str):
        self._output[unit_id] = output

    def get_output(self, unit_id: str) -> str:
        return self._output.get(unit_id, "")

    def set_error(self, unit_id: str, error: str):
        self._error[unit_id] = error

    def get_error(self, unit_id: str) -> str:
        return self._error.get(unit_id, "")

    def is_completed(self, unit_id: str) -> bool:
        status = self.get_status(unit_id)
        return status in (UnitStatus.SUCCESS, UnitStatus.FAILED, UnitStatus.SKIPPED)


class StepStore:
    """Step 層級存放（屬於單一 Unit）"""

    def __init__(self, unit_id: str):
        self._unit_id = unit_id
        self._status: Dict[str, StepStatus] = {}
        self._output: Dict[str, str] = {}
        self._error: Dict[str, str] = {}
        self._goals: Dict[str, str] = {}

    @property
    def unit_id(self):
        return self._unit_id

    def set_status(self, step_id: str, status: StepStatus):
        self._status[step_id] = status

    def get_status(self, step_id: str) -> Optional[StepStatus]:
        return self._status.get(step_id)

    def set_output(self, step_id: str, output: str):
        self._output[step_id] = output

    def get_output(self, step_id: str) -> str:
        return self._output.get(step_id, "")

    def set_error(self, step_id: str, error: str):
        self._error[step_id] = error

    def get_error(self, step_id: str) -> str:
        return self._error.get(step_id, "")

    def set_goal(self, step_id: str, goal: str):
        self._goals[step_id] = goal

    def get_goal(self, step_id: str) -> str:
        return self._goals.get(step_id, "")

    def get_successful_steps(self) -> List[Tuple[str, str]]:
        """回傳已成功 Steps 的 [(step_id, goal), ...]"""
        return [(sid, self._goals.get(sid, ""))
                for sid, status in self._status.items()
                if status == StepStatus.SUCCESS]

    def clear(self):
        """清除所有 Step 資料（Unit 結束後使用）"""
        self._status.clear()
        self._output.clear()
        self._error.clear()
        self._goals.clear()
