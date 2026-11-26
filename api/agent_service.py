from pathlib import Path

from fastapi import FastAPI
from starlette.responses import FileResponse

import uvicorn
from app import main
from starlette.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/query_agent/{query}")
async def query_agent(query: str):
    return await main(query)


@app.get("/", include_in_schema=False)
@app.get("/index", include_in_schema=False)
async def get_index():
    travel_agent_path = Path(__file__).parents[1]

    index_path = travel_agent_path / "pages/index.html"
    return FileResponse(
        path=index_path,
        status_code=200,
        media_type="text/html",
    )


if __name__ == "__main__":

    uvicorn.run(app, host="0.0.0.0", port=8000)
