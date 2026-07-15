from utils import make_request
from output import output, output_error, set_formatter, OutputFormatter
import sys

def setup_parser(subparsers):
    parser = subparsers.add_parser("toolbox", help="整理工具命令")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    # 1. duplicates (X-1)
    duplicates_parser = sub_subparsers.add_parser("duplicates", help="重复照片工具")
    duplicates_subparsers = duplicates_parser.add_subparsers(dest="action", help="可用操作")
    duplicates_subparsers.required = True

    duplicates_scan_parser = duplicates_subparsers.add_parser("scan", help="扫描重复照片")
    duplicates_scan_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    duplicates_scan_parser.set_defaults(func=execute_duplicates_scan)

    duplicates_list_parser = duplicates_subparsers.add_parser("list", help="列出重复照片")
    duplicates_list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    duplicates_list_parser.set_defaults(func=execute_duplicates_list)

    # 2. similar (X-2)
    similar_parser = sub_subparsers.add_parser("similar", help="相似照片工具")
    similar_subparsers = similar_parser.add_subparsers(dest="action", help="可用操作")
    similar_subparsers.required = True

    similar_scan_parser = similar_subparsers.add_parser("scan", help="扫描相似照片")
    similar_scan_parser.add_argument("--threshold", type=float, default=0.9, help="相似度阈值 (默认0.9)")
    similar_scan_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    similar_scan_parser.set_defaults(func=execute_similar_scan)

    similar_status_parser = similar_subparsers.add_parser("status", help="获取相似照片扫描状态")
    similar_status_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    similar_status_parser.set_defaults(func=execute_similar_status)

    similar_result_parser = similar_subparsers.add_parser("result", help="获取相似照片扫描结果")
    similar_result_parser.add_argument("--task-id", required=True, help="任务ID")
    similar_result_parser.add_argument("--skip", type=int, default=0, help="跳过 N 个组")
    similar_result_parser.add_argument("--limit", type=int, default=20, help="限制返回 N 个组")
    similar_result_parser.add_argument("--all", action="store_true", help="自动翻页获取所有结果")
    similar_result_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    similar_result_parser.set_defaults(func=execute_similar_result)

    similar_cancel_parser = similar_subparsers.add_parser("cancel", help="取消相似照片扫描任务")
    similar_cancel_parser.add_argument("--task-id", required=True, help="任务ID")
    similar_cancel_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    similar_cancel_parser.set_defaults(func=execute_similar_cancel)

    # 3. cleanup (X-3)
    cleanup_parser = sub_subparsers.add_parser("cleanup", help="清理建议工具")
    cleanup_subparsers = cleanup_parser.add_subparsers(dest="action", help="可用操作")
    cleanup_subparsers.required = True

    cleanup_list_parser = cleanup_subparsers.add_parser("list", help="列出建议清理的照片")
    cleanup_list_parser.add_argument("--skip", type=int, default=0, help="跳过 N 张照片")
    cleanup_list_parser.add_argument("--limit", type=int, default=50, help="限制返回 N 张照片")
    cleanup_list_parser.add_argument("--sort-by", type=str, choices=["asc", "desc"], default="asc", help="排序方式")
    cleanup_list_parser.add_argument("--all", action="store_true", help="自动翻页获取所有结果")
    cleanup_list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    cleanup_list_parser.set_defaults(func=execute_cleanup_list)

    # 4. organize (X-4)
    organize_parser = sub_subparsers.add_parser("organize", help="照片整理工具")
    organize_subparsers = organize_parser.add_subparsers(dest="action", help="可用操作")
    organize_subparsers.required = True

    organize_preview_parser = organize_subparsers.add_parser("preview-options", help="预览整理选项")
    organize_preview_parser.add_argument("--strategy", required=True, choices=["time", "category", "person", "location"], help="整理策略")
    organize_preview_parser.add_argument("--location-granularity", default="city", help="位置粒度 (针对 location 策略)")
    organize_preview_parser.add_argument("--location-format", default="flat", help="位置格式 (针对 location 策略)")
    organize_preview_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    organize_preview_parser.set_defaults(func=execute_organize_preview_options)

    organize_start_parser = organize_subparsers.add_parser("start", help="开始整理照片")
    organize_start_parser.add_argument("--target-root", required=True, help="目标根目录")
    organize_start_parser.add_argument("--strategy", required=True, choices=["time", "category", "person", "location"], help="整理策略")
    organize_start_parser.add_argument("--action", default="copy", choices=["move", "copy"], help="操作方式 (move 或 copy)")
    organize_start_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    organize_start_parser.set_defaults(func=execute_organize_start)

    organize_status_parser = organize_subparsers.add_parser("status", help="获取整理任务状态")
    organize_status_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    organize_status_parser.set_defaults(func=execute_organize_status)

    # 5. rename (X-5)
    rename_parser = sub_subparsers.add_parser("rename", help="批量重命名工具")
    rename_subparsers = rename_parser.add_subparsers(dest="action", help="可用操作")
    rename_subparsers.required = True

    rename_start_parser = rename_subparsers.add_parser("start", help="开始重命名")
    rename_start_parser.add_argument("--target-root", required=True, help="目标根目录")
    rename_start_parser.add_argument("--template", default="IMG_{date}_{time}", help="命名模板")
    rename_start_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    rename_start_parser.set_defaults(func=execute_rename_start)

    rename_status_parser = rename_subparsers.add_parser("status", help="获取重命名任务状态")
    rename_status_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    rename_status_parser.set_defaults(func=execute_rename_status)

    # 6. time-from-filename (X-6)
    time_parser = sub_subparsers.add_parser("time-from-filename", help="从文件名提取时间工具")
    time_subparsers = time_parser.add_subparsers(dest="action", help="可用操作")
    time_subparsers.required = True

    time_start_parser = time_subparsers.add_parser("start", help="开始提取时间")
    time_start_parser.add_argument("--target-root", required=True, help="目标根目录")
    time_start_parser.add_argument("--only-missing-metadata", action="store_true", help="仅处理缺失元数据的照片")
    time_start_parser.add_argument("--make", help="指定相机品牌")
    time_start_parser.add_argument("--model", help="指定相机型号")
    time_start_parser.add_argument("--time-mode", choices=["auto", "custom"], default="auto", help="时间模式")
    time_start_parser.add_argument("--custom-time", help="自定义时间 (ISO 格式)")
    time_start_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    time_start_parser.set_defaults(func=execute_time_from_filename_start)

    time_status_parser = time_subparsers.add_parser("status", help="获取时间提取任务状态")
    time_status_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    time_status_parser.set_defaults(func=execute_time_from_filename_status)

def execute_duplicates_scan(args):
    set_formatter(args.format)
    data = make_request("/toolbox/duplicate-photos/scan", method="POST", json_data={})
    output(data)

def execute_duplicates_list(args):
    set_formatter(args.format)
    data = make_request("/toolbox/duplicate-photos")
    if data:
        output(data)
    else:
        output_error("未找到重复照片")

def execute_similar_scan(args):
    set_formatter(args.format)
    # Backend expects query param threshold
    data = make_request("/toolbox/similar/tasks", method="POST", params={"threshold": args.threshold}, json_data={})
    output(data)

def execute_similar_status(args):
    set_formatter(args.format)
    data = make_request("/toolbox/similar/tasks/latest")
    if data:
        output(data)
    else:
        output_error("无进行中的相似照片扫描任务")

def execute_similar_result(args):
    set_formatter(args.format)
    all_data = []
    current_skip = args.skip
    limit = args.limit if not args.all else max(20, args.limit)

    while True:
        data = make_request(f"/toolbox/similar/tasks/{args.task_id}/result", params={"skip": current_skip, "limit": limit})
        if not data:
            break
        all_data.extend(data)
        if not args.all or len(data) < limit:
            break
        current_skip += limit

    if all_data:
        output(all_data)
    else:
        output_error("未查询到相似照片结果")

def execute_similar_cancel(args):
    set_formatter(args.format)
    data = make_request(f"/toolbox/similar/tasks/{args.task_id}", method="DELETE")
    output(data)

def execute_cleanup_list(args):
    set_formatter(args.format)
    all_data = []
    current_skip = args.skip
    limit = args.limit if not args.all else max(50, args.limit)

    while True:
        data = make_request("/toolbox/cleanup", params={"skip": current_skip, "limit": limit, "sort_by": args.sort_by})
        if not data:
            break
        all_data.extend(data)
        if not args.all or len(data) < limit:
            break
        current_skip += limit

    if all_data:
        output(all_data)
    else:
        output_error("未找到建议清理的照片")

def execute_organize_preview_options(args):
    set_formatter(args.format)
    payload = {
        "strategy": args.strategy,
        "location_granularity": args.location_granularity,
        "location_format": args.location_format
    }
    data = make_request("/toolbox/organize/preview-options", method="POST", json_data=payload)
    output(data)

def execute_organize_start(args):
    set_formatter(args.format)
    payload = {
        "target_root_path": args.target_root,
        "strategy": args.strategy,
        "action": args.action
    }
    data = make_request("/toolbox/organize/tasks", method="POST", json_data=payload)
    output(data)

def execute_organize_status(args):
    set_formatter(args.format)
    data = make_request("/toolbox/organize/tasks/latest")
    if data:
        output(data)
    else:
        output_error("无进行中的整理任务")

def execute_rename_start(args):
    set_formatter(args.format)
    payload = {
        "target_root_path": args.target_root,
        "template": args.template
    }
    data = make_request("/toolbox/rename/tasks", method="POST", json_data=payload)
    output(data)

def execute_rename_status(args):
    set_formatter(args.format)
    data = make_request("/toolbox/rename/tasks/latest")
    if data:
        output(data)
    else:
        output_error("无进行中的重命名任务")

def execute_time_from_filename_start(args):
    set_formatter(args.format)
    payload = {
        "target_root_path": args.target_root,
        "only_missing_metadata": args.only_missing_metadata,
        "time_mode": args.time_mode
    }
    if args.make:
        payload["make"] = args.make
    if args.model:
        payload["model"] = args.model
    if args.custom_time:
        payload["custom_time"] = args.custom_time
        
    data = make_request("/toolbox/time-from-filename/tasks", method="POST", json_data=payload)
    output(data)

def execute_time_from_filename_status(args):
    set_formatter(args.format)
    data = make_request("/toolbox/time-from-filename/tasks/latest")
    if data:
        output(data)
    else:
        output_error("无进行中的提取时间任务")
