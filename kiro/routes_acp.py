# -*- coding: utf-8 -*-
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from kiro.acp_models import JsonRpcRequest

router = APIRouter(tags=["ACP"])


@router.post("/acp")
async def acp_rpc(request: Request):
    payload = await request.json()
    rpc = JsonRpcRequest(**payload)
    client = request.app.state.acp_client
    try:
        result = await client.request(rpc.method, rpc.params)
        return JSONResponse({"jsonrpc": "2.0", "id": rpc.id, "result": result})
    except Exception as e:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": rpc.id,
                "error": {"code": -32000, "message": str(e)},
            },
            status_code=500,
        )
