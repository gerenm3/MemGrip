"""tests/L1/test_lvs -- 11 筆測試."""

import unittest

import pytest


class TestCalculateQ:
    """LVS.calculate_q 測試 (1-11)."""

    def test_calculate_q_all_zero_returns_zero(self, lvs_instance):
        task_record = {"final_status": "success", "units": [], "constraint_satisfied_ratio": 1.0, "avg_loop_count": 0}
        q = lvs_instance.calculate_q(task_record)
        assert q == 0

    def test_calculate_q_task_failed_only(self, lvs_instance):
        task_record = {"final_status": "failed", "units": [], "constraint_satisfied_ratio": 1.0, "avg_loop_count": 0}
        q = lvs_instance.calculate_q(task_record)
        assert q == 30

    def test_calculate_q_failed_units_capped_at_20(self, lvs_instance):
        units = [{"status": "FAILED"} for _ in range(3)]
        task_record = {"final_status": "success", "units": units, "constraint_satisfied_ratio": 1.0, "avg_loop_count": 0}
        q = lvs_instance.calculate_q(task_record)
        assert q == 20

    def test_calculate_q_failed_units_below_cap(self, lvs_instance):
        units = [{"status": "FAILED"} for _ in range(2)]
        task_record = {"final_status": "success", "units": units, "constraint_satisfied_ratio": 1.0, "avg_loop_count": 0}
        q = lvs_instance.calculate_q(task_record)
        assert q == 16

    def test_calculate_q_replan_capped_at_10(self, lvs_instance):
        units = [{"replan_count": 1}]
        task_record = {"final_status": "success", "units": units, "constraint_satisfied_ratio": 1.0, "avg_loop_count": 0}
        q = lvs_instance.calculate_q(task_record)
        assert q == 10

    def test_calculate_q_review_fail_capped_at_6(self, lvs_instance):
        task_record = {"session_id": "test_s1", "units": [], "constraint_satisfied_ratio": 1.0, "avg_loop_count": 0}
        with unittest.mock.patch.object(lvs_instance, '_count_review_fails', return_value=2):
            q = lvs_instance.calculate_q(task_record)
            assert q == 6

    def test_calculate_q_loop_hit_capped_at_4(self, lvs_instance):
        # loop_hit counts units with total_loop_count >= 5 (LOOP_HIT_THRESHOLD)
        units = [{"total_loop_count": 5}, {"total_loop_count": 5}]
        task_record = {"final_status": "success", "units": units, "constraint_satisfied_ratio": 1.0, "avg_loop_count": 0}
        q = lvs_instance.calculate_q(task_record)
        assert q == 4

    def test_calculate_q_unsatisfied_constraints_capped_at_15(self, lvs_instance):
        constraint_list = [{"satisfied": False} for _ in range(3)]
        units = [{"constraint_checks": constraint_list}]
        task_record = {"final_status": "success", "units": units, "constraint_satisfied_ratio": 1.0, "avg_loop_count": 0}
        q = lvs_instance.calculate_q(task_record)
        assert q == 15

    def test_calculate_q_constraint_penalty_when_ratio_below_0_7(self, lvs_instance):
        # ratio=0.5, penalty = (0.7-0.5)/0.7 * 10 = 2.857...
        task_record = {"final_status": "success", "units": [], "constraint_satisfied_ratio": 0.5, "avg_loop_count": 0}
        q = lvs_instance.calculate_q(task_record)
        assert abs(q - 2.8571428571428563) < 0.001

    def test_calculate_q_loop_excess_when_avg_above_3(self, lvs_instance):
        # avg_loop=5, excess = (5-3)*3 = 6
        task_record = {"final_status": "success", "units": [], "constraint_satisfied_ratio": 1.0, "avg_loop_count": 5}
        q = lvs_instance.calculate_q(task_record)
        assert q == 6

    def test_calculate_q_max_score_capped_at_96_actual_cap(self, lvs_instance):
        """總和超過 MAX_Q_SCORE=96 時，上限真正生效。
        
        mock _count_review_fails=2 讓 review_fail 貢獻 6 分。
        計算：30+20+10+6+4+15+10+6+6 = 107，min(107, 96) = 96。
        """
        constraint_list = [{"satisfied": False} for _ in range(3)]
        unit_list = [
            {"status": "FAILED", "replan_count": 1, "total_loop_count": 5, "constraint_checks": constraint_list}
            for _ in range(3)
        ]
        task_record = {"session_id": "test_s1", "final_status": "failed", "units": unit_list, "constraint_satisfied_ratio": 0.0, "avg_loop_count": 10}
        with unittest.mock.patch.object(lvs_instance, '_count_review_fails', return_value=2):
            q = lvs_instance.calculate_q(task_record)
            assert q == 96
