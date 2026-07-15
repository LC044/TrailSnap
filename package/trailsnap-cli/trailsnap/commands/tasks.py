import json
import time
import sys
import requests
from utils import make_request, load_env
from output import output, output_success, output_error, OutputFormatter, get_formatter

def setup_parser(subparsers):
    parser = subparsers.add_parser("tasks", help="任务管理和查询")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    # list subcommand
    list_parser = sub_subparsers.add_parser("list", help="获取任务列表")
    list_parser.add_argument("--status", type=str, help="按状态过滤")
    list_parser.add_argument("--type", type=str, help="按任务类型过滤")
    list_parser.add_argument("--limit", type=int, default=50, help="限制返回数量")
    list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    list_parser.set_defaults(func=execute_list)

    # info subcommand
    info_parser = sub_subparsers.add_parser("info", help="根据 ID 获取任务详情")
    info_parser.add_argument("--id", required=True, help="任务 UUID")
    info_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    info_parser.set_defaults(func=execute_info)

    # status subcommand
    status_parser = sub_subparsers.add_parser("status", help="获取全局任务状态")
    status_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    status_parser.set_defaults(func=execute_status)

    # grouped subcommand
    grouped_parser = sub_subparsers.add_parser("grouped", help="按状态分组统计任务")
    grouped_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    grouped_parser.set_defaults(func=execute_grouped)

    # create subcommand
    create_parser = sub_subparsers.add_parser("create", help="创建新任务")
    create_parser.add_argument("--type", required=True, help="任务类型")
    group = create_parser.add_mutually_exclusive_group()
    group.add_argument("--payload-json", type=str, help="JSON 格式的任务附加数据")
    group.add_argument("--payload-file", type=str, help="包含 JSON 格式任务附加数据的文件路径")
    create_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    create_parser.set_defaults(func=execute_create)

    # cancel subcommand
    cancel_parser = sub_subparsers.add_parser("cancel", help="取消任务")
    cancel_parser.add_argument("--id", required=True, help="任务 UUID")
    cancel_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    cancel_parser.set_defaults(func=execute_cancel)

    # retry subcommand
    retry_parser = sub_subparsers.add_parser("retry", help="重试任务")
    retry_parser.add_argument("--id", required=True, help="任务 UUID")
    retry_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    retry_parser.set_defaults(func=execute_retry)

    # retry-all-failed subcommand
    retry_all_failed_parser = sub_subparsers.add_parser("retry-all-failed", help="重试所有失败任务")
    retry_all_failed_parser.add_argument("--types", type=str, help="指定任务类型，多个用逗号分隔")
    retry_all_failed_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    retry_all_failed_parser.set_defaults(func=execute_retry_all_failed)

    # clear-failed subcommand
    clear_failed_parser = sub_subparsers.add_parser("clear-failed", help="删除失败任务")
    clear_failed_parser.add_argument("--types", type=str, help="指定任务类型，多个用逗号分隔")
    clear_failed_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    clear_failed_parser.set_defaults(func=execute_clear_failed)

    # wait subcommand
    wait_parser = sub_subparsers.add_parser("wait", help="轮询等待任务完成")
    wait_parser.add_argument("--id", required=True, help="任务 UUID")
    wait_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    wait_parser.set_defaults(func=execute_wait)

    # pause subcommand
    pause_parser = sub_subparsers.add_parser("pause", help="暂停指定分类任务")
    pause_parser.add_argument("--category", required=True, help="分类名称")
    pause_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    pause_parser.set_defaults(func=execute_pause)

    # resume subcommand
    resume_parser = sub_subparsers.add_parser("resume", help="恢复指定分类任务")
    resume_parser.add_argument("--category", required=True, help="分类名称")
    resume_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    resume_parser.set_defaults(func=execute_resume)

def execute_list(args):
    params = {}
    if args.status:
        params["status"] = args.status
    if args.type:
        params["type"] = args.type
    if args.limit:
        params["limit"] = args.limit
    
    data = make_request("/tasks/", params=params, method="GET")
    output(data)

def execute_info(args):
    data = make_request(f"/tasks/{args.id}", method="GET")
    output(data)

def execute_status(args):
    data = make_request("/tasks/status", method="GET")
    output(data)

def execute_grouped(args):
    data = make_request("/tasks/grouped-status", method="GET")
    output(data)

def execute_create(args):
    payload = {}
    if args.payload_json:
        try:
            payload = json.loads(args.payload_json)
        except json.JSONDecodeError as e:
            output_error(f"解析 payload JSON 失败: {e}")
            return
    elif args.payload_file:
        try:
            with open(args.payload_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            output_error(f"读取 payload 文件失败: {e}")
            return

    data = {
        "type": args.type,
        "payload": payload
    }
    result = make_request("/tasks/", method="POST", json_data=data)
    output_success("任务创建成功", result)

def execute_cancel(args):
    result = make_request(f"/tasks/{args.id}/cancel", method="POST")
    output_success("任务取消成功", result)

def execute_retry(args):
    result = make_request(f"/tasks/{args.id}/retry", method="POST")
    output_success("任务重试成功", result)

def execute_retry_all_failed(args):
    params = {}
    if args.types:
        params["types"] = args.types.split(",")
    result = make_request("/tasks/retry-all-failed", method="POST", params=params)
    output_success("重试所有失败任务成功", result)

def execute_clear_failed(args):
    params = {}
    if args.types:
        params["types"] = args.types.split(",")
    result = make_request("/tasks/failed", method="DELETE", params=params)
    output_success("删除失败任务成功", result)

def execute_wait(args):
    env = load_env()
    base_url = env.get("TRAILSNAP_API_URL")
    token = env.get("TRAILSNAP_API_TOKEN")
    if not base_url or not token:
        output_error("API URL 和 Token 未配置，请先运行 'config' 命令。")
        sys.exit(1)
        
    url = f"{base_url.rstrip('/')}/tasks/{args.id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    formatter = get_formatter()
    
    while True:
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            task_data = data.get("data", data)
            status = task_data.get("status")
            processed = task_data.get("processed_items", 0)
            total = task_data.get("total_items", 0)
            
            if formatter.format == "json":
                pass
            else:
                sys.stdout.write(f"\r状态: {status} | 进度: {processed}/{total}")
                sys.stdout.flush()
                
            if status in ["COMPLETED", "FAILED", "CANCELLED"]:
                if formatter.format != "json":
                    print()
                output(task_data)
                if status == "FAILED":
                    sys.exit(1)
                break
                
            time.sleep(1)
        except Exception as e:
            if formatter.format != "json":
                print()
            output_error(f"等待任务失败: {e}")
            sys.exit(1)

def execute_pause(args):
    result = make_request(f"/tasks/categories/{args.category}/pause", method="POST")
    output_success("暂停任务成功", result)

def execute_resume(args):
    result = make_request(f"/tasks/categories/{args.category}/resume", method="POST")
    output_success("恢复任务成功", result)
