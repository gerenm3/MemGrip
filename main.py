"""
MemGrip - Entry Point
Basic chat loop with Ollama backend.
Memory layer will be integrated in Week 2-3.
"""

import asyncio
from core import Orchestrator

if __name__ == "__main__":
    o = Orchestrator(trace_logger=None, optimization_advisor=None)
    asyncio.run(o.run())
