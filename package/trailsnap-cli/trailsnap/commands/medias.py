import json
import os
import sys
from utils import make_request, load_env, normalize_trailsnap_url
from output import output, output_error, set_formatter, OutputFormatter


def _thumbnail_endpoint(photo_id, size):
    user = make_request("/users/me")
    owner_id = user.get("id") if isinstance(user, dict) else None
    if not owner_id:
        output_error("获取当前用户失败，无法生成缩略图地址")
        sys.exit(1)
    return f"/medias/{owner_id}/{photo_id}/thumbnail?size={size}"

def setup_parser(subparsers):
    parser = subparsers.add_parser("medias", help="获取和管理媒体文件")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    get_parser = sub_subparsers.add_parser("get", help="获取媒体文件")
    get_parser.add_argument("--photo-id", type=str, required=True, help="照片ID")
    get_parser.add_argument("--size", type=str, default="medium", help="照片质量，默认 medium，可选值：small,medium,large")
    get_parser.add_argument("--format", type=str, default="url", help="输出格式，默认 URL，可选值：url,base64,file,json,pretty,table")
    get_parser.add_argument("--output", type=str, default=None, help="输出文件路径，默认不保存，仅当format为file时有效")
    get_parser.set_defaults(func=execute_get)

def execute_get(args):
    set_formatter(args.format)
    env = load_env()
    photo_id = args.photo_id
    size = args.size
    if size not in ["small", "medium", "large"]:
        output_error("错误：size参数值必须为 small,medium,large 中的一个")
        sys.exit(1)
    format = args.format
    if format not in ["url", "base64", "file"] + OutputFormatter.SUPPORTED_FORMATS:
        output_error("错误：format参数值必须为 url,base64,file,json,pretty,table 中的一个")
        sys.exit(1)
    
    out_path = args.output
    base_url = env.get("TRAILSNAP_API_URL", "")
    if base_url:
        base_url = normalize_trailsnap_url(base_url)

    if format == "url":
        if not base_url:
            output_error("错误：TRAILSNAP_API_URL环境变量未设置")
            sys.exit(1)
        url = base_url + f"/medias/{photo_id}/file" if size == 'large' else base_url + _thumbnail_endpoint(photo_id, size)
        print(url)
    elif format == "base64":
        data = make_request(f"{_thumbnail_endpoint(photo_id, size)}&format=base64")
        if data and "base64" in data:
            print(data["base64"])
        else:
            output_error("获取 base64 失败")
            sys.exit(1)
    elif format == "file":
        if not out_path:
            output_error("错误：output参数值不能为空")
            sys.exit(1)
        data = make_request(f"/medias/{photo_id}/file", method="GET", response_type="bytes")
        if data:
            with open(out_path, "wb") as f:
                f.write(data)
            print(f"将文件保存到 {out_path}")
        else:
            output_error("获取文件失败")
            sys.exit(1)
    else:
        # For json, pretty, table
        url = base_url + f"/medias/{photo_id}/file" if size == 'large' else base_url + _thumbnail_endpoint(photo_id, size)
        output({"photo_id": photo_id, "size": size, "url": url})
