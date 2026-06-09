"""L1 test for Config (module 21) - constants in config.py.

Black-box testing: only read docs/test_plan_l1/21_config.md and api_signatures.md.
No source code reading of config.py.
"""

import pytest
from pathlib import Path
import config


class TestValidIntents:
    """TC-21-01 ~ TC-21-04: VALID_INTENTS."""

    def test_TC21_01_valid_intents_contains_simple(self):
        assert "simple" in config.VALID_INTENTS

    def test_TC21_02_valid_intents_contains_tool(self):
        assert "tool" in config.VALID_INTENTS

    def test_TC21_03_valid_intents_contains_complex(self):
        assert "complex" in config.VALID_INTENTS

    def test_TC21_04_valid_intents_length(self):
        assert len(config.VALID_INTENTS) == 3


class TestMaxReplanAttempts:
    """TC-21-05: MAX_REPLAN_ATTEMPTS."""

    def test_TC21_05_max_replan_attempts(self):
        assert config.MAX_REPLAN_ATTEMPTS == 2


class TestContextSafetyRatio:
    """TC-21-06: CONTEXT_SAFETY_RATIO."""

    def test_TC21_06_context_safety_ratio(self):
        assert config.CONTEXT_SAFETY_RATIO == 0.8


class TestApprovalTimeout:
    """TC-21-07: APPROVAL_TIMEOUT."""

    def test_TC21_07_approval_timeout(self):
        assert config.APPROVAL_TIMEOUT == 1800


class TestEmbeddingThreshold:
    """TC-21-08: EMBEDDING_THRESHOLD."""

    def test_TC21_08_embedding_threshold(self):
        assert config.EMBEDDING_THRESHOLD == 0.75


class TestMaxClarifyRounds:
    """TC-21-09: MAX_CLARIFY_ROUNDS."""

    def test_TC21_09_max_clarify_rounds(self):
        assert config.MAX_CLARIFY_ROUNDS == 2


class TestClarifyTimeout:
    """TC-21-10: CLARIFY_TIMEOUT."""

    def test_TC21_10_clarify_timeout(self):
        assert config.CLARIFY_TIMEOUT == 20


class TestClarifyMaxAttempts:
    """TC-21-11: CLARIFY_MAX_ATTEMPTS."""

    def test_TC21_11_clarify_max_attempts(self):
        assert config.CLARIFY_MAX_ATTEMPTS == 3


class TestLlmTimeout:
    """TC-21-12: LLM_TIMEOUT."""

    def test_TC21_12_llm_timeout(self):
        assert config.LLM_TIMEOUT == 120


class TestClarifyTemperature:
    """TC-21-13: CLARIFY_TEMPERATURE."""

    def test_TC21_13_clarify_temperature(self):
        assert config.CLARIFY_TEMPERATURE == 0.5


class TestClarifyMaxTokens:
    """TC-21-14: CLARIFY_MAX_TOKENS."""

    def test_TC21_14_clarify_max_tokens(self):
        assert config.CLARIFY_MAX_TOKENS == 2048


class TestRouterModelName:
    """TC-21-15: ROUTER_MODEL_NAME."""

    def test_TC21_15_router_model_name_non_empty(self):
        assert config.ROUTER_MODEL_NAME != ""


class TestModelLarge:
    """TC-21-16: MODEL_LARGE."""

    def test_TC21_16_model_large(self):
        assert config.MODEL_LARGE == "large"


class TestModelMedium:
    """TC-21-17: MODEL_MEDIUM."""

    def test_TC21_17_model_medium(self):
        assert config.MODEL_MEDIUM == "medium"


class TestModelEmbedding:
    """TC-21-18: MODEL_EMBEDDING."""

    def test_TC21_18_model_embedding_non_empty(self):
        assert config.MODEL_EMBEDDING != ""


class TestMaxRetries:
    """TC-21-19: MAX_RETRIES."""

    def test_TC21_19_max_retries(self):
        assert config.MAX_RETRIES == 15


class TestTemperature:
    """TC-21-20: TEMPERATURE."""

    def test_TC21_20_temperature(self):
        assert config.TEMPERATURE == 0.7


class TestRouteTemperature:
    """TC-21-21: ROUTE_TEMPERATURE."""

    def test_TC21_21_route_temperature(self):
        assert config.ROUTE_TEMPERATURE == 0.0


class TestSummaryTemperature:
    """TC-21-22: SUMMARY_TEMPERATURE."""

    def test_TC21_22_summary_temperature(self):
        assert config.SUMMARY_TEMPERATURE == 0.2


class TestDisassemblyTemperature:
    """TC-21-23: DISASSEMBLY_TEMPERATURE."""

    def test_TC21_23_disassembly_temperature(self):
        assert config.DISASSEMBLY_TEMPERATURE == 0.0


class TestStepTemperature:
    """TC-21-24: STEP_TEMPERATURE."""

    def test_TC21_24_step_temperature(self):
        assert config.STEP_TEMPERATURE == 0.0


class TestStepExecuteTemperature:
    """TC-21-25: STEP_EXECUTE_TEMPERATURE."""

    def test_TC21_25_step_execute_temperature(self):
        assert config.STEP_EXECUTE_TEMPERATURE == 0.0


class TestIntegrationTemperature:
    """TC-21-26: INTEGRATION_TEMPERATURE."""

    def test_TC21_26_integration_temperature(self):
        assert config.INTEGRATION_TEMPERATURE == 0.3


class TestAgenticTemperature:
    """TC-21-27: AGENTIC_TEMPERATURE."""

    def test_TC21_27_agentic_temperature(self):
        assert config.AGENTIC_TEMPERATURE == 0.0


class TestMaxTokens:
    """TC-21-28: MAX_TOKENS."""

    def test_TC21_28_max_tokens(self):
        assert config.MAX_TOKENS == 8192


class TestDisassemblyMaxTokens:
    """TC-21-29: DISASSEMBLY_MAX_TOKENS."""

    def test_TC21_29_disassembly_max_tokens(self):
        assert config.DISASSEMBLY_MAX_TOKENS == 32768


class TestStepMaxTokens:
    """TC-21-30: STEP_MAX_TOKENS."""

    def test_TC21_30_step_max_tokens(self):
        assert config.STEP_MAX_TOKENS == 16384


class TestStepExecuteMaxIterations:
    """TC-21-31: STEP_EXECUTE_MAX_ITERATIONS."""

    def test_TC21_31_step_execute_max_iterations(self):
        assert config.STEP_EXECUTE_MAX_ITERATIONS == 5


class TestThink:
    """TC-21-32: THINK."""

    def test_TC21_32_think(self):
        assert config.THINK is False


class TestDisassemblyThink:
    """TC-21-33: DISASSEMBLY_THINK."""

    def test_TC21_33_disassembly_think(self):
        assert config.DISASSEMBLY_THINK is True


class TestStepThink:
    """TC-21-34: STEP_THINK."""

    def test_TC21_34_step_think(self):
        assert config.STEP_THINK is False


class TestStepExecuteThink:
    """TC-21-35: STEP_EXECUTE_THINK."""

    def test_TC21_35_step_execute_think(self):
        assert config.STEP_EXECUTE_THINK is False


class TestIntegrationThink:
    """TC-21-36: INTEGRATION_THINK."""

    def test_TC21_36_integration_think(self):
        assert config.INTEGRATION_THINK is False


class TestAgenticThink:
    """TC-21-37: AGENTIC_THINK."""

    def test_TC21_37_agentic_think(self):
        assert config.AGENTIC_THINK is False


class TestImportanceHigh:
    """TC-21-38: IMPORTANCE_HIGH."""

    def test_TC21_38_importance_high(self):
        assert config.IMPORTANCE_HIGH == 0.7


class TestImportanceLow:
    """TC-21-39: IMPORTANCE_LOW."""

    def test_TC21_39_importance_low(self):
        assert config.IMPORTANCE_LOW == 0.3


class TestSimilarityUpperBoundary:
    """TC-21-40: SIMILARITY_UPPER_BOUNDARY."""

    def test_TC21_40_similarity_upper_boundary(self):
        assert config.SIMILARITY_UPPER_BOUNDARY == 0.7


class TestBufferMaxTokens:
    """TC-21-41: BUFFER_MAX_TOKENS."""

    def test_TC21_41_buffer_max_tokens(self):
        assert config.BUFFER_MAX_TOKENS == 800


class TestVectorRepairInterval:
    """TC-21-42: VECTOR_REPAIR_INTERVAL."""

    def test_TC21_42_vector_repair_interval(self):
        assert config.VECTOR_REPAIR_INTERVAL == 50


class TestEnableWebSearch:
    """TC-21-43: ENABLE_WEB_SEARCH."""

    def test_TC21_43_enable_web_search(self):
        assert config.ENABLE_WEB_SEARCH is True


class TestEnableFileRW:
    """TC-21-44: ENABLE_FILE_RW."""

    def test_TC21_44_enable_file_rw(self):
        assert config.ENABLE_FILE_RW is True


class TestEnableTaskManager:
    """TC-21-45: ENABLE_TASK_MANAGER."""

    def test_TC21_45_enable_task_manager(self):
        assert config.ENABLE_TASK_MANAGER is True


class TestSkillDimensions:
    """TC-21-46: SKILL_DIMENSIONS length."""

    def test_TC21_46_skill_dimensions_length(self):
        assert len(config.SKILL_DIMENSIONS) == 5


class TestL1SkillDimensions:
    """TC-21-47: L1_SKILL_DIMENSIONS length."""

    def test_TC21_47_l1_skill_dimensions_length(self):
        assert len(config.L1_SKILL_DIMENSIONS) == 5


class TestL2SkillDimensions:
    """TC-21-48: L2_SKILL_DIMENSIONS length."""

    def test_TC21_48_l2_skill_dimensions_length(self):
        assert len(config.L2_SKILL_DIMENSIONS) == 5


class TestLVSEventScoresTaskFailed:
    """TC-21-49: LVS_EVENT_SCORES task_failed."""

    def test_TC21_49_lvs_event_scores_task_failed(self):
        assert config.LVS_EVENT_SCORES["task_failed"] == 30


class TestLVSEventScoresUnitFailed:
    """TC-21-50: LVS_EVENT_SCORES unit_failed."""

    def test_TC21_50_lvs_event_scores_unit_failed(self):
        assert config.LVS_EVENT_SCORES["unit_failed"] == 8


class TestLVSEventScoresReplan:
    """TC-21-51: LVS_EVENT_SCORES replan."""

    def test_TC21_51_lvs_event_scores_replan(self):
        assert config.LVS_EVENT_SCORES["replan"] == 10


class TestLVSEventScoresReviewFail:
    """TC-21-52: LVS_EVENT_SCORES review_fail."""

    def test_TC21_52_lvs_event_scores_review_fail(self):
        assert config.LVS_EVENT_SCORES["review_fail"] == 3


class TestLVSEventScoresLoopHit:
    """TC-21-53: LVS_EVENT_SCORES loop_hit."""

    def test_TC21_53_lvs_event_scores_loop_hit(self):
        assert config.LVS_EVENT_SCORES["loop_hit"] == 4


class TestTaskTypes:
    """TC-21-54: TASK_TYPES non-empty."""

    def test_TC21_54_task_types_non_empty(self):
        assert len(config.TASK_TYPES) > 0


class TestLogsDir:
    """TC-21-55: LOGS_DIR non-empty."""

    def test_TC21_55_logs_dir_non_empty(self):
        assert config.LOGS_DIR != ""


class TestTraceLogPath:
    """TC-21-56: TRACE_LOG_PATH non-empty."""

    def test_TC21_56_trace_log_path_non_empty(self):
        assert config.TRACE_LOG_PATH != ""


class TestHealthLogPath:
    """TC-21-57: HEALTH_LOG_PATH non-empty."""

    def test_TC21_57_health_log_path_non_empty(self):
        assert config.HEALTH_LOG_PATH != ""


class TestSignalLogPath:
    """TC-21-58: SIGNAL_LOG_PATH non-empty."""

    def test_TC21_58_signal_log_path_non_empty(self):
        assert config.SIGNAL_LOG_PATH != ""


class TestChromaDbPath:
    """TC-21-59: CHROMA_DB_PATH non-empty."""

    def test_TC21_59_chroma_db_path_non_empty(self):
        assert config.CHROMA_DB_PATH != ""


class TestCollectionSummaryName:
    """TC-21-60: COLLECTION_SUMMARY_NAME non-empty."""

    def test_TC21_60_collection_summary_name_non_empty(self):
        assert config.COLLECTION_SUMMARY_NAME != ""


class TestCollectionRawName:
    """TC-21-61: COLLECTION_RAW_NAME non-empty."""

    def test_TC21_61_collection_raw_name_non_empty(self):
        assert config.COLLECTION_RAW_NAME != ""


class TestTempCacheMaxTokens:
    """TC-21-62: TEMP_CACHE_MAX_TOKENS positive integer."""

    def test_TC21_62_temp_cache_max_tokens_positive(self):
        assert config.TEMP_CACHE_MAX_TOKENS > 0


class TestTempCacheMaxItems:
    """TC-21-63: TEMP_CACHE_MAX_ITEMS positive integer."""

    def test_TC21_63_temp_cache_max_items_positive(self):
        assert config.TEMP_CACHE_MAX_ITEMS > 0


class TestTempCacheIdleSeconds:
    """TC-21-64: TEMP_CACHE_IDLE_SECONDS positive integer."""

    def test_TC21_64_temp_cache_idle_seconds_positive(self):
        assert config.TEMP_CACHE_IDLE_SECONDS > 0


class TestTempCacheTopK:
    """TC-21-65: TEMP_CACHE_TOP_K positive integer."""

    def test_TC21_65_temp_cache_top_k_positive(self):
        assert config.TEMP_CACHE_TOP_K > 0


class TestTempCacheDecayLambda:
    """TC-21-66: TEMP_CACHE_DECAY_LAMBDA positive float."""

    def test_TC21_66_temp_cache_decay_lambda_positive(self):
        assert config.TEMP_CACHE_DECAY_LAMBDA > 0


class TestTempCacheEvictionThreshold:
    """TC-21-67: TEMP_CACHE_EVICTION_THRESHOLD between 0 and 1."""

    def test_TC21_67_temp_cache_eviction_threshold_between_0_and_1(self):
        assert 0 < config.TEMP_CACHE_EVICTION_THRESHOLD < 1


class TestPatternsPath:
    """TC-21-68: PATTERNS_PATH non-empty."""

    def test_TC21_68_patterns_path_non_empty(self):
        assert config.PATTERNS_PATH != ""


class TestFileRWBasePath:
    """TC-21-69: FILE_RW_BASE_PATH non-empty."""

    def test_TC21_69_file_rw_base_path_non_empty(self):
        assert config.FILE_RW_BASE_PATH != ""


class TestBaseRoles:
    """TC-21-70: BASE_ROLES non-empty."""

    def test_TC21_70_base_roles_non_empty(self):
        assert len(config.BASE_ROLES) > 0


class TestSkillDirBase:
    """TC-21-71: SKILL_DIR_BASE Path type."""

    def test_TC21_71_skill_dir_base_is_path(self):
        assert isinstance(config.SKILL_DIR_BASE, Path)


class TestLLMMode:
    """TC-21-72: LLM_MODE valid value."""

    def test_TC21_72_llm_mode_valid_value(self):
        assert config.LLM_MODE in ("local", "cloud", "hybrid")


class TestDebugMode:
    """TC-21-73: DEBUG_MODE bool type."""

    def test_TC21_73_debug_mode_is_bool(self):
        assert isinstance(config.DEBUG_MODE, bool)


class TestMcpTimeoutSeconds:
    """TC-21-74: MCP_TIMEOUT_SECONDS >= 1."""

    def test_TC21_74_mcp_timeout_seconds_ge_1(self):
        assert config.MCP_TIMEOUT_SECONDS >= 1


class TestRouteMaxTokens:
    """TC-21-75: ROUTE_MAX_TOKENS."""

    def test_TC21_75_route_max_tokens(self):
        assert config.ROUTE_MAX_TOKENS == 8192


class TestSummaryMaxTokens:
    """TC-21-76: SUMMARY_MAX_TOKENS."""

    def test_TC21_76_summary_max_tokens(self):
        assert config.SUMMARY_MAX_TOKENS == 8192


class TestStepExecuteMaxTokens:
    """TC-21-77: STEP_EXECUTE_MAX_TOKENS."""

    def test_TC21_77_step_execute_max_tokens(self):
        assert config.STEP_EXECUTE_MAX_TOKENS == 16384


class TestIntegrationMaxTokens:
    """TC-21-78: INTEGRATION_MAX_TOKENS."""

    def test_TC21_78_integration_max_tokens(self):
        assert config.INTEGRATION_MAX_TOKENS == 8192


class TestToolExecutionMaxTokens:
    """TC-21-79: TOOL_EXECUTION_MAX_TOKENS."""

    def test_TC21_79_tool_execution_max_tokens(self):
        assert config.TOOL_EXECUTION_MAX_TOKENS == 8192


class TestAgenticMaxTokens:
    """TC-21-80: AGENTIC_MAX_TOKENS."""

    def test_TC21_80_agentic_max_tokens(self):
        assert config.AGENTIC_MAX_TOKENS == 2048