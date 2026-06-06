"""tests — 測試 Simple 路徑.

測試流程：
1. 組裝 Orchestrator
2. 模擬簡單查詢（路由到 simple 路徑）
3. 驗證回覆生成
"""

import asyncio
import sys
import os

# 確保專案根目錄在 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))


async def test_simple_path():
    """測試 simple 路徑"""
    from bootstrap import build_orchestrator
    from models.blueprints import Result
    
    # 組裝 Orchestrator
    print("[測試] 正在組裝 Orchestrator...")
    orc = build_orchestrator()
    print("[測試] Orchestrator 組裝成功")
    
    # 測試 simple 路徑
    print("\n[測試] 測試 simple 路徑...")
    
    # 模擬路由結果（simple intent）
    route_result = Result(
        success=True,
        data={
            "intent": "simple",
            "need_rag": False,
            "domain": "general",
        }
    )
    
    # 測試 dispatch_simple
    user_input = "你好，今天天氣如何？"
    try:
        reply = await orc._dispatch(route_result, user_input)
        print(f"[測試] Simple 路徑回覆:\n{reply}")
        print("\n[測試] Simple 路徑測試通過")
    except Exception as e:
        print(f"[測試] Simple 路徑測試失敗: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


async def main():
    """主測試函式"""
    print("=" * 50)
    print("v2 Simple 路徑測試")
    print("=" * 50)
    
    success = await test_simple_path()
    
    print("\n" + "=" * 50)
    if success:
        print("所有測試通過")
    else:
        print("測試失敗")
    print("=" * 50)
    
    return success


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
