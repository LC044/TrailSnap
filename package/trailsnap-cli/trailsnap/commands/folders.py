from utils import make_request
from output import output, output_error, set_formatter, OutputFormatter

def setup_parser(subparsers):
    parser = subparsers.add_parser("folders", help="管理和查询挂载的存储目录")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    list_parser = sub_subparsers.add_parser("list", help="查询挂载的存储目录")
    list_parser.add_argument("--all", action="store_true", help="自动翻页获取所有结果 (目录查询不支持分页，忽略此参数)")
    list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    list_parser.set_defaults(func=execute_list)

def execute_list(args):
    set_formatter(args.format)
    data = make_request("/settings/directories")
    if data is not None:
        output(data)
    else:
        output_error("未查询到存储目录信息")
