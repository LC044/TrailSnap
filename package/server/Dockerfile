# 使用官方Python镜像作为基础镜像
# FROM python:3.12.12-alpine3.21
FROM python:3.12.12-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件并安装

RUN pip install uv

# 复制项目所有文件到工作目录
COPY . .

RUN uv sync

# 暴露端口
EXPOSE 8000
# 核心：将虚拟环境的bin目录加入PATH
ENV PATH="/app/.venv/bin:$PATH"
# 运行应用
CMD ["python", "start.py"]