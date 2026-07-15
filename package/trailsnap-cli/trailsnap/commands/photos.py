from utils import make_request, load_env
from output import output, output_success, output_error, set_formatter, OutputFormatter

def setup_parser(subparsers):
    parser = subparsers.add_parser("photos", help="管理和查询照片")
    sub_subparsers = parser.add_subparsers(dest="subcommand", help="可用操作")
    sub_subparsers.required = True

    # list subcommand
    list_parser = sub_subparsers.add_parser("list", help="查询照片列表")
    list_parser.add_argument("--skip", type=int, default=0, help="跳过 N 张照片")
    list_parser.add_argument("--limit", type=int, default=10, help="限制返回 N 张照片")
    list_parser.add_argument("--all", action="store_true", help="自动翻页获取所有结果")
    list_parser.add_argument("--order_by", type=str, default="memory_score", help="排序字段，默认按值得回忆评分排序，可选值：quality_score,memory_score,photo_time")
    list_parser.add_argument("--image-type", help="按图片类型过滤照片，多个类型用逗号分隔，可选值：Camera,Screenshot,Other")
    list_parser.add_argument("--start-date", help="按开始日期过滤照片，格式为 YYYY-MM-DD")
    list_parser.add_argument("--end-date", help="按结束日期过滤照片，格式为 YYYY-MM-DD")
    list_parser.add_argument("--start-time", help="可选开始时分秒，格式为 HH:MM:SS，需配合 --start-date 使用")
    list_parser.add_argument("--end-time", help="可选结束时分秒，格式为 HH:MM:SS，需配合 --end-date 使用")
    list_parser.add_argument("--album-id", help="按相册 ID 过滤，多个 ID 用逗号分隔")
    list_parser.add_argument("--people-id", help="按人物 ID 过滤，多个 ID 用逗号分隔")
    list_parser.add_argument("--tag-id", help="按标签 ID 过滤，多个 ID 用逗号分隔")
    list_parser.add_argument("--city", help="按城市过滤，多个城市用逗号分隔")
    list_parser.add_argument("--province", help="按省份过滤，多个省份用逗号分隔")
    list_parser.add_argument("--scene", help="按景区过滤，多个景区用逗号分隔")
    list_parser.add_argument("--make", help="按相机品牌过滤，多个品牌用逗号分隔")
    list_parser.add_argument("--model", help="按相机型号过滤，多个型号用逗号分隔")
    list_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    list_parser.set_defaults(func=execute_list)

    # info subcommand
    info_parser = sub_subparsers.add_parser("info", help="获取单张照片信息")
    info_parser.add_argument("--photo-id", required=True, help="照片ID")
    info_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    info_parser.set_defaults(func=execute_info)

    # delete subcommand
    delete_parser = sub_subparsers.add_parser("delete", help="删除照片")
    delete_parser.add_argument("--photo-id", required=True, help="照片ID")
    delete_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    delete_parser.set_defaults(func=execute_delete)

    # update (W-9)
    update_parser = sub_subparsers.add_parser("update", help="更新照片")
    update_parser.add_argument("--id", required=True, help="照片ID")
    update_parser.add_argument("--photo-time", help="照片拍摄时间")
    update_parser.add_argument("--description", help="照片描述")
    update_parser.add_argument("--filename", help="照片文件名")
    update_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    update_parser.set_defaults(func=execute_update)

    # location-batch (W-10)
    location_batch_parser = sub_subparsers.add_parser("location-batch", help="批量更新照片位置")
    location_batch_parser.add_argument("--csv", required=True, help="CSV文件路径")
    location_batch_parser.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    location_batch_parser.set_defaults(func=execute_location_batch)

    # trash (W-11)
    trash_parser = sub_subparsers.add_parser("trash", help="回收站操作")
    trash_subparsers = trash_parser.add_subparsers(dest="action", help="可用操作")
    trash_subparsers.required = True

    trash_list = trash_subparsers.add_parser("list", help="回收站列表")
    trash_list.add_argument("--skip", type=int, default=0, help="跳过")
    trash_list.add_argument("--limit", type=int, default=100, help="限制")
    trash_list.add_argument("--all", action="store_true", help="获取全部")
    trash_list.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    trash_list.set_defaults(func=execute_trash_list)

    trash_restore = trash_subparsers.add_parser("restore", help="恢复照片")
    trash_restore.add_argument("--ids", required=True, help="照片ID列表，逗号分隔")
    trash_restore.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    trash_restore.set_defaults(func=execute_trash_restore)

    trash_purge = trash_subparsers.add_parser("purge", help="永久删除")
    trash_purge.add_argument("--ids", required=True, help="照片ID列表，逗号分隔")
    trash_purge.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    trash_purge.set_defaults(func=execute_trash_purge)

    # batch (W-12, W-13)
    batch_parser = sub_subparsers.add_parser("batch", help="批量操作")
    batch_subparsers = batch_parser.add_subparsers(dest="action", help="可用操作")
    batch_subparsers.required = True

    batch_delete = batch_subparsers.add_parser("delete", help="批量删除照片")
    batch_delete.add_argument("--ids", required=True, help="照片ID列表，逗号分隔")
    batch_delete.add_argument("--delete-file", action="store_true", help="是否同时删除物理文件")
    batch_delete.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    batch_delete.set_defaults(func=execute_batch_delete)

    batch_transfer = batch_subparsers.add_parser("transfer", help="批量转移到相册")
    batch_transfer.add_argument("--ids", required=True, help="照片ID列表，逗号分隔")
    batch_transfer.add_argument("--target-album", required=True, help="目标相册ID")
    batch_transfer.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    batch_transfer.set_defaults(func=execute_batch_transfer)

    # tags (W-14)
    tags_parser = sub_subparsers.add_parser("tags", help="照片标签操作")
    tags_subparsers = tags_parser.add_subparsers(dest="action", help="可用操作")
    tags_subparsers.required = True

    tags_list = tags_subparsers.add_parser("list", help="照片标签列表")
    tags_list.add_argument("--photo-id", required=True, help="照片ID")
    tags_list.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    tags_list.set_defaults(func=execute_tags_list)

    tags_add = tags_subparsers.add_parser("add", help="添加照片标签")
    tags_add.add_argument("--photo-id", required=True, help="照片ID")
    tags_add.add_argument("--tag-id", required=True, help="标签ID")
    tags_add.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    tags_add.set_defaults(func=execute_tags_add)

    tags_remove = tags_subparsers.add_parser("remove", help="移除照片标签")
    tags_remove.add_argument("--photo-id", required=True, help="照片ID")
    tags_remove.add_argument("--tag-id", required=True, help="标签ID")
    tags_remove.add_argument("--format", type=str, default="json", choices=OutputFormatter.SUPPORTED_FORMATS, help="输出格式")
    tags_remove.set_defaults(func=execute_tags_remove)

def execute_list(args):
    set_formatter(args.format)
    start_dt = None
    if args.start_date:
        start_dt = f"{args.start_date} {args.start_time}" if args.start_time else f"{args.start_date} 00:00:00"
    end_dt = None
    if args.end_date:
        end_dt = f"{args.end_date} {args.end_time}" if args.end_time else f"{args.end_date} 23:59:59"

    base_params = {
        "start_time": start_dt,
        "end_time": end_dt,
        "image_types": args.image_type.split(",") if args.image_type else [],
        "scenes": args.scene.split(",") if args.scene else [],
        "album_ids": args.album_id.split(",") if args.album_id else [],
        "cities": args.city.split(",") if args.city else [],
        "provinces": args.province.split(",") if args.province else [],
        "makes": args.make.split(",") if args.make else [],
        "models": args.model.split(",") if args.model else [],
        "face_ids": args.people_id.split(",") if args.people_id else [],
        "tag_ids": args.tag_id.split(",") if args.tag_id else [],
        "order_by": args.order_by
    }

    env = load_env()
    base_url = env.get("TRAILSNAP_API_URL", "")

    all_data = []
    current_skip = args.skip
    limit = args.limit if not args.all else max(100, args.limit)

    while True:
        params = base_params.copy()
        params.update({"skip": current_skip, "limit": limit})
        data = make_request("/photos/detail", params)
        if not data:
            break
        all_data.extend(data)
        if not args.all or len(data) < limit:
            break
        current_skip += limit

    if all_data:
        photos = []
        for photo in all_data:
            metadata = photo.get("metadata_info", {})
            if not metadata:
                metadata = {}
            image_description = photo.get("image_description", {})
            if not image_description:
                image_description = {}
            photos.append({
                "id": photo["id"],
                "url": f"{base_url}/medias/{photo['id']}/file",
                "filename": photo["filename"],
                "file_type": photo["file_type"],
                "photo_time": photo["photo_time"],
                "address": metadata.get("address", ""),
                "description": {
                    "description": image_description.get("description", ""),
                    "tags": image_description.get("tags", []),
                    "memory_score": image_description.get("memory_score", 0),
                    "quality_score": image_description.get("quality_score", 0),
                    "narrative": image_description.get("narrative", "")
                }
            })
        output(photos)
    else:
        output_error("没有查询到照片列表")

def execute_info(args):
    set_formatter(args.format)
    data = make_request("/metadata", {"photo_id": args.photo_id})
    description_data = make_request(f"/photos/{args.photo_id}/description")
    if not description_data:
        description_data = {}
    if data:
        info = {
            # "file_path": data.get("file_path"),
            "address": data.get("address"),
            "albums": data.get("albums", []),
            "tags": data.get("tags", []),
            "faces_identities": data.get("faces_identities", []),
            "description": description_data
        }
        output(info)
    else:
        output_error("未查询到照片信息")

def execute_delete(args):
    set_formatter(args.format)
    data = make_request(f"/photos/{args.photo_id}", method="DELETE")
    if data:
        output_success(f"照片 {args.photo_id} 删除成功")
    else:
        output_error("照片删除失败或不存在")

def execute_update(args):
    set_formatter(args.format)
    payload = {}
    if args.photo_time:
        payload["photo_time"] = args.photo_time
    if args.description:
        payload["description"] = args.description
    if args.filename:
        payload["filename"] = args.filename
        
    if not payload:
        output_error("未提供任何更新字段")
        return
        
    data = make_request(f"/photos/{args.id}", method="PUT", json_data=payload)
    output(data)

def execute_location_batch(args):
    set_formatter(args.format)
    import os
    import csv
    if not os.path.exists(args.csv):
        output_error(f"CSV文件不存在: {args.csv}")
        return
        
    requests_to_make = []
    with open(args.csv, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or row[0].startswith('#') or row[0] == 'photo_id':
                continue
            if len(row) < 3:
                continue
            photo_id = row[0].strip()
            lat = float(row[1].strip())
            lng = float(row[2].strip())
            city = row[3].strip() if len(row) > 3 else None
            province = row[4].strip() if len(row) > 4 else None
            country = row[5].strip() if len(row) > 5 else None
            district = row[6].strip() if len(row) > 6 else None
            address = row[7].strip() if len(row) > 7 else None
            
            payload = {
                "photo_ids": [photo_id],
                "latitude": lat,
                "longitude": lng,
            }
            if city: payload["city"] = city
            if province: payload["province"] = province
            if country: payload["country"] = country
            if district: payload["district"] = district
            if address: payload["formatted_address"] = address
            requests_to_make.append(payload)

    success_count = 0
    for req in requests_to_make:
        data = make_request("/metadata/batch-location", method="POST", json_data=req)
        if data and data.get("count", 0) > 0:
            success_count += 1
            
    output({"success_count": success_count, "total_requests": len(requests_to_make)})

def execute_trash_list(args):
    set_formatter(args.format)
    all_data = []
    current_skip = args.skip
    limit = args.limit if not args.all else max(100, args.limit)

    while True:
        data = make_request("/photos/recycle-bin", {"skip": current_skip, "limit": limit})
        if not data:
            break
        all_data.extend(data)
        if not args.all or len(data) < limit:
            break
        current_skip += limit

    if all_data:
        output(all_data)
    else:
        output_error("回收站为空")

def execute_trash_restore(args):
    set_formatter(args.format)
    ids = [p.strip() for p in args.ids.split(',')]
    data = make_request("/photos/recycle-bin/restore", method="POST", json_data=ids)
    output(data)

def execute_trash_purge(args):
    set_formatter(args.format)
    ids = [p.strip() for p in args.ids.split(',')]
    # DELETE method with JSON payload might need to be handled, or pass as params
    # /photos/recycle-bin/permanent
    data = make_request("/photos/recycle-bin/permanent", method="DELETE", json_data=ids)
    output(data)

def execute_batch_delete(args):
    set_formatter(args.format)
    ids = [p.strip() for p in args.ids.split(',')]
    payload = {
        "photo_ids": ids,
        "delete_file": args.delete_file
    }
    data = make_request("/photos/batch", method="DELETE", json_data=payload)
    output(data)

def execute_batch_transfer(args):
    set_formatter(args.format)
    ids = [p.strip() for p in args.ids.split(',')]
    payload = {
        "photo_ids": ids,
        "target_album_id": args.target_album
    }
    data = make_request("/photos/batch/transfer", method="POST", json_data=payload)
    output(data)

def execute_tags_list(args):
    set_formatter(args.format)
    data = make_request(f"/photos/{args.photo_id}/tags")
    output(data)

def execute_tags_add(args):
    set_formatter(args.format)
    data = make_request(f"/photos/{args.photo_id}/tags", method="POST", json_data={"tag_id": args.tag_id})
    output(data)

def execute_tags_remove(args):
    set_formatter(args.format)
    data = make_request(f"/photos/{args.photo_id}/tags/{args.tag_id}", method="DELETE")
    output(data)

