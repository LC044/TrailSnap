from utils import make_request
from output import output, output_error, set_formatter, OutputFormatter

def setup_parser(subparsers):
    parser = subparsers.add_parser("locations", help="管理和查询位置")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    list_parser = sub_subparsers.add_parser("list", help="查询位置分布，不含时间信息（地点名，照片数量）")
    list_parser.add_argument("--level", choices=["city", "province", "district", "scene"], default="city", help="分组级别，默认 city, 可选值：city,province,district,scene（5A景区） 中的一个")
    list_parser.add_argument("--skip", type=int, default=0, help="跳过 N 个位置")
    list_parser.add_argument("--limit", type=int, default=100, help="限制返回 N 个位置")
    list_parser.add_argument("--all", action="store_true", help="自动翻页获取所有结果")
    list_parser.add_argument("--start-date", help="可选，开始日期，格式 YYYY-MM-DD")
    list_parser.add_argument("--end-date", help="可选，结束日期，格式 YYYY-MM-DD")
    list_parser.add_argument("--start-time", help="可选开始时分秒，格式 HH:MM:SS，配合 --start-date 使用")
    list_parser.add_argument("--end-time", help="可选结束时分秒，格式 HH:MM:SS，配合 --end-date 使用")
    list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    list_parser.set_defaults(func=execute_list)

    timeline_parser = sub_subparsers.add_parser("timeline", help="查询足迹时间轴列表，按时间和地点分组（开始日期，结束日期，地点名，照片数量）")
    timeline_parser.add_argument("--level", choices=["city", "province", "district", "scene"], default="city", help="分组级别，默认 city, 可选值：city,province,district,scene（5A景区） 中的一个")
    timeline_parser.add_argument("--skip", type=int, default=0, help="跳过 N 个位置")
    timeline_parser.add_argument("--limit", type=int, default=100, help="限制返回 N 个位置")
    timeline_parser.add_argument("--all", action="store_true", help="自动翻页获取所有结果")
    timeline_parser.add_argument("--start-date", help="可选，开始日期，格式 YYYY-MM-DD")
    timeline_parser.add_argument("--end-date", help="可选，结束日期，格式 YYYY-MM-DD")
    timeline_parser.add_argument("--start-time", help="可选开始时分秒，格式 HH:MM:SS，配合 --start-date 使用")
    timeline_parser.add_argument("--end-time", help="可选结束时分秒，格式 HH:MM:SS，配合 --end-date 使用")
    timeline_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    timeline_parser.set_defaults(func=execute_timeline)

    # scenes (W-20)
    scenes_parser = sub_subparsers.add_parser("scenes", help="景区操作")
    scenes_subparsers = scenes_parser.add_subparsers(dest="action", help="可用操作")
    scenes_subparsers.required = True

    scenes_list = scenes_subparsers.add_parser("list", help="景区列表")
    scenes_list.add_argument("--skip", type=int, default=0, help="跳过")
    scenes_list.add_argument("--limit", type=int, default=100, help="限制")
    scenes_list.add_argument("--all", action="store_true", help="获取全部")
    scenes_list.add_argument("--start-date", help="开始日期")
    scenes_list.add_argument("--end-date", help="结束日期")
    scenes_list.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    scenes_list.set_defaults(func=execute_scenes_list)

    scenes_create = scenes_subparsers.add_parser("create", help="创建景区")
    scenes_create.add_argument("--name", required=True, help="景区名称")
    scenes_create.add_argument("--level", help="景区级别，如5A")
    scenes_create.add_argument("--province", help="省份")
    scenes_create.add_argument("--city", help="城市")
    scenes_create.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    scenes_create.set_defaults(func=execute_scenes_create)

    scenes_info = scenes_subparsers.add_parser("info", help="查看景区详情")
    scenes_info.add_argument("--id", required=True, help="景区ID")
    scenes_info.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    scenes_info.set_defaults(func=execute_scenes_info)

    scenes_update = scenes_subparsers.add_parser("update", help="更新景区")
    scenes_update.add_argument("--id", required=True, help="景区ID")
    scenes_update.add_argument("--name", help="景区名称")
    scenes_update.add_argument("--level", help="景区级别")
    scenes_update.add_argument("--province", help="省份")
    scenes_update.add_argument("--city", help="城市")
    scenes_update.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    scenes_update.set_defaults(func=execute_scenes_update)

    scenes_delete = scenes_subparsers.add_parser("delete", help="删除景区")
    scenes_delete.add_argument("--id", required=True, help="景区ID")
    scenes_delete.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    scenes_delete.set_defaults(func=execute_scenes_delete)

def execute_timeline(args):
    set_formatter(args.format)
    start_dt = None
    if args.start_date:
        start_dt = f"{args.start_date} {args.start_time}" if args.start_time else f"{args.start_date} 00:00:00"
    end_dt = None
    if args.end_date:
        end_dt = f"{args.end_date} {args.end_time}" if args.end_time else f"{args.end_date} 23:59:59"

    all_data = []
    current_skip = args.skip
    limit = args.limit if not args.all else max(100, args.limit)

    while True:
        data = make_request("/locations/timeline", {"start_date": start_dt, "end_date": end_dt, "skip": current_skip, "limit": limit, "level": args.level})
        if not data or not data.get("nodes"):
            break
        nodes = data["nodes"]
        all_data.extend(nodes)
        if not args.all or len(nodes) < limit:
            break
        current_skip += limit

    if all_data:
        timelines = [{
            "startDate": timeline["startDate"],
            "endDate": timeline["endDate"],
            "locationName": timeline["locationName"],
            "count": timeline["photoCount"]
        } for timeline in all_data]
        output(timelines)
    else:
        output_error("未查询到位置足迹时间轴数据")

def execute_list(args):
    set_formatter(args.format)
    start_dt = None
    if args.start_date:
        start_dt = f"{args.start_date} {args.start_time}" if args.start_time else f"{args.start_date} 00:00:00"
    end_dt = None
    if args.end_date:
        end_dt = f"{args.end_date} {args.end_time}" if args.end_time else f"{args.end_date} 23:59:59"

    all_data = []
    current_skip = args.skip
    limit = args.limit if not args.all else max(100, args.limit)

    while True:
        data = make_request("/locations", {"level": args.level, "skip": current_skip, "limit": limit, "start_date": start_dt, "end_date": end_dt})
        if not data:
            break
        all_data.extend(data)
        if not args.all or len(data) < limit:
            break
        current_skip += limit

    if all_data:
        locations = [{
            "name": location["name"],
            "count": location["count"]
        } for location in all_data]
        output(locations)
    else:
        output_error("未查询到位置记录")

def execute_scenes_list(args):
    set_formatter(args.format)
    all_data = []
    current_skip = args.skip
    limit = args.limit if not args.all else max(100, args.limit)

    while True:
        params = {"skip": current_skip, "limit": limit}
        if args.start_date: params["start_date"] = args.start_date
        if args.end_date: params["end_date"] = args.end_date
        data = make_request("/locations/scenes/list", params)
        if not data:
            break
        # data might be a BaseResponse unwrapped in make_request, so data is the list
        if isinstance(data, dict) and "data" in data:
            nodes = data["data"]
        else:
            nodes = data
        all_data.extend(nodes)
        if not args.all or len(nodes) < limit:
            break
        current_skip += limit

    if all_data:
        output(all_data)
    else:
        output_error("未查询到景区列表")

def execute_scenes_create(args):
    set_formatter(args.format)
    payload = {"name": args.name}
    if args.level: payload["level"] = args.level
    if args.province: payload["province"] = args.province
    if args.city: payload["city"] = args.city
    
    data = make_request("/locations/scenes", method="POST", json_data=payload)
    output(data)

def execute_scenes_info(args):
    set_formatter(args.format)
    data = make_request(f"/locations/scenes/{args.id}")
    output(data)

def execute_scenes_update(args):
    set_formatter(args.format)
    payload = {}
    if args.name: payload["name"] = args.name
    if args.level: payload["level"] = args.level
    if args.province: payload["province"] = args.province
    if args.city: payload["city"] = args.city
    
    if not payload:
        output_error("未提供任何更新字段")
        return
        
    data = make_request(f"/locations/scenes/{args.id}", method="PUT", json_data=payload)
    output(data)

def execute_scenes_delete(args):
    set_formatter(args.format)
    data = make_request(f"/locations/scenes/{args.id}", method="DELETE")
    output(data)

