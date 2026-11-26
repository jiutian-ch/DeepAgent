import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

@lru_cache(maxsize=1)
def get_llm_client():
    return ChatOpenAI(
        model=os.environ["ALIYUN_MODEL"],
        api_key=os.environ["aliQwen-api"],
        base_url=os.environ["ALIYUN_BASE_URL"]
    )