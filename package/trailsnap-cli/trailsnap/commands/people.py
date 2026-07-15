from utils import make_request
from output import output, output_error, set_formatter, OutputFormatter

def setup_parser(subparsers):
    parser = subparsers.add_parser("people", help="管理和查询人物（面部识别）")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    list_parser = sub_subparsers.add_parser("list", help="查询人物列表")
    list_parser.add_argument("--skip", type=int, default=0, help="跳过 N 个记录")
    list_parser.add_argument("--limit", type=int, default=100, help="返回的记录数，默认 100")
    list_parser.add_argument("--all", action="store_true", help="自动翻页获取所有结果")
    list_parser.add_argument("--types", type=str, default="named", help="查询类型，默认 named, 可选值：named,unnamed,hidden 中的一个或多个,逗号分隔")
    list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    list_parser.set_defaults(func=execute_list)

    # create (W-15)
    create_parser = sub_subparsers.add_parser("create", help="创建人物")
    create_parser.add_argument("--name", required=True, help="人物名称")
    create_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    create_parser.set_defaults(func=execute_create)

    # info (W-15)
    info_parser = sub_subparsers.add_parser("info", help="查看人物详情")
    info_parser.add_argument("--id", required=True, help="人物ID")
    info_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    info_parser.set_defaults(func=execute_info)

    # update (W-15)
    update_parser = sub_subparsers.add_parser("update", help="更新人物")
    update_parser.add_argument("--id", required=True, help="人物ID")
    update_parser.add_argument("--name", help="新人物名称")
    update_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    update_parser.set_defaults(func=execute_update)

    # delete (W-15)
    delete_parser = sub_subparsers.add_parser("delete", help="删除人物")
    delete_parser.add_argument("--id", required=True, help="人物ID")
    delete_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    delete_parser.set_defaults(func=execute_delete)

    # merge (W-16)
    merge_parser = sub_subparsers.add_parser("merge", help="合并人物")
    merge_parser.add_argument("--target", required=True, help="目标人物ID")
    merge_parser.add_argument("--sources", required=True, help="源人物ID列表，逗号分隔")
    merge_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    merge_parser.set_defaults(func=execute_merge)

    # cover (W-17)
    cover_parser = sub_subparsers.add_parser("cover", help="设置人物封面")
    cover_parser.add_argument("--id", required=True, help="人物ID")
    cover_parser.add_argument("--photo-id", required=True, help="照片ID")
    cover_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    cover_parser.set_defaults(func=execute_cover)

    # rescan (W-18)
    rescan_parser = sub_subparsers.add_parser("rescan", help="重新扫描人物")
    rescan_parser.add_argument("--id", required=True, help="人物ID")
    rescan_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    rescan_parser.set_defaults(func=execute_rescan)

    # photos (W-19)
    photos_parser = sub_subparsers.add_parser("photos", help="人物照片操作")
    photos_subparsers = photos_parser.add_subparsers(dest="action", help="可用操作")
    photos_subparsers.required = True

    photos_add = photos_subparsers.add_parser("add", help="向人物添加照片")
    photos_add.add_argument("--id", required=True, help="人物ID")
    photos_add.add_argument("--photo-id", required=True, help="照片ID列表，逗号分隔")
    photos_add.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    photos_add.set_defaults(func=execute_photos_add)

    photos_remove = photos_subparsers.add_parser("remove", help="从人物移除照片")
    photos_remove.add_argument("--id", required=True, help="人物ID")
    photos_remove.add_argument("--photo-id", required=True, help="照片ID列表，逗号分隔")
    photos_remove.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    photos_remove.set_defaults(func=execute_photos_remove)

def execute_list(args):
    set_formatter(args.format)
    valid_types = {"named", "unnamed", "hidden"}
    if not set(args.types.split(",")) <= valid_types:
        output_error("types参数值必须为 named,unnamed,hidden 中的一个或多个")
        return

    args.types = args.types.split(",")
    
    all_data = []
    current_skip = args.skip
    limit = args.limit if not args.all else max(100, args.limit)

    while True:
        data = make_request("/faces/identities", {"skip": current_skip, "limit": limit, "types": args.types})
        if not data:
            break
        all_data.extend(data)
        if not args.all or len(data) < limit:
            break
        current_skip += limit

    if all_data:
        identities = [{
            "id": identity["id"],
            "name": identity["identity_name"],
            "tags": identity["tags"],
            "description": identity["description"],
            "face_count": identity["face_count"]
        } for identity in all_data]
        output(identities)
    else:
        output_error("未查询到人物记录")

def execute_create(args):
    set_formatter(args.format)
    payload = {"identity_name": args.name}
    data = make_request("/faces/identities", method="POST", json_data=payload)
    output(data)

def execute_info(args):
    set_formatter(args.format)
    data = make_request(f"/faces/identities/{args.id}")
    output(data)

def execute_update(args):
    set_formatter(args.format)
    payload = {}
    if args.name:
        payload["identity_name"] = args.name
    
    if not payload:
        output_error("未提供任何更新字段")
        return
        
    data = make_request(f"/faces/identities/{args.id}", method="PUT", json_data=payload)
    output(data)

def execute_delete(args):
    set_formatter(args.format)
    data = make_request(f"/faces/identities/{args.id}", method="DELETE")
    output(data)

def execute_merge(args):
    set_formatter(args.format)
    sources = [s.strip() for s in args.sources.split(',')]
    payload = {
        "target_identity_id": args.target,
        "source_identity_ids": sources
    }
    data = make_request("/faces/identities/merge", method="POST", json_data=payload)
    output(data)

def execute_cover(args):
    set_formatter(args.format)
    payload = {"photo_id": args.photo_id}
    data = make_request(f"/faces/identities/{args.id}/cover", method="PUT", json_data=payload)
    output(data)

def execute_rescan(args):
    set_formatter(args.format)
    data = make_request(f"/faces/identities/{args.id}/rescan", method="POST")
    output(data)

def execute_photos_add(args):
    set_formatter(args.format)
    photo_ids = [p.strip() for p in args.photo_id.split(',')]
    payload = {"photo_ids": photo_ids}
    data = make_request(f"/faces/identities/{args.id}/add-photos", method="POST", json_data=payload)
    output(data)

def execute_photos_remove(args):
    set_formatter(args.format)
    photo_ids = [p.strip() for p in args.photo_id.split(',')]
    payload = {"photo_ids": photo_ids}
    data = make_request(f"/faces/identities/{args.id}/remove-photos", method="POST", json_data=payload)
    output(data)

