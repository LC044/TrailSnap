#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from commands import config, photos, tags, albums, locations, people, folders, medias
from output import set_formatter, OutputFormatter

VERSION = "0.4.0"

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="TrailSnap CLI 命令行工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    subparsers.required = True

    parser.add_argument("-v", "--version", action="version", version=VERSION)
    parser.add_argument(
        "--format",
        type=str,
        default="json",
        choices=OutputFormatter.SUPPORTED_FORMATS,
        help="输出格式: json (完整JSON，默认), pretty (人性化), table (表格), ndjson (换行分隔JSON), csv (逗号分隔值)"
    )

    # 注册各个子命令
    config.setup_parser(subparsers)
    photos.setup_parser(subparsers)
    tags.setup_parser(subparsers)
    albums.setup_parser(subparsers)
    locations.setup_parser(subparsers)
    people.setup_parser(subparsers)
    folders.setup_parser(subparsers)
    medias.setup_parser(subparsers)

    args = parser.parse_args()

    # 设置全局输出格式
    set_formatter(args.format)

    # 执行对应的命令处理函数
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
