import json
import urllib.request
from urllib.error import URLError, HTTPError
import sys
from pathlib import Path
from urllib.parse import urlencode

import os

# 获取用户目录（永久目录，不会消失）
if os.name == "nt":  # Windows
    CONFIG_DIR = Path(os.getenv("APPDATA")) / "trailsnap"
else:  # Mac/Linux
    CONFIG_DIR = Path.home() / ".config" / "trailsnap"

# 确保目录存在
CONFIG_DIR.mkdir(exist_ok=True)

# .env 配置文件 永久保存在这里
ENV_FILE = CONFIG_DIR / ".env"

def load_env():
    if not ENV_FILE.exists():
        return {}
    env = {}
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip()
    return env

def save_env(url, token):
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(f"TRAILSNAP_API_URL={url}\n")
        f.write(f"TRAILSNAP_API_TOKEN={token}\n")
    print(f"配置已保存到 {ENV_FILE}")

JSON_ERRORS = "--json-errors" in sys.argv

def _print_error_and_exit(kind: str, code: int, msg: str, request_id: str = None):
    if JSON_ERRORS:
        err = {"kind": kind, "code": code, "msg": msg}
        if request_id:
            err["request_id"] = request_id
        print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
    else:
        print(f"错误 ({kind} {code}): {msg}", file=sys.stderr)
        if request_id:
            print(f"Request ID: {request_id}", file=sys.stderr)
    sys.exit(1)

def make_request(endpoint, params=None, method="GET", response_type="json", json_data=None, files=None):
    env = load_env()
    base_url = env.get("TRAILSNAP_API_URL")
    token = env.get("TRAILSNAP_API_TOKEN")
    
    if not base_url or not token:
        _print_error_and_exit("ConfigError", 401, "API URL 和 Token 未配置，请先运行 'config' 命令。")
        
    url = f"{base_url.rstrip('/')}{endpoint}"
    if params:
        # 过滤掉 None 值
        params = {k: v for k, v in params.items() if v is not None}
        if params:
            query_string = urlencode(params, doseq=True)
            url = f"{url}?{query_string}"
            
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    req_data = None
    if files:
        import mimetypes
        import uuid
        boundary = uuid.uuid4().hex
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        body = bytearray()
        for fieldname, f in files.items():
            filename = getattr(f, "name", "upload.bin")
            mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{fieldname}"; filename="{os.path.basename(filename)}"\r\n'.encode("utf-8"))
            body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
            body.extend(f.read())
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        req_data = bytes(body)
    elif json_data is not None:
        headers["Content-Type"] = "application/json"
        req_data = json.dumps(json_data).encode("utf-8")
    elif method in ("POST", "PUT", "PATCH"):
        headers["Content-Type"] = "application/json"
        req_data = b"{}"
    
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as response:
            req_id = response.headers.get("X-Request-Id", "")
            if response_type == "json":
                try:
                    result = json.loads(response.read().decode("utf-8"))
                except json.JSONDecodeError:
                    _print_error_and_exit("APIError", 500, "解析 JSON 响应失败", req_id)
                # 处理可能返回的统一结构 {"code": ..., "msg": ..., "data": ...}
                if isinstance(result, dict) and "code" in result and "msg" in result:
                    if result["code"] not in (200, 0):
                        _print_error_and_exit("APIError", result["code"], result.get('msg', '未知错误'), req_id)
                    # 如果有 data 字段，则返回 data，否则返回整个结构（兼容部分可能只需要成功状态的情况）
                    return result.get("data", result)
                return result
            elif response_type == "text":
                return response.read().decode("utf-8")
            if response_type == "bytes":
                return response.read()
            else:
                _print_error_and_exit("SystemError", 500, f"未知的响应类型: {response_type}", req_id)
    except HTTPError as e:
        req_id = e.headers.get("X-Request-Id", "")
        try:
            body = e.read().decode("utf-8")
            body_json = json.loads(body)
            msg = body_json.get("detail", body_json.get("msg", body))
        except Exception:
            msg = body if 'body' in locals() else str(e)
        
        kind = "AuthError" if e.code in (401, 403) else "NotFoundError" if e.code == 404 else "ClientError" if e.code < 500 else "ServerError"
        _print_error_and_exit(kind, e.code, msg, req_id)
    except URLError as e:
        _print_error_and_exit("NetworkError", 0, str(e.reason))
    except Exception as e:
        _print_error_and_exit("SystemError", 0, str(e))

load_env()