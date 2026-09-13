from typing import Any


def ok(data: Any = None, msg: str = "success") -> dict[str, Any]:
    return {"code": 0, "msg": msg, "data": data}
