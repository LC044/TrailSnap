import os
import re
import json
import logging


def extract_text(json_path):
    """
    从OCR保存的JSON文件中提取所有识别文本
    """
    texts = []
    polys = []
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        rec_texts = data.get("rec_texts", [])
        rec_polys = data.get("rec_polys", [])

        # 同时遍历，只保留非空文本及其对应的 poly
        for txt, poly in zip(rec_texts, rec_polys):
            stripped = txt.strip()
            if stripped:  # 非空才保留
                texts.append(stripped)
                polys.append(poly)

    except Exception as e:
        print(f"读取JSON文件失败: {e}")
    return texts, polys


def _fix_ocr_text(s):
    return s.replace('I', '1').replace('l', '1').replace('O', '0').replace('o', '0')


def normalize_ticket_text(text):
    text=text.translate(str.maketrans({'車':'车','號':'号','東':'东','溫':'温','鄉':'乡','臺':'台','廣':'广',
        '門':'门','樂':'乐','長':'长','慶':'庆','雲':'云','龍':'龙','寧':'宁','濟':'济','蘭':'兰','陽':'阳',
        '烏':'乌','張':'张','壽':'寿','貴':'贵','黃':'黄','興':'兴'})).strip()
    text=re.sub(r'(?<!\d)(\d{1,2}[-/]\d{2})(\d{2}[:：]\d{2})',r'\1 \2',text)
    text=re.sub(r'(?<=[\u4e00-\u9fa5])[Il|丨]\s*([GDCKTZSNLYA]\d{1,4})',r'\1',text)
    text=re.sub(r'(?<![A-Za-z0-9])([gdcktzsnlya])(?=\d{1,4}(?!\d))',lambda m:m[1].upper(),text)
    text=re.sub(r'(?<![A-Za-z0-9])([GDCKTZS])i(?=\d{1,3}(?!\d))',r'\g<1>1',text)
    # A paper ticket's service can be glued to a noisy serial/station block.
    if '站' in text and re.search(r'[\u4e00-\u9fa5]',text):
        text=re.sub(r'(?<=\d)([GDCKTZS]\d{1,4})$',r' \1',text)
    return re.sub(r'^[0O①②③④⑤⑥⑦⑧⑨]\s*([GDCKTZSNLYA]\d{1,4})$',r'\1',text)


def candidate_train_codes(texts):
    texts=[_fix_ocr_text(normalize_ticket_text(t)) for t in texts]
    modern={m[1] for t in texts for m in re.finditer(r'(?<![A-Za-z0-9])([GDCKTZS]\d{1,4})(?![A-Za-z0-9])',t)}
    if modern:return modern
    return {m[1] for t in texts if (m:=re.fullmatch(r'([NLYA]\d{1,4})\s*次?',t))}


_STATION_INTERFERENCE = {
    "去看看", "时刻表", "其他问题", "年月日",
    "上铺", "中铺", "下铺", "复兴号", "和谐号", "智能动车", "乘车人", "身份证", "二等座",
    "限乘", "当日", "当次",
    "报销", "使用",
    "改签", "退票", "变更", "变更到", "变更到站",
    "复制", "订单", "订单号", "已支付", "取票号",
    "学生票", "非现金", "线上购买", "交回", "须交回",
    "餐饮", "特产", "订酒店", "租车", "约车",
     "经停", "经停站", "检票口", "检票", "前往",
     "购票成功", "抢票成功", "成功", "以车","已出","已进",
     "车次", "座席", "今天", "明天", "昨天", "过去", "未来", "成人票", "电子乘车码", "同车换座",
     "一等座", "商务座", "硬座", "无座", "软座", "硬卧", "软卧", "误售", "广告", "传媒", "中国铁", "全价", "网折"
}


def _normalize_station_name(name: str) -> str:
    return (name or "").strip()


_VALID_STATION_NAMES = set()
_STATION_PINYIN = None


def _station_from_printed_pinyin(name, poly, texts, polys):
    """Corroborate a single damaged Chinese glyph with its printed romanization."""
    global _STATION_PINYIN
    if name in _get_valid_station_names() or len(name)<2 or len(poly)<4:
        return name
    if _STATION_PINYIN is None:
        try:
            path=os.path.join(os.path.dirname(__file__),'..','data','railway_station_pinyin.json')
            with open(path,encoding='utf-8') as stream:
                _STATION_PINYIN=json.load(stream)['stations']
        except (OSError,ValueError,KeyError):
            _STATION_PINYIN={}
    x,y=_poly_center(poly)
    height=max(p[1] for p in poly)-min(p[1] for p in poly)
    printed=set()
    for text,box in zip(texts,polys):
        if not re.fullmatch(r"[A-Za-z' ]{3,40}",text.strip()) or len(box)<4:continue
        xx,yy=_poly_center(box)
        if abs(xx-x)<=max(80,height*3) and 0<yy-y<=max(70,height*3):
            printed.add(re.sub(r"[^a-z]",'',text.lower()))
    candidates={station for station,pinyin in _STATION_PINYIN.items()
                if len(station)==len(name) and sum(a!=b for a,b in zip(station,name))==1
                and pinyin.lower() in printed}
    return candidates.pop() if len(candidates)==1 else name

def _get_valid_station_names():
    global _VALID_STATION_NAMES
    if not _VALID_STATION_NAMES:
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            json_path = os.path.abspath(os.path.join(current_dir, "..", "data", "railway_station.json"))
            with open(json_path, 'r', encoding='utf-8') as f:
                import json
                station_list = json.load(f)
                for name in station_list:
                    name = name.strip()
                    if name:
                        _VALID_STATION_NAMES.add(name)
        except Exception as e:
            logging.error(f"Failed to load station names from json: {e}")
    return _VALID_STATION_NAMES

def _is_valid_station_name(name: str) -> bool:
    if not name:
        return False
    name = name.strip()
    if not (1 <= len(name) <= 8):
        return False
    if len(name) == 1 and name not in _get_valid_station_names():
        return False
    if not re.fullmatch(r'[\u4e00-\u9fa5]+', name):
        return False
    if any(w in name for w in _STATION_INTERFERENCE):
        return False
    if re.fullmatch(r'(?:周|星期)[一二三四五六日天]', name):
        return False
    return True


def _poly_center(poly):
    if not poly or len(poly) < 4:
        return 0.0, 0.0
    cx = sum(p[0] for p in poly) / 4
    cy = sum(p[1] for p in poly) / 4
    return cx, cy


def _station_candidates(texts, polys):
    """Accept dictionary entries or new stations with route layout evidence."""
    known = _get_valid_station_names()
    candidates = []
    rail_rows=[_poly_center(p)[1] for t,p in zip(texts,polys)
               if re.fullmatch(r'(?:[GDCKTZSNLYA]\d{1,4}|\d{3,5})\s*次?',normalize_ticket_text(t))]
    for i, (text, poly) in enumerate(zip(texts, polys)):
        raw = text.strip()
        if '站' in raw and candidate_train_codes([raw]):
            chinese=re.sub(r'[^\u4e00-\u9fa5]','',raw).removesuffix('站')
            if chinese in known:raw=chinese
        # Paper tickets can merge a route arrow or a numeric service into a name.
        route = re.fullmatch(r'([\u4e00-\u9fa5]+?)[—→一-]([\u4e00-\u9fa5]+)', raw)
        if route and all(n in known for n in route.groups()) and len(poly)>=4:
            x,y=_poly_center(poly);width=max(p[0] for p in poly)-min(p[0] for p in poly)
            for name,offset in zip(route.groups(),(-.25,.25)):
                candidates.append((name,i,x+offset*width,y,True,20))
            continue
        inline = re.fullmatch(r'([\u4e00-\u9fa5]+?)(?:[GDCKTZSNLYA]?\d{1,5})次',raw)
        if inline and inline[1] in known:
            raw=inline[1]
        punctuated=re.sub(r'[。·\s]','',raw)
        if punctuated.removesuffix('站') in known:
            raw=punctuated
        joined=[(raw[:j],raw[j:]) for j in range(1,len(raw))
                if raw not in known and raw[:j] in known and raw[j:] in known and raw[:j]!=raw[j:]]
        if len(joined)==1 and len(poly)>=4:
            x,y=_poly_center(poly);width=max(p[0] for p in poly)-min(p[0] for p in poly)
            for name,offset in zip(joined[0],(-.25,.25)):
                candidates.append((name,i,x+offset*width,y,True,20))
            continue
        # Compact order lists put the complete route into a single text box.
        compact = re.fullmatch(r'[GDCKTZSNLYA]\d{1,4}\s*(.+?)\s*[-—→一]\s*(.+)', raw)
        pair = [part.strip().removesuffix('站') for part in compact.groups()] if compact else []
        if len(pair) == 2 and all(name in known for name in pair):
            x,y = _poly_center(poly)
            width = max(p[0] for p in poly)-min(p[0] for p in poly)
            for name,offset in zip(pair,(-.25,.25)):
                candidates.append((name,i,x+offset*width,y,True,20))
            continue
        merged = [m for m in re.finditer(r'([\u4e00-\u9fa5]{1,8})站',raw) if m[1] in known]
        if len(merged) >= 2 and len(poly) >= 4:
            left=min(p[0] for p in poly);right=max(p[0] for p in poly)
            _,y=_poly_center(poly)
            for match in merged:
                x=left+(right-left)*(match.start()+match.end())/(2*len(raw))
                candidates.append((match[1],i,x,y,True,20))
            continue
        labeled = re.match(r'^(?:出发站|到达站|出发|到达)[:：\s]*(.+)$', raw)
        name = labeled.group(1) if labeled else raw
        arrow = bool(re.search(r'[>›→]$', name))
        name = re.sub(r'[>›→\s]+$', '', name)
        # Position icons and a merged clock are outside the station's text.
        name = re.sub(r'^[^\u4e00-\u9fa5]+|[^\u4e00-\u9fa5]+$', '', name)
        name = name.removesuffix('站')
        if name[:1] in ('始', '终', '过', '一') and name[1:] in known:
            name = name[1:]
        if name[-1:] in ('始','终','过','一') and name[:-1] in known:
            name = name[:-1]
        name = _station_from_printed_pinyin(name,poly,texts,polys)
        if not _is_valid_station_name(name):
            continue
        x, y = _poly_center(poly)
        height = max(p[1] for p in poly) - min(p[1] for p in poly) if len(poly) >= 4 else 0
        if name in known or labeled:
            candidates.append((name, i, x, y, True, height))
        elif arrow or raw.endswith('站'):
            candidates.append((name, i, x, y, True, height))
        elif any(abs(row-y)<=max(40,height*2) for row in rail_rows):
            candidates.append((name, i, x, y, False, height))
        elif any(_extract_hhmm(t) and abs(_poly_center(p)[0] - x) < 80
                 and abs(_poly_center(p)[1] - y) < 100 for t, p in zip(texts, polys)):
            candidates.append((name, i, x, y, False, height))
    # Join a split station glyph only with adjacent geometry and a unique known name.
    for i,(text,poly) in enumerate(zip(texts,polys)):
        left=text.strip()
        if len(poly)<4 or not re.fullmatch(r'[\u4e00-\u9fa5]{1,3}',left) or left in known:
            continue
        x,y=_poly_center(poly);height=max(p[1] for p in poly)-min(p[1] for p in poly)
        right=max(p[0] for p in poly)
        joins=[]
        for j,(tail,box) in enumerate(zip(texts,polys)):
            if i==j or len(box)<4:continue
            name=(left+tail.strip()).removesuffix('站')
            xx,yy=_poly_center(box)
            gap=min(p[0] for p in box)-right
            if name in known and abs(yy-y)<=max(12,height*.6) and -.2*height<=gap<=height:
                joins.append((name,(x+xx)/2))
        if len(joins)==1:
            name,xx=joins[0]
            candidates.append((name,i,xx,y,True,height))
    # Prefer dictionary-supported endpoints over weak clock-adjacent labels.
    # Keep novel stations when there is no complete known pair.
    if len({name for name, *_ in candidates if name in known}) >= 2:
        candidates = [c for c in candidates if c[0] in known]
    return [(name, i, x) for name, i, x, y, trusted, height in candidates
            if trusted or any(j != i and tt and abs(yy - y) <= max(30, height * 2)
                              and abs(xx - x) > max(40, height * 2)
                              for _, j, xx, yy, tt, _ in candidates)]


def resolve_train_code(texts, departure_station='', polys=None):
    """Resolve only an unambiguous service, including departure-specific renumbering."""
    texts=[normalize_ticket_text(text) for text in texts]
    if departure_station:
        pattern = re.compile(re.escape(departure_station) + r'站?起车次(?:号)?变更为\s*([GDCKTZSNLYA]\d{1,4})(?!\d)')
        changed = {m.group(1) for t in texts for m in pattern.finditer(t)}
        if len(changed) == 1:
            return changed.pop()
        if polys:
            # 12306 puts “自当前车站起车次号变更为…” below the relevant stop.
            for i, (text, poly) in enumerate(zip(texts, polys)):
                note = re.search(r'当前车站起车次(?:号)?变更为\s*([GDCKTZSNLYA]\d{1,4})(?!\d)', text)
                if not note or len(poly) < 4:
                    continue
                _, y = _poly_center(poly)
                height = max(p[1] for p in poly) - min(p[1] for p in poly)
                stops = []
                for j, (stop, box) in enumerate(zip(texts, polys)):
                    name = re.sub(r'[^\u4e00-\u9fa5]+$', '', stop.strip()).removesuffix('站')
                    if name not in _get_valid_station_names() and name != departure_station:
                        continue
                    _, yy = _poly_center(box)
                    if 0 < y - yy <= max(60, height * 4):
                        stops.append((y - yy, name))
                if stops and min(stops)[1] == departure_station:
                    changed.add(note.group(1))
            if len(changed) == 1:
                return changed.pop()
    codes = candidate_train_codes(texts)
    return next(iter(codes)) if len(codes) == 1 else ''


def _order_dep_arr_by_geometry(a, b):
    """
    a,b: (name, cx, cy)
    - 如果两站主要横向分布(abs(dx) >= abs(dy))：按 x 左->右
    - 如果两站主要纵向分布(abs(dy) > abs(dx))：按 y 上->下
    返回 (dep_name, arr_name)
    """
    (n1, x1, y1) = a
    (n2, x2, y2) = b
    dx = x2 - x1
    dy = y2 - y1

    if abs(dx) >= abs(dy):
        # 左 -> 右
        return (n1, n2) if x1 <= x2 else (n2, n1)
    else:
        # 上 -> 下
        return (n1, n2) if y1 <= y2 else (n2, n1)


def _pick_left_right_station_names(station_with_y):
    """
    station_with_y: List[(name, cx, cy)]
    返回同一带内的两个站名（去重），并根据几何分布自动决定方向：
    - 横向：左->右
    - 纵向：上->下（适配旋转90°）
    """
    # 先过滤 + 去重（保留第一个出现的坐标）
    uniq = []
    seen = set()
    for n, cx, cy in station_with_y:
        if n in seen:
            continue
        if not _is_valid_station_name(n):
            continue
        uniq.append((n, cx, cy))
        seen.add(n)
        if len(uniq) >= 2:
            break

    if len(uniq) >= 2:
        return _order_dep_arr_by_geometry(uniq[0], uniq[1])
    if len(uniq) == 1:
        return uniq[0][0], ""
    return "", ""


def _pick_dep_arr_from_station_candidates(station_with_y):
    """
    station_with_y: List[(name, cx, cy)]
    策略：
    1) 先按 y 聚类（阈值略放宽），优先找“同一行>=2个不同站名”的行；
    2) 若找不到，则回退到“整体最靠上的两个不同站名”（按 y,x）。
    """
    if not station_with_y:
        return "", ""

    cleaned = []
    for name, cx, cy in station_with_y:
        name = _normalize_station_name(name)
        if _is_valid_station_name(name):
            cleaned.append((name, cx, cy))
    if not cleaned:
        return "", ""

    cleaned.sort(key=lambda x: (x[2], x[1]))  # y,x

    y_threshold = 45
    rows = []
    for item in cleaned:
        if not rows:
            rows.append([item])
        else:
            if abs(item[2] - rows[-1][0][2]) <= y_threshold:
                rows[-1].append(item)
            else:
                rows.append([item])

    # 找到最靠上的“同一行出现2个不同站名”的行
    for row in rows:
        row_sorted = sorted(row, key=lambda x: x[1])
        uniq = []
        seen = set()
        for n, cx, cy in row_sorted:
            if n not in seen:
                uniq.append((n, cx, cy))
                seen.add(n)
        if len(uniq) >= 2:
            return _order_dep_arr_by_geometry(uniq[0], uniq[1])

    # 回退：选“水平距离最大”的两站（抗倾斜/分行）
    # 先去重（同名站可能出现多次）
    uniq = []
    seen = set()
    for n, cx, cy in cleaned:
        if n not in seen:
            uniq.append((n, cx, cy))
            seen.add(n)

    if len(uniq) >= 2:
        best_pair = None
        best_dx = -1

        # 直接全量两两组合；站名候选一般很少，O(n^2)足够
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                dx = abs(uniq[i][1] - uniq[j][1])
                if dx > best_dx:
                    best_dx = dx
                    best_pair = (uniq[i], uniq[j])

        (a, b) = best_pair  # a,b: (name, cx, cy)
        return _order_dep_arr_by_geometry(a, b)

    if len(uniq) == 1:
        return uniq[0][0], ""
    return "", ""


def _split_carriage_seat_if_glued(ticket_info: dict):
    if ticket_info.get("carriage") or not ticket_info.get("seat_num"):
        return
    s = ticket_info["seat_num"].strip()
    m = re.fullmatch(r'(\d{2})(\d{2}[A-F])', s)
    if m:
        ticket_info["carriage"] = m.group(1)
        ticket_info["seat_num"] = m.group(2)


def _post_fix_arrival_station(ticket_info: dict, ocr_texts: list):
    if ticket_info.get("arrival_station") and ticket_info.get("departure_station"):
        return ticket_info

    stations = []
    seen = set()

    for t in ocr_texts:
        # 1) 'XX站' 模式（保留）
        for m in re.finditer(r'([\u4e00-\u9fa5]{2,8})站', t):
            nm = _normalize_station_name(m.group(1))
            if _is_valid_station_name(nm) and nm not in seen:
                stations.append(nm); seen.add(nm)

        # 2) 纯站名块模式：先不限制方向后缀，全部收集
        stripped = _normalize_station_name(t)
        # 去除结尾非中文标记（如 '西安北>'）
        stripped = re.sub(r'[^\u4e00-\u9fa5]+$', '', stripped)
        if _is_valid_station_name(stripped) and stripped not in seen:
            stations.append(stripped); seen.add(stripped)

    # 方向站优先（不改变旧行为，只是排序优先级）
    # def _rank(s: str) -> int:
    #     return 0 if s.endswith(("东", "西", "南", "北")) else 1
    # stations.sort(key=_rank)

    # 填充 dep/arr
    dep = ticket_info.get("departure_station", "")
    arr = ticket_info.get("arrival_station", "")

    if dep and not arr:
        for s in stations:
            if s != dep:
                ticket_info["arrival_station"] = s
                break
    elif not dep and not arr:
        if len(stations) >= 2:
            ticket_info["departure_station"] = stations[0]
            ticket_info["arrival_station"] = stations[1]

    # 一致性保护
    if ticket_info.get("departure_station") == ticket_info.get("arrival_station"):
        ticket_info["arrival_station"] = ""

    return ticket_info


# 新增：票面固定提示/字段标签等（这些不可能是姓名）
_NAME_BLOCKLIST_SUBSTR = {
    "事由", "动车组", "智能动车", "乘车人", "身份证", "中国铁路", "祝您旅途愉快",
    "仅供报销", "报销", "凭证", "遗失", "不补", "退票", "改签",
    "检票", "限乘", "当日", "当次", "中途下车失效","和谐号","复兴号",
    "买票请到", "请到", "12306", "95306","经停信息","成人票",
    "车站", "售", "出发", "到达","复制", "已支付", "学生票", "非现金支付",
    "线上购买","靠窗", "过道", "购票成功", "抢票成功", "返程", "加速包", "公众号",
    "行程", "积分", "价值", "换座", "申报", "大屏",
    "抢票", "专属", "关注", "分享", "祝您", "出行", "愉快", "返现","已进站","已出站",
    "星期一","星期二","星期三","星期四","星期五","星期六","星期日",
}



def _is_name_candidate_text(txt: str, ticket_info: dict, station_name_set: set) -> bool:
    """
    判断一个纯中文文本块是否可能是姓名（仅用于兜底规则）。
    设计目标：宁可漏，不可错（避免把票面提示词当姓名）。
    """
    if not txt:
        return False
    s = txt.strip()
    if not re.fullmatch(r'[\u4e00-\u9fa5]{2,6}', s):
        return False

    # 1) 站名互斥：只要这个块被识别/候选为站名，就绝不作为姓名
    if s in (station_name_set or set()):
        return False

    # 2) 票面固定提示/字段标签：包含这些子串就排除
    for bad in _NAME_BLOCKLIST_SUBSTR:
        if bad in s:
            return False

    # 4) 常见席别/无座等
    if s in {"无座", "站票", "一等座", "二等座", "商务座", "特等座", "硬座", "软座", "硬卧", "软卧"}:
        return False

    return True


def _is_id_like_text(t: str) -> bool:
    """身份证/证件号碎片/星号掩码块的粗判"""
    if not t:
        return False
    s = t.strip()
    # 含星号（掩码）
    if "*" in s and re.search(r'\d', s):
        return True
    # 纯数字且长度较长（身份证拆块、票号等）
    if s.isdigit() and len(s) >= 6:
        return True
    return False


def _is_low_confidence_name(name: str, station_name_set: set) -> bool:
    """判断当前 name 是否明显不可信，若不可信允许被纠正覆盖"""
    if not name:
        return True
    n = name.strip()
    if "站" in n:
        return True
    if n in (station_name_set or set()):
        return True
    for bad in _NAME_BLOCKLIST_SUBSTR:
        if bad in n:
            return True
    # 常见席别/提示词也视为低置信
    if n in {"无座", "站票", "一等座", "二等座", "商务座", "特等座", "硬座", "软座", "硬卧", "软卧"}:
        return True
    return False


def _extract_tail_name_from_masked_id_block(txt: str) -> str:
    """
    从类似 '****8035' / '4114****8035xxx' 这种块中提取尾部中文姓名。
    只提取 2~6 个中文字符，并排除包含'站'的情况。
    """
    if not txt:
        return ""
    s = txt.strip()

    # 关键：前面是若干 * 或数字（长度>=4），后面紧跟 2~6 个中文
    m = re.search(r'[\d\*]{4,}([\u4e00-\u9fa5]{2,6})$', s)
    if not m:
        return ""

    name = m.group(1).strip()
    if "站" in name:  # 防止误把“XX站”之类提成姓名
        return ""
    return name


_SEAT_TYPE_KEYWORDS = [
        "无座", "站票",'新空调硬座', '新空调硬卧', '新空调软座', '新空调软卧',
    "商务座", "特等座", "一等座", "二等座", "硬座", "软座", "硬卧", "软卧",
    "二等卧", "二等硬", "一等硬", "一等卧", "等座",
]


def _extract_seat_type_keyword(txt: str) -> str:
    if not txt:
        return ""
    for st in _SEAT_TYPE_KEYWORDS:
        if st in txt:
            return st
    return ""


def _is_discount_block(s: str) -> bool:
    """像 6.6折、7折、8.5折 这种块，绝不能参与票价解析/拼接"""
    if not s:
        return False
    s = s.strip()
    return ("折" in s) or bool(re.search(r'\d+(?:\.\d+)?\s*折', s))


def _is_price_fragment(s: str) -> bool:
    """
    允许参与拼接的“价格碎片”块：
    - ￥
    - ￥70 / 70元 / 443. / .5 / 5元 等
    但不允许包含“折”
    """
    if not s:
        return False
    s = s.strip()
    if _is_discount_block(s):
        return False
    # 只允许这些字符：数字、￥¥、点、元、空格
    return bool(re.fullmatch(r'[￥¥\d\.\s元]+', s))


# ============== 新增：提取 月日 / 时间 ==============
def _extract_month_day(txt: str):
    """从 '1月9日（周五）' / '01月09日' / '01-28周二' 等提取 (mm, dd)"""
    if not txt:
        return None
    s = _fix_ocr_text(txt).strip()
    
    # 0. 点号格式 (如 2026.04.02)
    m0 = re.search(r'(?:\d{4}\.)?(\d{1,2})\.(\d{1,2})', s)
    if m0:
        # 价格/折扣块里的点号不是日期："6.6折"、"￥12.5"、"5.5元"
        # 否则会把折扣块误读成 06月06日、把票价误读成 12月05日。
        before = s[m0.start() - 1] if m0.start() > 0 else ''
        after = s[m0.end()] if m0.end() < len(s) else ''
        if before not in ('￥', '¥') and after not in ('折', '元'):
            mm = m0.group(1).zfill(2)
            dd = m0.group(2).zfill(2)
            try:
                imonth = int(mm)
                iday = int(dd)
                if 1 <= imonth <= 12 and 1 <= iday <= 31:
                    return (mm, dd)
            except:
                pass

    # 1. 标准格式：X月X日
    m = re.search(r'(\d{1,2})\s*月\s*(\d{1,2})\s*日', s)
    if m:
        mm = m.group(1).zfill(2)
        dd = m.group(2).zfill(2)
        return (mm, dd)
    
    # 2. 短横线/斜杠格式：01-28 或 01/28
    # 通常后面会跟 '周' (01-28周二) 或者只是单纯的日期
    # 增加校验防止误匹配非日期数字
    m2 = re.search(r'(?<!\d)(\d{1,2})\s*[-/]\s*(\d{1,2})(?!\d)', s)
    if m2:
        mm = m2.group(1).zfill(2)
        dd = m2.group(2).zfill(2)
        try:
            imonth = int(mm)
            iday = int(dd)
            if 1 <= imonth <= 12 and 1 <= iday <= 31:
                return (mm, dd)
        except:
            pass
            
    return None

def _extract_hhmm(txt: str) -> str:
    """从 '17:12' / '18：18' 提取 HH:MM"""
    if not txt:
        return ""
    s = _fix_ocr_text(txt).strip()
    m = re.search(r'(?<!\d)(\d{1,2})[:：](\d{2})(?!\d)', s)
    if not m:
        return ""
    return f"{m.group(1).zfill(2)}:{m.group(2)}"


# OCR 常把整串日期时间识别成一个粘连的数字块：年份直接粘在月份前（'202405月07日'），
# 时分直接粘在日字后（'... 日1022'）。通用提取器看不到这两段信息，
# 只能还原出 '05月07日'，年份与时分会整体丢失，这里单独识别出来。
_COMPACT_YEAR_RE = re.compile(r'(?<!\d)(\d{4})\d{1,2}月\d{1,2}日')
_COMPACT_TIME_RE = re.compile(r'(?<!\d)\d{4}年?\d{1,2}月\d{1,2}日(\d{2})(\d{2})(?!\d)')


def _select_name_by_proximity(ocr_texts: list, station_name_set: set, ticket_info: dict) -> str:
    """
    额外建议功能：
    若存在证件号碎片/星号掩码块/身份证标签，则从其附近挑选最像姓名的纯中文块。
    """
    if not ocr_texts:
        return ""

    # 1. 寻找锚点：ID-like 文本 或 明确的ID标签
    anchors = []
    for i, t in enumerate(ocr_texts):
        if _is_id_like_text(t):
            anchors.append(i)
        elif "身份证" in t or "证件" in t:
             anchors.append(i)
    
    if not anchors:
        return ""

    candidates = []
    for i, t in enumerate(ocr_texts):
        # 排除锚点本身作为姓名候选
        if i in anchors:
            continue
            
        # 1) 纯中文块候选
        is_cand = _is_name_candidate_text(t, ticket_info, station_name_set)
        if is_cand:
            candidates.append((i, t.strip()))
            continue

        # 2) 粘连块候选（如 '****8035xxx'）
        glued = _extract_tail_name_from_masked_id_block(t)
        if glued:
            candidates.append((i, glued))

    if not candidates:
        return ""

    # 选择距离任意 anchor 最近的候选姓名
    best_name = ""
    best_dist = 10**9
    for ci, name in candidates:
        dist = min(abs(ci - ai) for ai in anchors)
        if dist < best_dist:
            best_dist = dist
            best_name = name

    # 距离阈值：过远就不强行认定（避免误判）
    return best_name if best_dist <= 4 else ""


def _build_departure_datetime(ocr_texts: list, polys: list, anchor_y=None) -> str:
    """
    只输出出发时间：例如 '01月09日 17:12' 或 '2025年01月09日 17:12'
    策略优化：
    1. 收集所有可能的 日期(md_cands) 和 时间(time_cands)。
    2. 如果有 anchor_y (车次行)，优先选离 anchor_y 最近的组合。
    3. 如果没有 anchor_y 或 距离太远，则选 彼此距离最近 的组合 (Date + Time)。
    """
    if not ocr_texts or not polys:
        return ""

    # 年份（可选，有就拼，没有就不猜）
    year = ""
    selected_date_index = None

    # 收集 月日、时间候选（带坐标）
    md_cands = []    # (index, cx, cy, mm, dd)
    time_cands = []  # (index, cx, cy, hhmm)

    for i, (t, poly) in enumerate(zip(ocr_texts, polys)):
        if any(w in t for w in ('广告', '优惠', '活动', '截止', '经停', '当前时间')):
            continue
        cx, cy = _poly_center(poly)

        md = _extract_month_day(t)
        if md:
            mm, dd = md
            md_cands.append((i, cx, cy, mm, dd))

        hhmm = _extract_hhmm(t)
        if hhmm:
            time_cands.append((i, cx, cy, hhmm))
        elif md:
            # '粘连块'：时分直接粘在日字后、没有冒号（'202405月07日1022开'）。
            # 通用时间提取器需要冒号，会跳过这种块，导致时分丢失。
            compact = _COMPACT_TIME_RE.search(t)
            if compact:
                time_cands.append((i, cx, cy, f"{compact.group(1)}:{compact.group(2)}"))

    if not md_cands and not time_cands:
        return ""

    # 辅助：计算两个候选的距离 (曼哈顿距离 or 欧氏距离? 这里简单用 abs dy + abs dx 权重)
    def _dist(c1, c2):
        return abs(c1[2] - c2[2]) + abs(c1[1] - c2[1]) * 0.5

    best_mm, best_dd = "", ""
    best_time = ""

    # 情况A：有 anchor_y，尝试找 anchor_y 附近的
    # 但是要注意：有些票面 日期在最上面，车次在中间，相距很远。
    # 所以 anchor_y 只是一个参考，不能作为硬过滤。
    
    # 策略：
    # 1. 如果有 md_cands 和 time_cands，尝试配对，找“彼此最近”且“符合阅读顺序”的对。
    # 2. 如果只有 md_cands，选离 anchor_y 最近的，或者最靠上的。
    # 3. 如果只有 time_cands，选离 anchor_y 最近的（如果是出发时间，通常和车次较近，或者在最左/最上）。

    if md_cands and time_cands:
        # 寻找最佳配对
        best_pair_score = 10**9
        best_pair = None

        for md in md_cands:
            for tm in time_cands:
                # 1. 紧密度 (Tightness): Date 和 Time 之间的距离
                d_tight = _dist(md, tm)
                
                # 2. 位置分 (Position): 该组合在页面上的位置 (偏好 Top-Left)
                # 优先选择页面左上方的“日期+时间”组合作为出发时间
                avg_x = (md[1] + tm[1]) / 2
                avg_y = (md[2] + tm[2]) / 2
                
                # 综合分 = 紧密度 + 位置惩罚
                # 系数 0.1 保证位置影响足够打破 Tie，但不会让相距很远的组合仅仅因为靠左而被选中
                score = d_tight + (avg_x + avg_y) * 0.1
                
                if score < best_pair_score:
                    best_pair_score = score
                    best_pair = (md, tm)
        
        if best_pair:
            selected_date_index = best_pair[0][0]
            best_mm, best_dd = best_pair[0][3], best_pair[0][4]
            best_time = best_pair[1][3]
            
    else:
        # 只有其中一种
        if md_cands:
            # 优先选离 anchor_y 最近的
            if anchor_y is not None:
                md_cands.sort(key=lambda x: abs(x[2] - anchor_y))
            else:
                # 否则选最靠上的
                md_cands.sort(key=lambda x: x[2])
            best_mm, best_dd = md_cands[0][3], md_cands[0][4]
            selected_date_index = md_cands[0][0]

        if time_cands:
            # 时间：如果有多个时间（出发、到达），通常出发在左/上
            # 简单策略：按 Geometry 排序
            # 1. 过滤掉特别远的（如果 anchor_y 存在且很强相关）- 暂时不滤
            
            # 区分出发/到达：
            # 如果是横排：左边是出发
            # 如果是竖排：上面是出发
            # 计算分布范围
            xs = [x[1] for x in time_cands]
            ys = [x[2] for x in time_cands]
            range_x = max(xs) - min(xs) if len(xs) > 1 else 0
            range_y = max(ys) - min(ys) if len(ys) > 1 else 0

            if range_x >= range_y:
                 # 横向：选最左
                 best_cand = min(time_cands, key=lambda x: x[1])
            else:
                 # 纵向：选最上
                 best_cand = min(time_cands, key=lambda x: x[2])
            best_time = best_cand[3]

    # 拼接输出
    date_part = ""
    if selected_date_index is not None:
        # A year belongs to the selected date, never to an unrelated advert.
        selected_text = _fix_ocr_text(ocr_texts[selected_date_index])
        ym = re.search(r'(?<!\d)(\d{4})[年./-]\d{1,2}[月./-]\d{1,2}', selected_text)
        if ym:
            year = ym.group(1)
        elif compact_year := _COMPACT_YEAR_RE.search(selected_text):
            # 年份直接粘在月份前：'202405月07日' -> 2024年05月07日
            year = compact_year.group(1)
        else:
            # OCR can split the year from the date. Only an adjacent, bare year
            # in the same row/column belongs to it; prose/adverts never do.
            dx, dy = _poly_center(polys[selected_date_index])
            for j, (text, poly) in enumerate(zip(ocr_texts, polys)):
                bare_year = re.fullmatch(r'(\d{4})年', text.strip())
                x, y = _poly_center(poly)
                if bare_year and abs(j - selected_date_index) == 1 and (
                    (abs(y - dy) <= 20 and 0 <= dx - x <= 100) or
                    (abs(x - dx) <= 20 and 0 <= dy - y <= 60)
                ):
                    year = bare_year.group(1)
                    break
    if not year and best_mm and best_dd:
        header_years=set()
        for text in ocr_texts:
            explicit=re.match(r'^(?:乘车日期|发车时间|出发日期)[:：]\s*(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})',text.strip())
            if explicit and (int(explicit[2]),int(explicit[3]))==(int(best_mm),int(best_dd)):
                header_years.add(explicit[1])
        if len(header_years)==1:year=header_years.pop()
    if best_mm and best_dd:
        date_part = f"{best_mm}月{best_dd}日"
        if year:
            date_part = f"{year}年{date_part}"

    if date_part and best_time:
        return f"{date_part} {best_time}"
    if date_part:
        return date_part
    return best_time


def parse_ticket_info(ocr_texts, polys):
    """
    解析OCR识别的文本
    """
    logging.debug("ticket_parser.parse_ticket_info: start")
    ocr_texts = [normalize_ticket_text(t) for t in ocr_texts]
    logging.debug("ticket_parser.parse_ticket_info: raw_texts=%s", ocr_texts)
    ticket_info = {
        "train_code": "",
        "departure_station": "",
        "arrival_station": "",
        "datetime": "",
        "carriage": "",
        "seat_num": "",
        "berth_type": "",
        "price": "",
        "seat_type": "",
        "name": "",
        "discount_type": "",
        "detection_id": 0
    }

    # 为每个文本块计算中心点
    centers = []
    for i, poly in enumerate(polys):
        if len(poly) >= 4:
            # 计算中心点
            x_sum = sum(p[0] for p in poly)
            y_sum = sum(p[1] for p in poly)
            center_x = x_sum / 4
            center_y = y_sum / 4
            centers.append((center_y, center_x, i))
        else:
            centers.append((0, 0, i))

    # 按中心点的y坐标排序（从上到下）
    centers.sort(key=lambda x: x[0])  # 按y坐标排序
    visual_order_indices = [idx for _, _, idx in centers]

    # 从ocr_texts和visual_order_indices中获取按视觉顺序的文本
    visual_texts = [ocr_texts[i] for i in visual_order_indices]

    # 从visual_texts中提取车站
    station_candidates = []  # (name, visual_idx, cx)

    station_candidates = _station_candidates(visual_texts, [polys[i] for i in visual_order_indices])

    # 从visual_texts中提取车次
    train_code = ""
    train_index_in_visual = -1
    # 车次优先级：G > D > C > K > T > Z
    present_codes=candidate_train_codes(visual_texts)
    prefixes = list('GDCKTZS') if any(c[0] in 'GDCKTZS' for c in present_codes) else list('NLYA')
    for idx, txt in enumerate(visual_texts):
        fixed_txt = _fix_ocr_text(txt)
        if train_code:
            break
        for p in prefixes:
            # 不依赖 \b：允许后面跟中文，但不允许继续跟数字
            # 同时避免在长串字母数字中间误命中
            m = re.search(rf'(?<![A-Za-z0-9])({p}\d{{1,4}})(?!\d)', fixed_txt)
            if not m:
                continue
            code = m.group(1)
            if code not in present_codes:
                continue
            # 过滤明显伪造码：如 C0000 / G0000
            if re.fullmatch(r'[GDCKTZSNLYA]0{3,4}', code):
                continue
            # 基本长度约束（2~5）
            if 2 <= len(code) <= 5:
                train_code = code
                train_index_in_visual = idx
                break
    # 数字纯车次兜底（如“7006”）：仅当未识别到字母前缀时启用
    if not train_code:
        for idx, txt in enumerate(visual_texts):
            s = _fix_ocr_text(txt).strip()
            # 排除明显价格/时间/日期块
            if any(x in s for x in ["￥", "元", ":", "：", "月", "日", "/", "-", ".", "年"]):
                continue
            # 排除长数字（订单号/票号）
            if re.search(r'\d{6,}', s):
                continue
            # A fare or seat number inside a larger block is not a train code.
            m_num = re.fullmatch(r'(\d{3,5})\s*(?:次|车次)?', s)
            if not m_num:
                # Preserve the actual printed legacy prefix (e.g. 游5次).
                m_num = re.fullmatch(r'((?:游|临|特|直|快|普)\d{1,4})次',s)
            if not m_num:
                embedded=re.fullmatch(r'([\u4e00-\u9fa5]+?)(\d{1,5})次',s)
                if embedded and embedded[1].removesuffix('站') in _get_valid_station_names():
                    m_num=re.fullmatch(r'(\d{1,5})次',embedded[2]+'次')
            if m_num:
                train_code = m_num.group(1)
                train_index_in_visual = idx
                logging.debug("ticket_parser.train_code: numeric fallback detected %s in txt=%s", train_code, txt)
                break
    ticket_info["train_code"] = train_code

    # === 新增：车次的y坐标锚点，用于修正倾斜导致的站名行分裂 ===
    train_anchor_y = None
    if train_index_in_visual >= 0:
        train_orig_idx = visual_order_indices[train_index_in_visual]
        _, train_anchor_y = _poly_center(polys[train_orig_idx])

    # === 只拼“出发日期 + 出发时间”到 datetime ===
    if not ticket_info["datetime"]:
        ticket_info["datetime"] = _build_departure_datetime(ocr_texts, polys, train_anchor_y)

    if station_candidates:
        # 获取每个候选车站的真实 y 坐标（通过 orig_idx 找到原始 poly）
        station_with_y = []
        for name, visual_idx, cx in station_candidates:
            orig_idx = visual_order_indices[visual_idx]
            poly = polys[orig_idx]
            cy = sum(p[1] for p in poly) / 4 if len(poly) >= 4 else 0
            station_with_y.append((name, cx, cy))

        # 先按 y 分组（取最小 y 的那一行，通常是出发/到达站所在行）
        station_with_y.sort(key=lambda x: (x[2], x[1]))  # 先 y，再 x

        # 提取 y 最小的那一行（顶部行）
        min_y = station_with_y[0][2]
        top_row_stations = [s for s in station_with_y if abs(s[2] - min_y) < 30]  # 阈值可调

        # 按 x 排序（左 → 右）
        top_row_stations.sort(key=lambda x: x[1])

        unique_names = []
        seen = set()
        for name, _, _ in top_row_stations:
            if name not in seen:
                unique_names.append(name)
                seen.add(name)

        if station_candidates:
            station_with_y = []
            for name, visual_idx, cx in station_candidates:
                orig_idx = visual_order_indices[visual_idx]
                poly = polys[orig_idx]
                cy = sum(p[1] for p in poly) / 4 if len(poly) >= 4 else 0
                station_with_y.append((_normalize_station_name(name), cx, cy))

            # === 新增：优先使用“车次所在行”的站名（抗倾斜/旋转）===
            dep, arr = "", ""
            if train_anchor_y is not None:
                # 经验阈值：同一行上下浮动，倾斜票面会拉大y差，所以这里放宽一些
                anchor_poly=polys[visual_order_indices[train_index_in_visual]]
                anchor_height=max(p[1] for p in anchor_poly)-min(p[1] for p in anchor_poly) if len(anchor_poly)>=4 else 0
                band = [s for s in station_with_y if abs(s[2] - train_anchor_y) <= max(90,anchor_height*2)]
                band.sort(key=lambda s:abs(s[2]-train_anchor_y))
                # band里如果能取到2个站名，按x左->右就是出发->到达
                dep, arr = _pick_left_right_station_names(band)

            # 回退到你原来的逻辑（按y聚类/最靠上两个）
            if not dep or not arr:
                dep, arr = _pick_dep_arr_from_station_candidates(station_with_y)

            if dep and not ticket_info["departure_station"]:
                ticket_info["departure_station"] = dep
            if arr and not ticket_info["arrival_station"]:
                ticket_info["arrival_station"] = arr

    # === 新增：构建站名集合（供姓名候选互斥使用），只构建一次 ===
    station_name_set = set()
    if ticket_info.get("departure_station"):
        station_name_set.add(ticket_info["departure_station"].strip())
        station_name_set.add(ticket_info["departure_station"].strip() + "站")
    if ticket_info.get("arrival_station"):
        station_name_set.add(ticket_info["arrival_station"].strip())
        station_name_set.add(ticket_info["arrival_station"].strip() + "站")

    # station_candidates 里也加入（候选多为不含“站”的形式，但也补全“站”变体）
    for n, _, _ in station_candidates:
        nn = _normalize_station_name(n)
        if _is_valid_station_name(nn):
            station_name_set.add(nn)
            station_name_set.add(nn + "站")

    has_id_like = any(_is_id_like_text(t) or "身份证" in t or "证件" in t for t in ocr_texts)

    # 遍历每个独立文本块，逐个匹配对应字段
    for idx, txt in enumerate(ocr_texts):
        if not ticket_info["train_code"] or not (ticket_info["departure_station"] and ticket_info["arrival_station"]):
            # 1. 查找所有“XX站”车站及其位置
            stations_in_txt = []
            for match in re.finditer(r'([\u4e00-\u9fa5]{1,6})站', txt):
                name = match.group(1)
                if _is_valid_station_name(name):
                    stations_in_txt.append((name, match.start(), match.end()))

            # 2. 查找车次及其位置
            train_match = None
            if not ticket_info["train_code"]:
                train_match = re.search(r'(?<![0-9])([GDCKTZSNLYA]\d{1,4})(?![0-9])', txt)
                if train_match:
                    ticket_info["train_code"] = train_match.group(1)
                    train_start = train_match.start()
                else:
                    train_start = -1
            else:
                # 车次已知，但仍可尝试定位（用于已有车次但未处理车站的情况）
                tm = re.search(r'(?<![0-9])([GDCKTZSNLYA]\d{1,4})(?![0-9])', txt)
                train_start = tm.start() if tm else -1

            # 3. 如果有车站
            if stations_in_txt:
                # 按位置排序
                stations_in_txt.sort(key=lambda x: x[1])

                if train_start >= 0:
                    # 车次存在：找车次之后的第一个车站 → 到达站
                    arrival_candidates = [s for s in stations_in_txt if s[1] > train_start]
                    departure_candidates = [s for s in stations_in_txt if s[1] < train_start]

                    if arrival_candidates and not ticket_info["arrival_station"]:
                        ticket_info["arrival_station"] = arrival_candidates[0][0]  # 最近的右侧车站

                    if departure_candidates and not ticket_info["departure_station"]:
                        ticket_info["departure_station"] = departure_candidates[-1][0]  # 最近的左侧车站

                else:
                    # 无车次：按原逻辑，第一个是出发，第二个是到达
                    if not ticket_info["departure_station"]:
                        ticket_info["departure_station"] = stations_in_txt[0][0]
                    elif not ticket_info["arrival_station"] and len(stations_in_txt) > 1:
                        ticket_info["arrival_station"] = stations_in_txt[1][0]

        # 3. 发车时间匹配（支持中文/英文冒号，带或不带“开”字）
        if not ticket_info["datetime"]:
            # 先在整个 ocr_texts 中分别找日期和时间（并支持跨文本块拼接）
            year_candidate = None
            date_candidate = None
            time_candidate = None
            mdhm_candidate = None  # "MM月DD日 HH:MM"

            for t in ocr_texts:
                tt = _fix_ocr_text(t).strip()
                # A) 年份块：如 "2025年"
                if not year_candidate:
                    ym = re.search(r'(\d{4})年', tt)
                    if ym:
                        year_candidate = ym.group(1)
                # B) 完整日期块：YYYY年MM月DD日（你原来的规则）或 YYYY.MM.DD
                if not date_candidate:
                    d_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', tt)
                    if d_match:
                        date_candidate = d_match.group(1)
                    else:
                        d_match_dot = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', tt)
                        if d_match_dot:
                            yy = d_match_dot.group(1)
                            mm = d_match_dot.group(2).zfill(2)
                            dd = d_match_dot.group(3).zfill(2)
                            date_candidate = f"{yy}年{mm}月{dd}日"
                # C) 月日+时间在同一块：如 "06月02日10:40开"
                #    把月日和时分一起抓出来，供 year-only 拼接用
                if not mdhm_candidate:
                    mdhm = re.search(r'(\d{1,2})月(\d{1,2})日\s*(\d{1,2})[:：](\d{2})\s*开?', tt)
                    if mdhm:
                        mm = mdhm.group(1).zfill(2)
                        dd = mdhm.group(2).zfill(2)
                        hh = mdhm.group(3).zfill(2)
                        mi = mdhm.group(4).zfill(2)
                        mdhm_candidate = (mm, dd, hh, mi)

                # D) 单独时间块：HH:MM（你原来的规则，保留）
                if not time_candidate:
                    t_match = re.search(r'(\d{1,2})[:：](\d{2})\s*开?', tt)
                    if t_match:
                        h = t_match.group(1).zfill(2)
                        m = t_match.group(2).zfill(2)
                        time_candidate = f"{h}:{m}"
                if date_candidate and time_candidate:
                    break
                # E) 紧凑粘连日期时间（年/月/日可能丢或误识别）
                # 例：2025405八26108:46开  -> 2025年05月26日 08:46
                if not date_candidate and not mdhm_candidate:
                    m_compact = re.search(
                        r'(\d{4})\D*(\d{1,2})\D*([0-3]?\d)(?:日|1|I|l)?\s*(\d{1,2})[:：](\d{2})\s*开?',
                        tt
                    )
                    if m_compact:
                        yy = m_compact.group(1)
                        mm = m_compact.group(2).zfill(2)
                        dd = m_compact.group(3).zfill(2)
                        hh = m_compact.group(4).zfill(2)
                        mi = m_compact.group(5).zfill(2)
                        # 直接生成最终 datetime
                        ticket_info["datetime"] = f"{yy}年{mm}月{dd}日 {hh}:{mi}"
                        break

            if ticket_info["datetime"]:
                continue

            # 1) 原逻辑：完整日期 + 时间
            if date_candidate and time_candidate:
                ticket_info["datetime"] = f"{date_candidate} {time_candidate}"
            # 2) 新增：年份块 + (月日时分) 块
            elif year_candidate and mdhm_candidate:
                mm, dd, hh, mi = mdhm_candidate
                ticket_info["datetime"] = f"{year_candidate}年{mm}月{dd}日 {hh}:{mi}"
            # 3) 只有日期（无时间）
            elif date_candidate:
                ticket_info["datetime"] = date_candidate

        if not ticket_info["datetime"]:
            # 定义多种时间格式正则（按优先级排序）
            time_patterns = [
                r'(\d{4})(\d{2})月(\d{2})(\d{3})[:：](\d{2})开?',
                r'(\d{4})(\d{2})(\d{2})日(\d{2})(\d{2})',
                # '2024年1005日16:50开'
                r'(\d{4})年(\d{2})(\d{2})日(\d{1,2}):(\d{2})开?',
                r'(\d{4})(\d{2})月(\d{1,2})日(\d{4})开?',
                r'(\d{4}年\d{1,2}月)(\d{1,2})[^\d:\s]{1,3}?(\d{1,2})[:：](\d{2})开?',
                # 格式1: "2020年08月29日20：54开" 或 "2020年08月29日20:54开"
                r'(\d{4}年\d{1,2}月\d{1,2}日)[\s:：]*(\d{1,2})[:：](\d{2})开?',
                # 格式2: "2020年08月29日 20:54"（有空格）
                r'(\d{4}年\d{1,2}月\d{1,2}日)\s+(\d{1,2})[:：](\d{2})',
                # 格式3: 紧凑型 "2020年08月29日2054"
                r'(\d{4}年\d{1,2}月\d{1,2}日)(\d{2})(\d{2})',
            ]

            for i, pattern in enumerate(time_patterns):
                match = re.search(pattern, txt)
                if match:
                    if i == 0:
                        year = match.group(1)
                        month = match.group(2).zfill(2)
                        day = match.group(3).zfill(2)
                        hour = match.group(4)[-2:].zfill(2)
                        minute = match.group(5).zfill(2)
                        ticket_info["datetime"] = f"{year}年{month}月{day}日 {hour}:{minute}"
                    elif i == 1:
                        year = match.group(1)
                        month = match.group(2).zfill(2)
                        day = match.group(3).zfill(2)
                        hour = match.group(4).zfill(2)
                        minute = match.group(5).zfill(2)
                        ticket_info["datetime"] = f"{year}年{month}月{day}日 {hour}:{minute}"

                    elif i == 2:
                        year = match.group(1)
                        month = match.group(2).zfill(2)
                        day = match.group(3).zfill(2)
                        hour = match.group(4).zfill(2)
                        minute = match.group(5).zfill(2)
                        ticket_info["datetime"] = f"{year}年{month}月{day}日 {hour}:{minute}"

                    elif i == 3:
                        # 新规则：202404月07日1022开 → YYYY MM DD HHmm
                        year = match.group(1)
                        month = match.group(2).zfill(2)
                        day = match.group(3).zfill(2)
                        time4 = match.group(4)
                        if len(time4) == 4:
                            hour = time4[:2]
                            minute = time4[2:]
                        else:
                            hour = time4.zfill(4)[:2]
                            minute = time4.zfill(4)[2:]
                        ticket_info["datetime"] = f"{year}年{month}月{day}日 {hour}:{minute}"

                    elif i == 4:
                        # 泛化分隔符模式：如 2025年01月18H13:46
                        year_month = match.group(1)
                        day = match.group(2).zfill(2)
                        hour = match.group(3).zfill(2)
                        minute = match.group(4).zfill(2)
                        ticket_info["datetime"] = f"{year_month}{day}日 {hour}:{minute}"
                    else:
                        date_part = match.group(1)
                        hour = match.group(2).zfill(2)
                        minute = match.group(3).zfill(2)
                        if i == 7:  # 紧凑型：YYYY年MM月DDHHMM
                            hour = match.group(2)
                            minute = match.group(3)
                        ticket_info["datetime"] = f"{date_part} {hour}:{minute}"
                    break

            # 如果没匹配到，尝试粘连时间（如 2024年02月26014:08 → 应为 2024年02月26日 14:08）
            if not ticket_info["datetime"]:
                # 无时间格式（2024年02月26日）
                date_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', txt)
                if date_match:
                    ticket_info["datetime"] = date_match.group(1)
                sticky_match = re.search(r'(\d{4}年\d{1,2}月)(\d{4,6}):(\d{2})', txt)
                if sticky_match:
                    year_month = sticky_match.group(1)
                    time_digits = sticky_match.group(2)
                    minute = sticky_match.group(3).zfill(2)

                    if len(time_digits) == 4:
                        day = time_digits[:2]
                        hour = time_digits[2:]
                    elif len(time_digits) == 5:
                        day = time_digits[:2]
                        hour = time_digits[-2:]
                        # 检查：hour 是否合理（00~23）
                        if hour.isdigit() and 0 <= int(hour) <= 23:
                            pass
                        else:
                            hour = time_digits[2:4]
                    elif len(time_digits) == 6:
                        day = time_digits[:2]
                        hour = time_digits[2:4]
                    else:
                        day = time_digits[:2] if len(time_digits) >= 2 else '01'
                        hour = time_digits[2:4] if len(time_digits) >= 4 else '00'
                    # 补零并验证
                    day = day.zfill(2)
                    hour = hour.zfill(2)

                    d = int(day)
                    h = int(hour)
                    if 1 <= d <= 31 and 0 <= h <= 23:
                        ticket_info["datetime"] = f"{year_month}{day}日 {hour}:{minute}"

            # 如果已提取到时间，不在这里 continue，让其他字段（比如车次、座位号、价格等）继续尝试从该文本块匹配
            # 删除了: if ticket_info["datetime"]: continue

        # ====== 无座/站票优先处理：seat_type = 无座(或站票)，seat_num 必须为空 ======
        if not ticket_info["seat_num"]:
            ns = None
            if "无座" in txt:
                ns = "无座"
            elif "站票" in txt:
                ns = "站票"

            if ns:
                ticket_info["seat_type"] = ns
                ticket_info["seat_num"] = ""  # 强制为空（按你的口径）
                logging.debug("ticket_parser.seat_type: detected no-seat, seat_type=%s, cleared seat_num", ns)

                # 无座票常写：车厢04车 / (硬座车厢04车) 等，尽量补 carriage
                if not ticket_info["carriage"]:
                    m_car = re.search(r'车厢\s*(\d{1,2})\s*车', txt) or re.search(r'(\d{1,2})\s*车', txt)
                    if m_car:
                        ticket_info["carriage"] = m_car.group(1).zfill(2)
                else:
                    ticket_info["carriage"] = str(ticket_info["carriage"]).zfill(2)

                # 这个块已经处理完，避免后面 seat_type 又被“硬座”覆盖
                continue

        # 4. 车厢号+座位号+铺位类型匹配（重点优化：同一文本块拆分多个字段）
        if not (ticket_info["carriage"] and ticket_info["seat_num"] and ticket_info["berth_type"]):
            # 匹配格式：数字车+数字+字母号+铺位类型（如09车14F号上铺、3车02号中铺、12车厢009座中铺）
            # combo_match = re.search(r'(\d+)车(\d+[A-F]?)号(上铺|中铺|下铺)?', txt)
            # 车厢+座位+铺位类型（匹配空白变体：上\s*铺 等，支持 '车/车厢' 和 '号/座'）
            combo_match = re.search(r'(\d{1,2})\s*(?:车|车厢)\s*(\d{1,3}\s*[A-Fa-f]?)\s*(?:号|座)?\s*((?:上\s*铺)|(?:中\s*铺)|(?:下\s*铺))?', txt)
            if combo_match:
                # 拆分车厢号、座位号、铺位类型
                if not ticket_info["seat_type"]:
                    st = _extract_seat_type_keyword(txt)
                    if st:
                        ticket_info["seat_type"] = st
                if not ticket_info["carriage"]:
                    ticket_info["carriage"] = combo_match.group(1)
                if not ticket_info["seat_num"]:
                    ticket_info["seat_num"] = re.sub(r'\s+', '', combo_match.group(2)).upper()
                if not ticket_info["berth_type"] and combo_match.group(3):
                    # 归一化去掉中间空白：上\s*铺 -> 上铺
                    ticket_info["berth_type"] = re.sub(r'\s+', '', combo_match.group(3))
                    logging.debug("ticket_parser.parse_ticket_info: combo berth_type=%s from txt=%s", ticket_info["berth_type"], txt)
                if not ticket_info["carriage"] and ticket_info["seat_num"]:
                    m = re.fullmatch(r'(\d{2})(\d{2}[A-F])', ticket_info["seat_num"])
                    if m:
                        ticket_info["carriage"] = m.group(1)
                        ticket_info["seat_num"] = m.group(2)
                continue
            # 追加：0206F号 这种粘连（常见于 "二等座0206F号"）
            if not (ticket_info["carriage"] and ticket_info["seat_num"]):
                if ("订单" not in txt) and ("订单号" not in txt):
                    glued_match = re.search(r'(\d{2})(\d{2}[A-Fa-f])号', txt)
                    if glued_match:
                        if not ticket_info["seat_type"]:
                            st = _extract_seat_type_keyword(txt)
                            if st:
                                ticket_info["seat_type"] = st

                        if not ticket_info["carriage"]:
                            ticket_info["carriage"] = glued_match.group(1)
                        if not ticket_info["seat_num"]:
                            ticket_info["seat_num"] = glued_match.group(2).upper()
                        continue

        # 处理 03403A → 03车03A号
        if not (ticket_info["carriage"] and ticket_info["seat_num"]):
            # 假设前2位是车厢，后2位是座位数字，最后是字母
            short_seat_match = re.fullmatch(r'(\d{2})(\d{2}[A-F])号', txt)
            if short_seat_match:
                ticket_info["carriage"] = short_seat_match.group(1)
                ticket_info["seat_num"] = short_seat_match.group(2)
                continue
            # 074080号
            pure_num_match = re.fullmatch(r'(\d{6,8})号', txt)
            if pure_num_match:
                num_str = pure_num_match.group(1)
                if len(num_str) >= 4:
                    ticket_info["carriage"] = num_str[:2]
                    ticket_info["seat_num"] = num_str[2:]
                continue

            # 03车03A号
            combo_match = re.search(r'(\d+)车(\d+[A-F]?)号', txt)
            if combo_match:
                ticket_info["carriage"] = combo_match.group(1)
                ticket_info["seat_num"] = combo_match.group(2)
                continue

            # OCR错误规则：如 "03403A" → 假设格式为 XX?XXA（6字符，最后是字母）
            if len(txt) == 6 and txt[-1] in 'ABCDEF' and txt[:2].isdigit():
                # 尝试跳过第3位（常见OCR把"车"识别为数字）
                if txt[3:-1].isdigit():  # 如 '03A' 的前部分 '03'
                    ticket_info["carriage"] = txt[:2]
                    ticket_info["seat_num"] = txt[3:]
                    continue

            # 规则2: 泛化OCR错误格式，如 "03+12C号", "05#08A号", "12&01B号"
            ocr_match = re.search(r'(\d{1,2})[^\u4e00-\u9fa5\dA-Za-z]{1,3}?(\d{1,2}[A-F]?)号', txt)
            if ocr_match:
                ticket_info["carriage"] = ocr_match.group(1)
                ticket_info["seat_num"] = ocr_match.group(2)
                continue

            # 规则3: 单独匹配车厢（如 "03车"）
            if not ticket_info["carriage"]:
                carriage_match = re.search(r'(\d+)车', txt)
                if carriage_match:
                    ticket_info["carriage"] = carriage_match.group(1)

            # 规则4: 单独匹配座位（如 "12C号"）
            if not ticket_info["seat_num"]:
                seat_match = re.search(r'(\d+[A-F]?)号', txt)
                if seat_match:
                    ticket_info["seat_num"] = seat_match.group(1)

        # 5. 单独匹配车厢号（兼容只有车厢号的文本块）
        if not ticket_info["carriage"]:
            carriage_match = re.search(r'(\d+)车', txt)
            if carriage_match:
                ticket_info["carriage"] = carriage_match.group(1)
                continue

        # 新增：无座/站票 作为 seat_num（用于普速/无座票）
        if not ticket_info["seat_num"]:
            if txt.strip() in ("无座", "站票"):
                ticket_info["seat_num"] = txt.strip()
                continue

        # 6. 单独匹配座位号（兼容只有座位号的文本块）
        if not ticket_info["seat_num"]:
            # 修改座位号匹配，支持数字+字母的组合
            seat_match = re.search(r'(\d+[A-F]?)号', txt)
            if seat_match:
                ticket_info["seat_num"] = seat_match.group(1)
                continue

        # 7. 单独匹配铺位类型（兼容只有铺位类型的文本块）
        if not ticket_info["berth_type"]:
            # 支持空白变体匹配：上\s*铺 / 中\s*铺 / 下\s*铺
            m_berth = re.search(r'(上\s*铺|中\s*铺|下\s*铺)', txt)
            if m_berth:
                ticket_info["berth_type"] = re.sub(r'\s+', '', m_berth.group(1))
                logging.debug("ticket_parser.parse_ticket_info: single berth_type=%s from txt=%s", ticket_info["berth_type"], txt)
                # continue  <-- 移除continue，以便后续还能匹配 seat_type (如 "K154 | 硬卧中铺")

        # 8. 票价匹配（处理价格被分割的情况，如 ['￥443.', '5元']）
        if not ticket_info["price"]:
            s = txt.strip()
            
            # (0) 折扣块/价值积分块直接跳过
            # 如果含有"价值"，说明是积分价值而非票价
            if "价值" in s:
                pass
            elif _is_discount_block(s):
                pass
            else:
                # (1) 先尝试当前块单独取价（最优先）
                #     注意：只要命中了 ￥xx 或 xx元 就直接用，不做拼接
                single = s.replace("¥", "￥").replace(" ", "")
                m_single = re.search(r'￥(\d+(?:\.\d+)?)', single) or re.search(r'(\d+(?:\.\d+)?)元', single)
                if m_single:
                    ticket_info["price"] = m_single.group(1)
                else:
                    # (2) 再尝试跨块拼接：只允许拼接“价格碎片”，遇到折扣/非碎片立刻停止
                    price_related = ("￥" in s) or ("¥" in s) or ("元" in s)
                    if price_related and _is_price_fragment(s):
                        combined = single
                        # 最多向后拼 2 个块（你原来是 idx+3，这里保持同等强度）
                        for j in range(idx + 1, min(idx + 3, len(ocr_texts))):
                            nxt = ocr_texts[j].strip()
                            if not _is_price_fragment(nxt):
                                break
                            combined += nxt.replace("¥", "￥").replace(" ", "")

                            # 拼接后必须是“纯价格结构”才认
                            # 允许：￥443.5 / ￥443.5元 / 443.5元
                            m = re.fullmatch(r'￥?(\d+(?:\.\d+)?)元?', combined)
                            if m:
                                ticket_info["price"] = m.group(1)
                                break

                    # (3) 最后兜底：纯小数块可能是票价碎片，但要非常保守
                    #     仅当块本身像价格碎片（且不含折）才接受
                    if not ticket_info["price"]:
                        if _is_price_fragment(s) and ("元" in s or "￥" in s or "¥" in s):
                            m_num = re.search(r'(\d+(?:\.\d+)?)', s)
                            if m_num:
                                val = m_num.group(1)
                                try:
                                    num = float(val)
                                    if 5 <= num <= 3000:
                                        ticket_info["price"] = val
                                except ValueError:
                                    pass

        # 9. 座位类型匹配（如新车空调硬卧）
        if not ticket_info["seat_type"]:
            for seat_type in _SEAT_TYPE_KEYWORDS:
                if seat_type in txt:
                    ticket_info["seat_type"] = seat_type
                    break
            if ticket_info["seat_type"]:
                continue

        # 10. 优惠类型匹配（学生票/儿童票等）
        if not ticket_info["discount_type"]:
            # 扩展优惠类型关键词，包括"学惠"
            discount_types = ["学生票", "儿童票", "优惠票", "残疾军人票", "学惠", "学", "惠"]
            for discount in discount_types:
                if discount in txt:
                    ticket_info["discount_type"] = "学生票" if discount == "学惠" or discount == '学' or discount == '惠' else discount
                    break
            if ticket_info["discount_type"]:
                continue

        # 11. 姓名匹配 - 放在优惠类型之后，避免"学惠"被误识别为姓名
        if not ticket_info["name"]:
            # 主规则：匹配「6位地区码 + 8-10位（数字+*） + 4位校验码」后面的中文
            name_match = re.search(r'(\d{6})([\d\*]{8,10})([\dXx]{4})([\u4e00-\u9fa5]+)', txt)
            if name_match:
                ticket_info["name"] = name_match.group(4).strip()
                continue
            # 备用规则1：只要有15-17位（数字+*）+ 结尾（数字/X/x），后面的中文都算姓名
            backup_match1 = re.search(r'[\d\*]{15,17}[\dXx]([\u4e00-\u9fa5]+)', txt)
            if backup_match1:
                ticket_info["name"] = backup_match1.group(1).strip()
                continue
            # 备用规则2：匹配数字+空格+中文姓名的模式（如"5678 张三"）
            backup_match2 = re.search(r'\d+\s+([\u4e00-\u9fa5]{2,6})', txt)
            if backup_match2:
                ticket_info["name"] = backup_match2.group(1).strip()
                continue

            # 新增规则：掩码证件号与姓名粘连（如 '****8035xxx'）
            glued = _extract_tail_name_from_masked_id_block(txt)
            if glued:
                ticket_info["name"] = glued
                continue

            # A standalone Chinese word is not evidence of a passenger name.

    # 姓名增强纠正
    # 若当前 name 低置信，则尝试从证件号/掩码附近挑选姓名
    if _is_low_confidence_name(ticket_info.get("name", ""), station_name_set):
        better = _select_name_by_proximity(ocr_texts, station_name_set, ticket_info)
        if better:
            ticket_info["name"] = better
        else:
            # 若没有更可靠候选，则保持空（避免把站名/提示词当姓名）
            if _is_low_confidence_name(ticket_info.get("name", ""), station_name_set):
                ticket_info["name"] = ""

    _split_carriage_seat_if_glued(ticket_info)
    
    # Candidates were validated before selection, including credible new stations.

    # 再构建 station_name_set（保证包含最终的 dep/arr）
    station_name_set = set()
    for k in ("departure_station", "arrival_station"):
        v = (ticket_info.get(k) or "").strip()
        if v:
            station_name_set.add(v)
            station_name_set.add(v + "站")

    # 若姓名等于站名，直接清空（电子票里没有证件号时，宁可空也别错）
    if ticket_info.get("name") in station_name_set:
        ticket_info["name"] = ""

    # Explicit labels outrank guesses around identity-number fragments.
    for i, text in enumerate(ocr_texts):
        match = re.fullmatch(r'(?:乘车人|旅客姓名|姓名)[:：\s]*([\u4e00-\u9fa5]{2,6})?', text.strip())
        if not match:
            continue
        name = match.group(1) or ''
        if not name and i < len(polys):
            x, y = _poly_center(polys[i])
            nearby = []
            for j, (candidate, poly) in enumerate(zip(ocr_texts, polys)):
                xx, yy = _poly_center(poly)
                if j != i and _is_name_candidate_text(candidate, ticket_info, station_name_set):
                    if (abs(yy - y) <= 25 and 0 < xx - x < 240) or (abs(xx - x) < 80 and 0 < yy - y < 60):
                        nearby.append((abs(xx - x) + abs(yy - y), candidate))
            if nearby:
                name = min(nearby)[1]
        if _is_name_candidate_text(name, ticket_info, station_name_set):
            ticket_info['name'] = name
            break

    codes = candidate_train_codes(ocr_texts)
    if codes:
        ticket_info['train_code'] = resolve_train_code(ocr_texts, ticket_info['departure_station'], polys)
    damaged=[m for text in ocr_texts if (m:=re.fullmatch(r'([GDCKTZ])([0-9]{5})',text.strip()))]
    if len(damaged)==1 and not any(code[0] in 'GDCKTZ' for code in codes):
        match=damaged[0]
        ticket_info['train_code']=''
        ticket_info['train_code_raw']=match[0]
        ticket_info['train_code_candidates']=[match[1]+match[2][:-1],match[1]+match[2][1:]]

    logging.debug("ticket_parser.parse_ticket_info: parsed ticket_info=%s", ticket_info)
    from app.services.ticket_journey_parser import extract_journey_time
    ticket_info.update(extract_journey_time(ocr_texts, polys, ticket_info))
    return ticket_info


def parse_ticket_cards(texts, polys, initial=None):
    """Split a compact order list only when every resulting card is complete."""
    initial = parse_ticket_info(texts,polys) if initial is None else initial
    anchors=[]
    for text,poly in zip(texts,polys):
        codes=re.findall(r'(?<![A-Za-z0-9])[GDCKTZSNLYA]\d{1,4}(?![A-Za-z0-9])',normalize_ticket_text(text))
        if len(set(codes))==1 and len(poly)>=4:
            anchors.append((_poly_center(poly)[1],codes[0]))
    anchors.sort()
    if len(anchors)<2 or any(b[0]-a[0]<60 for a,b in zip(anchors,anchors[1:])):
        return [initial]
    boundaries=[(a[0]+b[0])/2 for a,b in zip(anchors,anchors[1:])]
    cards=[]
    for i,(_,code) in enumerate(anchors):
        lo=boundaries[i-1] if i else -float('inf')
        hi=boundaries[i] if i<len(boundaries) else float('inf')
        blocks=[(t,p) for t,p in zip(texts,polys) if lo<=_poly_center(p)[1]<hi]
        info=parse_ticket_info([t for t,p in blocks],[p for t,p in blocks])
        if (info.get('train_code')!=code or not all(info.get(k) for k in ('departure_station','arrival_station'))
                or not re.search(r'\d{1,2}月\d{1,2}日|\d{4}[-/]\d{1,2}[-/]\d{1,2}',info.get('datetime') or '')):
            return [initial]
        cards.append(info)
    return cards
