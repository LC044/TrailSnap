from utils import make_request, load_env
from output import output, output_error, set_formatter, OutputFormatter
import sys

def setup_parser(subparsers):
    parser = subparsers.add_parser("albums", help="管理和查询相册")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    # list
    list_parser = sub_subparsers.add_parser("list", help="查询相册列表")
    list_parser.add_argument("--skip", type=int, default=0, help="跳过 N 张相册")
    list_parser.add_argument("--limit", type=int, default=100, help="限制返回 N 张相册")
    list_parser.add_argument("--all", action="store_true", help="自动翻页获取所有结果")
    list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    list_parser.set_defaults(func=execute_list)

    # create (W-1)
    create_parser = sub_subparsers.add_parser("create", help="创建相册")
    create_parser.add_argument("--name", required=True, help="相册名称")
    create_parser.add_argument("--type", required=True, choices=["normal", "smart"], help="相册类型")
    create_parser.add_argument("--description", help="相册描述")
    create_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    create_parser.set_defaults(func=execute_create)

    # info (W-2)
    info_parser = sub_subparsers.add_parser("info", help="查看相册详情")
    info_parser.add_argument("--id", required=True, help="相册ID")
    info_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    info_parser.set_defaults(func=execute_info)

    # update (W-3)
    update_parser = sub_subparsers.add_parser("update", help="更新相册")
    update_parser.add_argument("--id", required=True, help="相册ID")
    update_parser.add_argument("--name", help="新相册名称")
    update_parser.add_argument("--description", help="新相册描述")
    update_parser.add_argument("--type", choices=["normal", "smart"], help="新相册类型")
    update_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    update_parser.set_defaults(func=execute_update)

    # delete (W-4)
    delete_parser = sub_subparsers.add_parser("delete", help="删除相册")
    delete_parser.add_argument("--id", required=True, help="相册ID")
    delete_parser.add_argument("--yes", action="store_true", help="免确认删除")
    delete_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    delete_parser.set_defaults(func=execute_delete)

    # cover (W-8)
    cover_parser = sub_subparsers.add_parser("cover", help="设置相册封面")
    cover_parser.add_argument("--id", required=True, help="相册ID")
    cover_parser.add_argument("--photo-id", required=True, help="照片ID")
    cover_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    cover_parser.set_defaults(func=execute_cover)

    # photos
    photos_parser = sub_subparsers.add_parser("photos", help="相册内照片操作")
    photos_subparsers = photos_parser.add_subparsers(dest="action", help="可用操作")
    photos_subparsers.required = True

    # photos list (W-5)
    photos_list_parser = photos_subparsers.add_parser("list", help="列出相册内照片")
    photos_list_parser.add_argument("--id", required=True, help="相册ID")
    photos_list_parser.add_argument("--skip", type=int, default=0, help="跳过")
    photos_list_parser.add_argument("--limit", type=int, default=100, help="限制")
    photos_list_parser.add_argument("--all", action="store_true", help="获取全部")
    photos_list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    photos_list_parser.set_defaults(func=execute_photos_list)

    # photos add (W-6)
    photos_add_parser = photos_subparsers.add_parser("add", help="向相册添加照片")
    photos_add_parser.add_argument("--id", required=True, help="相册ID")
    photos_add_parser.add_argument("--photo-id", required=True, help="照片ID列表，逗号分隔")
    photos_add_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    photos_add_parser.set_defaults(func=execute_photos_add)

    # photos remove (W-7)
    photos_remove_parser = photos_subparsers.add_parser("remove", help="从相册移除照片")
    photos_remove_parser.add_argument("--id", required=True, help="相册ID")
    photos_remove_parser.add_argument("--photo-id", required=True, help="照片ID")
    photos_remove_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    photos_remove_parser.set_defaults(func=execute_photos_remove)

def execute_list(args):
    set_formatter(args.format)
    
    all_data = []
    current_skip = args.skip
    limit = args.limit if not args.all else max(100, args.limit)

    while True:
        data = make_request("/albums", {"skip": current_skip, "limit": limit})
        if not data:
            break
        all_data.extend(data)
        if not args.all or len(data) < limit:
            break
        current_skip += limit

    if all_data:
        albums = [{
            "id": album["id"],
            "name": album["name"],
            "count": album.get("num_photos", 0),
            "description": album.get("description", ""),
            "condition": album.get("condition", ""),
            "type": album.get("type", "")
        } for album in all_data]
        output(albums)
    else:
        output_error("未查询到相册记录")

def execute_create(args):
    set_formatter(args.format)
    payload = {
        "name": args.name,
        "type": args.type,
    }
    if args.description:
        payload["description"] = args.description
    
    data = make_request("/albums", method="POST", json_data=payload)
    output(data)

def execute_info(args):
    set_formatter(args.format)
    data = make_request(f"/albums/{args.id}")
    output(data)

def execute_update(args):
    set_formatter(args.format)
    payload = {}
    if args.name:
        payload["name"] = args.name
    if args.description:
        payload["description"] = args.description
    if args.type:
        payload["type"] = args.type
        
    if not payload:
        output_error("未提供任何更新字段")
        return
        
    data = make_request(f"/albums/{args.id}", method="PUT", json_data=payload)
    output(data)

def execute_delete(args):
    set_formatter(args.format)
    if not args.yes:
        confirm = input(f"确定要删除相册 {args.id} 吗？(y/N): ")
        if confirm.lower() != 'y':
            sys.exit(0)
            
    data = make_request(f"/albums/{args.id}", method="DELETE")
    output(data)

def execute_cover(args):
    set_formatter(args.format)
    payload = {
        "cover_id": args.photo_id
    }
    data = make_request(f"/albums/{args.id}/cover", method="PUT", json_data=payload)
    output(data)

def execute_photos_list(args):
    set_formatter(args.format)
    
    all_data = []
    current_skip = args.skip
    limit = args.limit if not args.all else max(100, args.limit)

    while True:
        data = make_request(f"/albums/{args.id}/photos", {"skip": current_skip, "limit": limit})
        if not data:
            break
        all_data.extend(data)
        if not args.all or len(data) < limit:
            break
        current_skip += limit

    if all_data:
        output(all_data)
    else:
        output_error("该相册未查询到照片")

def execute_photos_add(args):
    set_formatter(args.format)
    photo_ids = [p.strip() for p in args.photo_id.split(',')]
    payload = photo_ids
    
    data = make_request(f"/albums/{args.id}/photos", method="POST", json_data=payload)
    output(data)

def execute_photos_remove(args):
    set_formatter(args.format)
    data = make_request(f"/albums/{args.id}/photos/{args.photo_id}", method="DELETE")
    output(data)

