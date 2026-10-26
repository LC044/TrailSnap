import re
from datetime import datetime


class FlightTicketParser:
    def __init__(self):
        self.patterns = {

            'flight_code': re.compile(r'(?:^|[^A-Z0-9])([A-Z0-9]{2})\s*([0-9]{3,4})(?!\d)', re.IGNORECASE),

            # 日期时间: 支持多种格式
            # YYYY-MM-DD, YYYY/MM/DD, YYYY年MM月DD日, MM月DD日
            'date': re.compile(r'(?:(\d{4})[./年-])?(\d{1,2})[./月-](\d{1,2})日?'),
            # HH:MM
            'time': re.compile(r'([0-2]?\d)[:：]([0-5]\d)'),
            # 价格: 数字，可能包含小数点，可能带有 ¥, CNY 等符号
            'price': re.compile(r'(?:CNY|¥|￥)?\s*(\d+(?:\.\d{1,2})?)'),
            # 姓名: 2-4个汉字
            'name_cn': re.compile(r'[\u4e00-\u9fa5]{2,4}'),
            'city_arrow': re.compile(
                r'(?:(?:[0-9月日年\-\.]*\s*(?:周|星期)[一二三四五六日]\s*)|(?:(?<=[0-9])日\s*))?((?:(?!一)[\u4e00-\u9fa5]){2,5})\s*[-—>to一→]+\s*((?:(?!一)[\u4e00-\u9fa5]){2,5})',
                re.IGNORECASE)
        }

        # 关键词排除列表 (增强版)
        self.exclude_words = {
            '航空', '公司', '航班', '日期', '时间', '到达', '出发', '票价', '人民币',
            '电子', '客票', '行程', '单', '登机', '牌', '提示', '注意', '事项', '姓名',
            '旅客', '单程', '往返', '含税', '总价', '在线', '预订', '取消', '规则',
            '详情', '支付', '明细', '总计', '已出票', '机票', '筛选', '火车票', '汽车票',
            '保险', '燃油', '基建', '退改', '说明', '原订单', '改签', '申请', '订单',
            '机场', '收起', '状态', '完成', '更多', '分享', '添加', '日历', '我的',
            '退票', '出行信息', '电话', '客服', '投诉', '乘机人', '出行人', '展开',
            '直飞', '返程', '去程', '输入', '关键', '目的地', '点亮', '足迹', '地图',
            '海航', '北部湾', '值机', '柜台', '登机口', '暂无', '酒店', '接送机', '我要',
            '复制', '周一', '周二', '周三', '周四', '周五', '周六', '周日',
            '星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日',
            '小时', '分钟', '小时分', '时分', '月', '日', '月日', '年', '机场', '龙湾', 'T1', 'T2', 'T3', 'T4',
            '信息', '完整信息', '大安', '济宁', '兰州', '中川', '无餐食', '餐食', '显示',
            '国航', '苏南', '瑞丽', '苏南瑞丽', '待出行', '第程', '第1程', '第2程',
            '原订单', '订单', '单程', '往返', '多程', '上海广州', '东京上海', '转东京', '转西安',
            '美食券', '优惠券', '成人', '儿童', '婴儿', '经济舱', '商务舱', '头等舱', '正餐', '无餐',
            '全部', '处理中', '待支付', '已完成', '售后', '退改', '查看隐藏信息',
            '身份证', '票号', '联系电话', '凭证', '报销', '接送机', '订接送机',
            '行李', '行李额', '通知', '手气', '必读', '免单', '抽奖', '规定', '提醒', '东航'
        }

    def parse(self, text_list):
        """
        解析 OCR 文本列表，提取航班信息
        :param text_list: OCR 提取的文本行列表
        :return: 包含提取字段的字典
        """
        result = {
            'flight_code': None,
            'departure_city': None,
            'arrival_city': None,
            'datetime': None,
            'price': None,
            'name': None
        }

        full_text = " ".join(text_list)
        date_texts = [text for text in text_list
                      if not any(word in text for word in ('广告', '优惠', '活动', '当前时间'))]

        # 1. 提取航班号
        # 优先在列表中单独查找
        for text in text_list:
            match = self.patterns['flight_code'].search(text)
            if match:
                code = f"{match.group(1)}{match.group(2)}".upper()
                result['flight_code'] = code
                break

        # 2. 提取日期和时间
        date_str = None
        time_str = None

        # 策略2.1: 优先寻找 "日期+时间" 组合 (同一行)
        # 应对如 "2025-09-2713:25" 或 "2025-09-27 13:25"
        combined_dt_pattern = re.compile(r'(?:(\d{4})[./年-])?(\d{1,2})[./月-](\d{1,2})[日]?\s*([0-2]?\d[:：][0-5]\d)')

        for text in date_texts:
            match = combined_dt_pattern.search(text)
            if match:
                year = match.group(1)
                month = match.group(2)
                day = match.group(3)
                time_val = match.group(4)

                # 排除包含 "最晚", "预计", "截止" 等词的行，这些通常是出票时间而非航班时间
                if any(k in text for k in ['最晚', '预计', '截止', '完成', '订单']):
                    # 除非这行看起来非常像航班信息 (例如包含 "直飞", "航空" 等)，否则跳过
                    if not any(k in text for k in ['直飞', '航空', '舱', '飞', '到达', '出发']):
                        continue

                if not year:
                    year = str(datetime.now().year)
                    result['year_source'] = 'inferred_current_year'

                date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                time_str = time_val.replace('：', ':')
                # 规范化时间格式 HH:MM
                if ':' in time_str:
                    h, m = time_str.split(':')
                    time_str = f"{h.zfill(2)}:{m}"
                break

        # 策略2.2: 如果未找到组合，分别查找
        if not date_str or not time_str:
            for text in date_texts:
                if not date_str:
                    date_match = self.patterns['date'].search(text)
                    if date_match:
                        # 排除干扰行 (如同 combined_dt_pattern)
                        if any(k in text for k in ['最晚', '预计', '截止', '完成', '订单']):
                            if not any(k in text for k in ['直飞', '航空', '舱', '飞', '到达', '出发']):
                                continue

                        year = date_match.group(1)
                        month = date_match.group(2)
                        day = date_match.group(3)

                        if not year:
                            year = str(datetime.now().year)
                            result['year_source'] = 'inferred_current_year'

                        date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

                if date_str and not time_str:
                    # 排除可能是日期一部分的数字 (虽然 regex 已区分，但为了保险)
                    if self.patterns['date'].search(text) and not combined_dt_pattern.search(text):
                        # 如果这一行有日期但没有匹配到组合时间，不要在这里强行找时间（除非单独有时间）
                        pass

                    time_match = self.patterns['time'].search(text)
                    if time_match:
                        # 简单的过滤：如果是全图OCR，第一行往往是状态栏时间，需要谨慎
                        # 这里简单判定：如果时间出现在 "起飞" "出发" 等词所在的行，或者单独一行但不在开头？
                        # 暂时先接受第一个找到的时间，如果策略2.1没找到的话。
                        # 但为了避免状态栏时间 (如 15:27)，我们可以检查该行是否有 "起飞" "出发" "预计"
                        # 或者该行是否包含 "当前时间" 等干扰
                        # 这是一个 trade-off。
                        time_str = f"{time_match.group(1).zfill(2)}:{time_match.group(2)}"

        if date_str:
            result['datetime'] = f"{date_str} {time_str}" if time_str else date_str

        # 3. 提取价格
        for text in text_list:
            if self.patterns['date'].search(text) or self.patterns['flight_code'].search(text):
                continue

            if '票价' in text or 'CNY' in text or '¥' in text or '￥' in text:
                # 排除 "已省", "省钱" 等干扰
                if any(k in text for k in ['已省', '省钱', '优惠']):
                    continue

                match = self.patterns['price'].search(text)
                if match:
                    result['price'] = match.group(1)
                    break

        if not result['price']:
            for text in text_list:
                clean_t = text.strip()
                if len(clean_t) == 4 and (clean_t.startswith('202') or clean_t.startswith('201')):
                    continue
                if re.fullmatch(r'\d+(?:\.\d{1,2})?', clean_t):
                    val = float(clean_t)
                    if 100 < val < 20000:
                        result['price'] = clean_t
                        break

        # 4. 提取城市 (出发地 -> 目的地)
        city_found = False
        for text in text_list:
            match = self.patterns['city_arrow'].search(text)
            if match:
                dep = match.group(1)
                arr = match.group(2)

                if any(x in dep for x in ['周', '星期', '出发', '航空']) or any(
                        x in arr for x in ['周', '星期', '出发', '航空']):
                    continue

                # 排除包含日期的误匹配 (如 "2月9日")
                # 简单判断: 城市名不应包含 "月" 或 "日" (除非是特定城市如日月潭? 但通常机场城市名不含)
                # 考虑到 "日照", "乌鲁木齐" 等，不能简单排除 "日"
                # 但结合之前的 pattern，如果 "周" 在其中已经被排除

                result['departure_city'] = dep
                result['arrival_city'] = arr
                city_found = True
                break

        # 策略4.5: 尝试寻找连续两行疑似城市名 (针对OCR分行的情况)
        if not city_found:
            for i in range(len(text_list) - 1):
                t1 = text_list[i].strip()
                t2 = text_list[i + 1].strip()

                # 辅助函数: 检查是否为疑似城市
                def is_potential_city(s):
                    if s in self.exclude_words: return False
                    if not (2 <= len(s) <= 5): return False
                    if not re.fullmatch(r'[\u4e00-\u9fa5]+', s): return False
                    # 排除常见非城市词
                    if any(k in s for k in ['机票', '行程', '订单', '支付', '明细', '搜索', '通知', '手气', '必读', '免单', '抽奖', '规定', '提醒', '说明']): return False
                    return True

                # 逻辑调整：不需要t1和t2同时为真才进入检查，因为中间可能有符号
                
                # Case 1: City1 [Separator] City2
                if is_potential_city(t1):
                     if t2 in ["—", "-", "->", "to", "→"]:
                          if i + 2 < len(text_list):
                              t3 = text_list[i + 2].strip()
                              if is_potential_city(t3):
                                  result['departure_city'] = t1
                                  result['arrival_city'] = t3
                                  city_found = True
                                  break
                     elif is_potential_city(t2):
                         # Case 2: City1 City2 (Adjacent)
                         result['departure_city'] = t1
                         result['arrival_city'] = t2
                         city_found = True
                         break

        # 策略C: 如果没找到城市，尝试寻找 "XXX机场" 或 "XXXT1/2"
        if not city_found:
            airports = []
            for text in text_list:
                clean_t = text.strip()
                # 简单的机场匹配: 结尾是 机场 或 T1-4
                if re.search(r'[\u4e00-\u9fa5]{2,5}(?:机场|T[1-4])$', clean_t):
                    # 提取城市名部分 (去掉 机场 或 Txxx)
                    # 这里简单去除非汉字和 "机场"
                    city_name = re.sub(r'(?:机场|T[1-4]|[A-Za-z0-9])+$', '', clean_t)
                    if len(city_name) >= 2 and city_name not in self.exclude_words:
                        airports.append(city_name)

            # 如果找到至少两个不同的机场，假设前两个是出发和到达
            if len(airports) >= 2:
                # 简单去重保持顺序
                seen = set()
                unique_airports = []
                for a in airports:
                    if a not in seen:
                        unique_airports.append(a)
                        seen.add(a)

                if len(unique_airports) >= 2:
                    result['departure_city'] = unique_airports[0]
                    result['arrival_city'] = unique_airports[1]

        # 5. 提取姓名 (增加对 * 号的支持，如 "朱*燕")
        # 策略A: 优先寻找 "名字+成人" 格式
        for text in text_list:
            clean_text = text.strip()
            match_adult = re.search(r'([\u4e00-\u9fa5][\u4e00-\u9fa5*]{1,3})(?=\s*成人)', clean_text)
            if match_adult:
                val = match_adult.group(1)
                if val not in self.exclude_words and val != "乘机人":
                    result['name'] = val.strip()
                    return result

        # 策略A2: 优先寻找 "乘机人+名字" 格式 (单行)
        for i, text in enumerate(text_list):
            clean_text = text.strip()

            # 情况1: 同一行 "乘机人 张三"
            if clean_text.startswith(("乘机人", "旅客", "出行人", "联系人")):
                possible_name = re.sub(r'^(乘机人|旅客|出行人|联系人)', '', clean_text).strip()
                possible_name = re.sub(r'[0-9a-zA-Z\s,，.。-]', '', possible_name)

                if 2 <= len(possible_name) <= 4 and re.match(r'^[\u4e00-\u9fa5*]+$', possible_name):
                    if possible_name not in self.exclude_words:
                        result['name'] = possible_name
                        return result

            # 情况2: 分行 "乘机人" \n "张三"
            if clean_text in ["乘机人", "旅客", "出行人", "乘机人信息"] and i + 1 < len(text_list):
                next_text = text_list[i + 1].strip()
                next_text_clean = re.sub(r'[0-9a-zA-Z\s,，.。-]', '', next_text)
                if 2 <= len(next_text_clean) <= 4 and re.match(r'^[\u4e00-\u9fa5*]+$', next_text_clean):
                    if next_text_clean not in self.exclude_words:
                        result['name'] = next_text_clean
                        return result

        # 策略B: 遍历文本寻找疑似人名
        for text in text_list:
            text = text.strip()
            text = re.sub(r'[0-9a-zA-Z\s,，.。-]', '', text)

            if not text:
                continue

            if text in self.exclude_words:
                continue

            # Skip if matches city
            if result['departure_city'] and text == result['departure_city']:
                continue
            if result['arrival_city'] and text == result['arrival_city']:
                continue

            # Skip if starts with city name (likely airport name, e.g. 长春龙嘉, 广州白云)
            if result['departure_city'] and text.startswith(result['departure_city']):
                continue
            if result['arrival_city'] and text.startswith(result['arrival_city']):
                continue

            if 2 <= len(text) <= 4:
                if not re.search(r'[\u4e00-\u9fa5]', text):
                    continue
                if not re.match(r'^[\u4e00-\u9fa5*]+$', text):
                    continue
                if any(ew in text for ew in self.exclude_words):
                    continue

                result['name'] = text
                break

        return result


def extract_flight_info(text_list):
    parser = FlightTicketParser()
    return parser.parse(text_list)
