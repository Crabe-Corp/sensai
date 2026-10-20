import os
from typing import Any, Dict
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import httpx

router = APIRouter()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ia:11434")

@router.get("/api/version")
async def get_ollama_version() -> Dict[str, Any]:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/version")
            return response.json()
        except Exception:
            return {"version": "0.1.0"}

@router.get("/api/tags")
async def get_ollama_tags() -> Dict[str, Any]:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return response.json()
        except Exception:
            return {"models": []}

@router.post("/api/show")
async def proxy_ollama_show(request: Request):
    body = await request.json()
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{OLLAMA_BASE_URL}/api/show", json=body)
        return response.json()


@router.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_catch_all(path: str, request: Request):
    if path == "chat":
        body = await request.json()
        is_stream = body.get("stream", True)
        
        if is_stream:
            async def stream_generator():
                async with httpx.AsyncClient() as client:
                    async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=body) as response:
                        async for chunk in response.aiter_bytes():
                            yield chunk
                            
            return StreamingResponse(stream_generator(), media_type="application/x-ndjson")
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=body)
                return response.json()
    
    method = request.method
    async with httpx.AsyncClient() as client:
        if method in ["GET", "DELETE"]:
            response = await client.request(method, f"{OLLAMA_BASE_URL}/api/{path}")
        else:
            body = await request.body()
            response = await client.request(method, f"{OLLAMA_BASE_URL}/api/{path}", content=body)
            
        if response.headers.get("content-type") == "application/x-ndjson":
            async def generic_stream():
                async with httpx.AsyncClient() as s_client:
                    async with s_client.stream(method, f"{OLLAMA_BASE_URL}/api/{path}", content=body) as s_response:
                        async for chunk in s_response.aiter_bytes():
                            yield chunk
            return StreamingResponse(generic_stream(), media_type="application/x-ndjson")
            
        try:
            return response.json()
        except Exception:
            return response.content