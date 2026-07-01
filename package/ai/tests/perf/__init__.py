"""AI 微服务各接口性能压测脚本包。

用法见 README.md。每个接口一个入口脚本（run_face.py / run_ocr.py / ...），
共享 runner.py 的异步压测引擎与 endpoints.py 的接口配置。
"""
