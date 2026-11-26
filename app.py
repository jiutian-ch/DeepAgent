import asyncio
import logging
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from core.map_agent import map_agent
from core.summary_agent import summary_agent
# from core.map_agent import map_agent
from core.ticket_agent import ticket_agent
from utils.llm_utils import get_llm_client
from utils.memory_utils import remember_turn

logger = logging.getLogger(__name__)

# 用绝对路径作为虚拟文件系统根目录，避免从其他工作目录启动时找不到 memory/AGENTS.md
PROJECT_ROOT = Path(__file__).resolve().parent

MAIN_AGENT_PROMPT = """
你是一名旅游规划总控智能体。
你的职责是根据用户输入，先抽取关键信息，再调度合适的子智能体完成任务。

规则：
1. 先从用户输入中抽取：出发地、目的地、日期/天数、预算、偏好、出行节奏
2. 如果用户没有明确说明游玩天数，默认按 1 天规划
3. 如果用户没有明确说明预算，默认按中等预算规划
4. 如果用户没有明确说明偏好，默认按“经典景点 + 少折腾”规划
5. 如果用户没有明确说明出行节奏，默认按“舒适型节奏”规划
6. 景点、路线、地图相关问题交给 map_agent
7. 火车票、车次、票价、时间建议交给 ticket_agent
8. 最终结果交给 summary_agent 汇总
9. 输出必须使用中文
10. 不做真实购票，只做规划和建议
"""


llm = get_llm_client()

main_agent = create_deep_agent(
    name="旅游规划助手",
    model=llm,
    system_prompt=MAIN_AGENT_PROMPT,
    backend=FilesystemBackend(root_dir=str(PROJECT_ROOT), virtual_mode=True),
    memory=["/memory/AGENTS.md"],
    subagents=[map_agent,ticket_agent,summary_agent],
)

async def main(query: str):
    result = main_agent.astream(
        input = {
            "messages":[
                {"role": "user", "content": query}
            ]
        }
    )

    tool_dict = {}

    async for chunk in result:
        for key, value in chunk.items():
            if key == "model":
                ai_message = value["messages"][-1]

                tool_calls = ai_message.tool_calls

                if tool_calls:
                    for tool_call in tool_calls:
                        tool_name = tool_call["args"]["subagent_type"]
                        args = tool_call["args"]["description"]
                        tool_id = tool_call["id"]
                        tool_dict[tool_id] = tool_name
                        print(f"调用工具：【{tool_name}】子智能体，传入参数是：{args}")

                else:

                    final_output = ai_message.content

                    print(f"旅游规划助手最终的输出是：{final_output}")

                    # 每轮对话结束后写入长期记忆（失败不影响本轮回复）
                    try:
                        await remember_turn(query, final_output)
                    except Exception:
                        logger.exception("写入对话记忆失败")

                    return final_output
            elif key == "tool_calls":
                tool_message = value["messages"][-1]
                content = tool_message.content
                tool_id = tool_message.tool_call_id
                tool_name = tool_dict[tool_id]
                print(f"子智能体 【{tool_name}】 返回的结果是：{content}")

if __name__ == "__main__":
    asyncio.run(main("帮我做一个北京到天津一日游的旅游规划"))
