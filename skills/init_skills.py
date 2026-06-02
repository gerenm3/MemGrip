"""init_skills — Skill 初始化."""

import asyncio
import json
import logging

import config
from skills.skill_manager import SkillManager

logger = logging.getLogger(__name__)


_DEFAULT_SKILL = {
    "reasoning_resolution": {
        "core_concept": "根據任務複雜度調整推論的深度",
        "prompt_patterns": {
            "simple": "直接回答，無需拆解",
            "moderate": "分步驟說明",
            "complex": "鏈式推論"
        },
        "design_principles": ["按難度選擇推論深度", "避免過度思考簡單問題"],
        "pitfalls": ["簡單問題過度拆解", "複雜問題過於簡化"]
    },
    "constraint_rigidity": {
        "core_concept": "控制輸出格式的嚴格程度",
        "prompt_patterns": {
            "flexible": "自然語言為主",
            "structured": "帶有格式要求",
            "strict": "遵守固定 Schema"
        },
        "design_principles": ["根據下游需求決定格式"],
        "pitfalls": ["不必要的嚴格格式"]
    },
    "signal_noise_ratio": {
        "core_concept": "控制提供給模型上下文的精確度",
        "prompt_patterns": {
            "minimal": "只提供必要資訊",
            "rich": "包含相關背景"
        },
        "design_principles": ["精簡但不遺漏關鍵資訊"],
        "pitfalls": ["過多無關上下文"]
    },
    "boundary_anchoring": {
        "core_concept": "決定測試範圍的覆蓋程度",
        "prompt_patterns": {
            "happy_path": "聚焦正常流程",
            "edge_cases": "包含異常狀況"
        },
        "design_principles": ["根據需求決定覆蓋範圍"],
        "pitfalls": ["忽略關鍵邊界情況"]
    },
    "uncertainty_handling": {
        "core_concept": "處理不確定資訊的策略",
        "prompt_patterns": {
            "conservative": "資訊不足時要求澄清",
            "aggressive": "合理假設並繼續"
        },
        "design_principles": ["保守為主，避免錯誤假設"],
        "pitfalls": ["基於錯誤假設繼續執行"]
    }
}


def _write_default_skill(task_type: str, level: str) -> None:
    """寫入預設 Skill Guide（LLM 失敗時的 fallback）。"""
    sm = SkillManager()
    sm.init_skill_dirs(task_type, level)
    sm.save_skill(task_type, _DEFAULT_SKILL, level)
    logger.info("已寫入預設 %s skill for '%s' (LLM fallback)", level, task_type)


def _build_dimensions_text(dimensions: dict | list = None) -> str:
    """從 config.SKILL_DIMENSIONS 動態生成五個維度定義字串。"""
    if isinstance(dimensions, list):
        dim_dict = {k: config.SKILL_DIMENSIONS[k] for k in dimensions if k in config.SKILL_DIMENSIONS}
    else:
        dim_dict = dimensions or config.SKILL_DIMENSIONS

    lines = ["五個維度定義："]
    for idx, (key, dim) in enumerate(dim_dict.items(), start=1):
        lines.append(f"\n{idx}. {dim['name']}")
        lines.append(f"   方向範圍：{dim['range']}")
        lines.append(f"   描述：{dim['description']}")
    return "\n".join(lines)


def _build_l1_prompt(domain: str) -> str:
    """為 L1 生成 task type 的 prompt"""
    format_example = config.SKILL_FORMAT_EXAMPLE
    dimensions_text = _build_dimensions_text()

    return f"""你是一個 AI 任務規劃專家。請根據以下維度定義，為「{domain}」領域生成一份 L1 任務拆解的 skill guide。

L1 的職責是：將使用者的複雜請求拆解為獨立的執行單元（Unit）。

{dimensions_text}

只輸出 JSON，格式如下：
{format_example}"""


async def init_l1_skill(task_type: str = "general"):
    """為指定 task type 初始化 L1 skill guide."""
    level = "l1"
    skill_manager = SkillManager()
    skill_manager.init_skill_dirs(task_type, level)

    existing = skill_manager.load_skill(task_type, level)
    if existing and any(existing.get(d) for d in config.L1_SKILL_DIMENSIONS):
        logger.info("L1 skill for '%s' 已存在，跳過初始化", task_type)
        return existing

    prompt = _build_l1_prompt(task_type)
    messages = [
        {"role": "user", "content": prompt}
    ]

    try:
        from clients.model_client import OllamaClient
        client = OllamaClient()
        content, _ = await client.chat(
            config.LARGE_MODEL_NAME, messages,
            temperature=0.0, max_tokens=8192,
            think=False, caller="init_skills"
        )

        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("\n", 1)[0].strip()

        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            content = content[start:end + 1]

        skill_data = json.loads(content)
        skill_manager.save_skill(task_type, skill_data, level)
        logger.info("L1 skill for '%s' 已初始化", task_type)
        return skill_data
    except Exception as e:
        logger.error("[init_skills] L1 初始化失敗: %s", e, exc_info=True)
        _write_default_skill(task_type, level)
        return {}


async def init_all_l1_skills():
    """初始化所有 task type 的 L1 skill guide"""
    results = {}
    for task_type in config.TASK_TYPES:
        results[task_type] = await init_l1_skill(task_type)
    results["global"] = await init_l1_skill("global")
    return results


def _build_l2_prompt(domain: str) -> str:
    """為 L2 生成 task type 的 prompt"""
    format_example = config.SKILL_FORMAT_EXAMPLE
    dimensions_text = _build_dimensions_text()

    return f"""你是一個 AI 步驟規劃專家。請根據以下維度定義，為「{domain}」領域生成一份 L2 步驟規劃的 skill guide。

L2 的職責是：將單一執行單元（Unit）規劃為具體可執行的 Step 序列。

{dimensions_text}

只輸出 JSON，格式如下：
{format_example}"""


async def init_l2_skill(task_type: str = "general"):
    """為指定 task type 初始化 L2 skill guide."""
    level = "l2"
    skill_manager = SkillManager()
    skill_manager.init_skill_dirs(task_type, level)

    existing = skill_manager.load_skill(task_type, level)
    if existing and any(existing.get(d) for d in config.L2_SKILL_DIMENSIONS):
        logger.info("L2 skill for '%s' 已存在，跳過初始化", task_type)
        return existing

    prompt = _build_l2_prompt(task_type)
    messages = [
        {"role": "user", "content": prompt}
    ]

    try:
        from clients.model_client import OllamaClient
        client = OllamaClient()
        content, _ = await client.chat(
            config.LARGE_MODEL_NAME, messages,
            temperature=0.0, max_tokens=8192,
            think=False, caller="init_skills"
        )

        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("\n", 1)[0].strip()

        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            content = content[start:end + 1]

        skill_data = json.loads(content)
        skill_manager.save_skill(task_type, skill_data, level)
        logger.info("L2 skill for '%s' 已初始化", task_type)
        return skill_data
    except Exception as e:
        logger.error("[init_skills] L2 初始化失敗: %s", e, exc_info=True)
        _write_default_skill(task_type, level)
        return {}


async def init_all_l2_skills():
    """初始化所有 task type 的 L2 skill guide"""
    results = {}
    for task_type in config.TASK_TYPES:
        results[task_type] = await init_l2_skill(task_type)
    results["global"] = await init_l2_skill("global")
    return results


async def init_all():
    """完整初始化 L1 和 L2 的所有 skill guide"""
    l1_results = await init_all_l1_skills()
    l2_results = await init_all_l2_skills()
    return {"l1": l1_results, "l2": l2_results}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Initialize L1/L2 skill guides")
    parser.add_argument("target", choices=["l1", "l2", "all"], help="Which skill levels to initialize")
    parser.add_argument("--domain", choices=["general", "software_dev", "it_security", "global"], default=None)
    args = parser.parse_args()

    sm = SkillManager()
    sm.init_skill_dirs("global", "l1")
    sm.init_skill_dirs("global", "l2")

    if args.target == "l1":
        if args.domain:
            asyncio.run(init_l1_skill(args.domain))
        else:
            asyncio.run(init_all_l1_skills())
    elif args.target == "l2":
        if args.domain:
            asyncio.run(init_l2_skill(args.domain))
        else:
            asyncio.run(init_all_l2_skills())
    else:
        asyncio.run(init_all())