from utils import make_request
from output import output, output_error, set_formatter, OutputFormatter

def setup_parser(subparsers):
    parser = subparsers.add_parser("tags", help="管理和查询分类标签")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    list_parser = sub_subparsers.add_parser("list", help="查询分类标签")
    list_parser.add_argument("--skip", type=int, default=0, help="跳过 N 个记录")
    list_parser.add_argument("--limit", type=int, default=100, help="限制返回 N 个记录")
    list_parser.add_argument("--all", action="store_true", help="自动翻页获取所有结果")
    list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    list_parser.set_defaults(func=execute_list)

def execute_list(args):
    set_formatter(args.format)
    
    all_data = []
    current_skip = args.skip
    limit = args.limit if not args.all else max(100, args.limit)

    while True:
        data = make_request("/tags", {"skip": current_skip, "limit": limit})
        if not data:
            break
        all_data.extend(data)
        if not args.all or len(data) < limit:
            break
        current_skip += limit

    if all_data:
        tags = [{
            "id": tag["id"],
            "name": tag["tag_name"],
            "count": tag["count"]
        } for tag in all_data]
        output(tags)
    else:
        output_error("未查询到分类标签记录")
