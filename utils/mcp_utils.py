from functools import lru_cache

from langchain_mcp_adapters.client import MultiServerMCPClient


@lru_cache(maxsize=1)
def get_mcp_client():
    return MultiServerMCPClient(
        {
            "12306-mcp": {
                "transport": "streamable_http",
                "url": "https://mcp.api-inference.modelscope.net/f4a37c57dab44b/mcp"
            }
        }
    )


