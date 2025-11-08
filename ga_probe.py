# ga_probe.py (logs only failed requests)
from fastapi import FastAPI, Request
from fastapi.responses import Response
import os, json, time, httpx, pathlib, traceback

UPSTREAM = os.getenv("UPSTREAM", "https://open.bigmodel.cn/api/paas/v4")
REWRITE  = os.getenv("REWRITE",  "1")         # 1=把 /v1/* 改写到智谱路径
LOGDIR   = pathlib.Path(os.getenv("LOGDIR", "/tmp/ghidrassist_debug"))
HTTP2    = os.getenv("HTTP2", "0") == "1"     # 需要 httpx[http2]，默认关
EMB_DIM  = os.getenv("EMBEDDING_DIM", "").strip()  # 例：export EMBEDDING_DIM=1024
THRESH   = int(os.getenv("LOG_THRESHOLD", "400"))  # 仅记录 >= THRESH 的响应
PREV_N   = int(os.getenv("PREVIEW_BYTES", "2048"))

LOGDIR.mkdir(parents=True, exist_ok=True)

EMBED_MODEL_MAP = {
    "text-embedding-ada-002": "embedding-3",
    "text-embedding-3-small": "embedding-3",
    "text-embedding-3-large": "embedding-3",
}
CHAT_MODEL_MAP = {
    "gpt-4o-mini": "glm-4-flash",
    "gpt-4o": "glm-4",
    "gpt-4.1-mini": "glm-4-flash",
    "gpt-4.1": "glm-4",
}

HOP_BY_HOP = {
    "connection","keep-alive","proxy-authenticate","proxy-authorization",
    "te","trailer","transfer-encoding","upgrade","host",
    "content-length","accept-encoding"
}

app = FastAPI()

def map_path(path: str) -> str:
    if REWRITE != "1":
        return f"{UPSTREAM.rstrip('/')}/{path.lstrip('/')}"
    if path.endswith("/v1/embeddings"):
        return f"{UPSTREAM.rstrip('/')}/embeddings"
    if path.endswith("/v1/chat/completions"):
        return f"{UPSTREAM.rstrip('/')}/chat/completions"
    if path in ("/v1", "/v1/"):
        return f"{UPSTREAM.rstrip('/')}/"
    return f"{UPSTREAM.rstrip('/')}/{path.lstrip('/').replace('v1/', '', 1)}"

def maybe_rewrite_body(path: str, headers: dict, body_bytes: bytes):
    ct = headers.get("content-type","").lower()
    if "application/json" not in ct:
        return body_bytes, None
    try:
        data = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        return body_bytes, None

    changed = {}
    if path.endswith("/v1/embeddings"):
        model = str(data.get("model",""))
        new_model = EMBED_MODEL_MAP.get(model)
        if new_model:
            data["model"] = new_model
            changed["model"] = {"from": model, "to": new_model}
        if EMB_DIM and str(data.get("model")) == "embedding-3" and "dimensions" not in data:
            try:
                data["dimensions"] = int(EMB_DIM)
                changed["dimensions"] = int(EMB_DIM)
            except ValueError:
                pass
    elif path.endswith("/v1/chat/completions"):
        model = str(data.get("model",""))
        new_model = CHAT_MODEL_MAP.get(model)
        if new_model:
            data["model"] = new_model
            changed["model"] = {"from": model, "to": new_model}

    if changed:
        return json.dumps(data, ensure_ascii=False).encode("utf-8"), changed
    return body_bytes, None

@app.api_route("/{full_path:path}", methods=["GET","POST","PUT","DELETE","PATCH"])
async def catch_all(req: Request, full_path: str):
    if full_path == "favicon.ico":
        return Response(status_code=204)

    ts  = time.strftime("%Y%m%d-%H%M%S")
    rid = f"{ts}-{int(time.time()*1000)%1000:03d}"
    try:
        body = await req.body()
        # 先准备“若失败才写”的请求摘要（去掉 Authorization）
        hdrs_log = dict(req.headers)
        had_auth = bool(hdrs_log.pop("authorization", None))
        try:
            body_preview = json.loads(body.decode("utf-8"))
        except Exception:
            body_preview = body[:PREV_N].decode("utf-8","ignore")

        # 可能重写模型名/维度（仅影响转发，不立即落盘）
        rewritten_body, rewrites = maybe_rewrite_body(f"/{full_path}", req.headers, body)
        if rewrites:
            body = rewritten_body
            hdrs_log["__rewrites__"] = rewrites

        dest = map_path(f"/{full_path}")
        if req.url.query:
            dest += f"?{req.url.query}"

        fwd_headers = {k: v for k, v in req.headers.items()
                       if v is not None and k.lower() not in HOP_BY_HOP}
        if "content-type" not in {k.lower() for k in fwd_headers}:
            fwd_headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(http2=HTTP2, timeout=60, follow_redirects=True) as client:
            r = await client.request(req.method, dest, content=body, headers=fwd_headers)

        # 仅在失败（status >= THRESH）时落盘请求/响应
        if r.status_code >= THRESH:
            (LOGDIR/f"{rid}-req.json").write_text(json.dumps({
                "rid": rid, "method": req.method, "path": f"/{full_path}",
                "has_auth": had_auth, "headers": hdrs_log, "body": body_preview
            }, ensure_ascii=False, indent=2))
            (LOGDIR/f"{rid}-resp.json").write_text(json.dumps({
                "rid": rid, "status": r.status_code, "headers": dict(r.headers),
                "preview": r.text[:PREV_N]
            }, ensure_ascii=False, indent=2))

        return Response(r.content, status_code=r.status_code,
                        media_type=r.headers.get("content-type","application/json"))
    except Exception as e:
        # 异常必落盘
        (LOGDIR/f"{rid}-error.json").write_text(json.dumps({
            "rid": rid, "error": str(e), "trace": traceback.format_exc()
        }, ensure_ascii=False, indent=2))
        return Response(json.dumps({"rid":rid,"error":str(e)}, ensure_ascii=False),
                        status_code=500, media_type="application/json")

