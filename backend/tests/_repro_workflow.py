"""Reproduce the chat workflow execution to diagnose the pending hang."""

import asyncio
import json
import logging
import time

logging.basicConfig(level=logging.INFO)

from tianshu.workflow.engine.engine import WorkflowEngine

WORKFLOW_ID = "1261c97f-d11a-462e-a0c4-1a6cbfca2c6f"


def load_workflow() -> dict:
    import os
    from tianshu.persistence import get_session_factory
    from tianshu.workflow.repository import WorkflowRepository

    os.environ.setdefault("TIAN_SHU_DATABASE", "postgres")
    factory = get_session_factory()
    session = factory()
    repo = WorkflowRepository(session)
    return asyncio.run(repo.get_by_id(WORKFLOW_ID))


def build_definition() -> dict:
    # Minimal equivalent of the stored workflow: input -> agent -> output
    return {
        "nodes": [
            {
                "id": "w1_input_1",
                "type": "input",
                "name": "用户输入",
                "config": {"input_key": "message", "default_value": ""},
            },
            {
                "id": "w1_agent_researcher",
                "type": "agent",
                "name": "调研员",
                "config": {
                    "agent_name": "researcher",
                    "model": "minimax-m3",
                    "system_prompt": "你是一个专业的市场调研员。",
                    "timeout": 30,
                },
            },
            {
                "id": "w1_output_1",
                "type": "output",
                "name": "最终输出",
                "config": {"aggregation": "merge"},
            },
        ],
        "edges": [
            {"id": "w1_e1", "source": "w1_input_1", "target": "w1_agent_researcher"},
            {"id": "w1_e2", "source": "w1_agent_researcher", "target": "w1_output_1"},
        ],
    }


async def main() -> None:
    definition = build_definition()
    engine = WorkflowEngine()
    inputs = {"message": "请 echo 一下 'MCP 联通测试'，并读取 notes.md 内容"}

    start = time.monotonic()
    event_count = 0
    try:
        async for event in engine.execute(
            workflow_id="w1",
            definition=definition,
            inputs=inputs,
            user_id="default",
            execution_id="repro-1",
        ):
            event_count += 1
            elapsed = time.monotonic() - start
            print(f"[{elapsed:.1f}s] EVENT {event.event_type}: {json.dumps(event.data, ensure_ascii=False)[:300]}")
            if event.event_type in ("workflow_failed", "workflow_completed", "workflow_cancelled"):
                break
            if elapsed > 90:
                print("TIMEOUT after 90s - still executing")
                break
    except Exception as exc:  # noqa: BLE001
        print(f"EXCEPTION: {type(exc).__name__}: {exc}")
    print(f"DONE in {time.monotonic() - start:.1f}s, {event_count} events")


if __name__ == "__main__":
    asyncio.run(main())
