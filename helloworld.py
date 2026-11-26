# import os
# from typing import Literal
# from dotenv import load_dotenv
#
# from langchain_openai import ChatOpenAI
# from tavily import TavilyClient
# from deepagents import create_deep_agent
#
# load_dotenv()
#
# # os.environ.setdefault("LANGSMITH_PROJECT", "deep_agent-test")
#
#
#
# os.environ.setdefault("LANGSMITH_TRACING", "true")
#
# tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
#
#
# def internet_search(
#     query: str,
#     max_results: int = 5,
#     topic: Literal["general", "news", "finance"] = "general",
#     include_raw_content: bool = False,
# ):
#     """Run a web search"""
#     return tavily_client.search(
#         query,
#         max_results=max_results,
#         include_raw_content=include_raw_content,
#         topic=topic,
#     )
#
# llm = ChatOpenAI(model="qwen3.7-max-2026-06-08",
#     api_key=os.environ["aliQwen-api"],
#     base_url="https://ws-d9yzr1rh2zyvixam.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
#   )
#
# agent = create_deep_agent(
#     model=llm,
#     tools=[internet_search],
#     system_prompt="你是一个智能助手，有必要时可以调用工具回答用户的问题",
# )
#
# result = agent.invoke({"messages": [{"role": "user", "content": "帮我看一下广东清远的最新天气"}]})
#
# # Print the agent's response
# print(result["messages"][-1].content)