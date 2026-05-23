# init_skills.py

import asyncio
import ollama
import json
import os
from skill_manager import init_skill_dirs, save_skill

MODEL = "qwen3.6:35b-a3b"

DIMENSIONS = """
五個維度定義：

1. 推論解析度 (Reasoning Resolution)
   方向範圍：direct → step_by_step → chain_of_thought
   描述：模型思考的步長，決定推導過程的顯式程度

2. 約束剛性 (Constraint Rigidity)
   方向範圍：guideline → rule → hard_schema
   描述：模型的自由度與合規性的平衡

3. 資訊信噪比 (Signal-to-Noise Ratio)
   方向範圍：minimal → balanced → rich
   描述：核心上下文與邊緣資訊的比例

4. 邊界錨定 (Boundary Anchoring)
   方向範圍：happy_path → mixed → edge_cases
   描述：典型案例與邊緣案例的比例

5. 不確定性處置 (Uncertainty Handling)
   方向範圍：aggressive → balanced → conservative
   描述：資訊不足時的行為模式
"""

async def generate_global_skills():
    client = ollama.AsyncClient()

    response = await client.chat(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": f"""
你是一個 prompt 設計系統。

以下是五個維度的定義：
{DIMENSIONS}

請為每個維度生成一份 skill 指導文件。
skill 指導的目的是：當大模型在生成任務規劃的 prompt 時，根據當前維度的設定方向，知道應該怎麼設計這個 prompt。

請自行決定每份 skill 指導應該包含什麼內容和結構。

只輸出 JSON，不要有任何其他文字：
{{
  "reasoning_resolution": {{ }},
  "constraint_rigidity": {{ }},
  "signal_noise_ratio": {{ }},
  "boundary_anchoring": {{ }},
  "uncertainty_handling": {{ }}
}}
"""
            }
        ],
        options={"temperature": 0}
    )

    content = response['message']['content']
    
    # 清理可能的 markdown 標記
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0]
    
    skill_data = json.loads(content)
    
    # 初始化目錄
    init_skill_dirs()
    
    # 存進 global
    save_skill("global", skill_data)
    print("Global skill 指導已初始化")
    print(f"路徑：/home/kali/memgrip/skills/global/current.json")

asyncio.run(generate_global_skills())
