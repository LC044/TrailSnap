#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/12/10 22:26
@Author      : SiYuan
@Email       : sixyuan044@gmail.com
@File        : server-filename.py
@Description : 
"""

import re
import traceback
from datetime import datetime

start_time = datetime(1990, 1, 1, 0, 0, 0)
end_time = datetime(2045, 1, 1, 0, 0, 0)


def is_within_range(dt, start, end):
    """
    检查给定时间是否在指定范围内
    :param dt: 要检查的时间 (datetime 对象)
    :param start: 范围起始时间 (datetime 对象)
    :param end: 范围结束时间 (datetime 对象)
    :return: 布尔值，True 表示在范围内，False 表示不在范围内
    """
    return start <= dt <= end


def valid_time(dt):
    if start_time <= dt <= datetime.now():
        return dt
    else:
        return None


def contains_uuid_or_hash(filename: str) -> bool:
    """检测文件名是否包含UUID/哈希特征（非时间相关）"""
    # 1. 检测UUID（含标准格式和无分隔符的UUID）
    uuid_patterns = [
        r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',  # 标准UUID
        r'[0-9a-fA-F]{32}',  # MD5/无分隔符UUID
        r'[0-9a-fA-F]{40}',  # SHA1
        r'[0-9a-fA-F]{64}',  # SHA256
    ]
    for pat in uuid_patterns:
        if re.search(pat, filename, re.IGNORECASE):
            return True
    
    # 2. 检测过长的纯数字串（非10/13位，且无日期分隔符）
    # 匹配14位以上的孤立数字串（排除YYYYMMDDHHMMSS的14位）
    long_num_pattern = r'(?<!\d)(\d{15,})(?!\d)'
    if re.search(long_num_pattern, filename):
        return True
    
    return False

def is_valid_timestamp(timestamp: str, filename: str) -> datetime | None:
    """
    严格验证时间戳有效性：
    1. 仅处理10位（秒）/13位（毫秒）数字
    2. 验证时间戳是否在1990-2040范围内
    """
    if contains_uuid_or_hash(filename):
        return None
    try:
        ts_len = len(timestamp)
        if ts_len == 10:
            result = datetime.fromtimestamp(int(timestamp))  # 转换为秒
        elif ts_len == 13:
            result = datetime.fromtimestamp(int(timestamp) / 1000)  # 转换为秒
        else:
            return None
        return valid_time(result)
    except (ValueError, OverflowError):
        return None

def _extract_datetime_from_filename(filename)-> datetime | None:
    # 定义正则表达式，匹配常见的时间格式
    patterns = [
        r"(\d{4})[ _\.-](\d{2})[ _\.-](\d{2})[ _\.-](\d{2})[ _\.-](\d{2})[ _\.-](\d{2})",  # 格式：YYYY_MM_DD_HH-MM-SS
        r"(\d{4})[ _\.-](\d{2})[ _\.-](\d{2})[ _\.-](\d{6})",  # 格式：YYYY-MM-DD_HHMMSS YYYY-MM-DD HHMMSS
        r"(\d{2})[ _\.-](\d{2})[ _\.-](\d{4})[ _\.-](\d{6})",  # 格式：DD-MM-YYYY_HHMMSS
        r"(\d{8})[ _\.-](\d{2})[ _\.-](\d{2})[ _\.-](\d{2})",  # 格式：YYYYMMDD_HH-MM-SS
        r"(\d{8})[ _T\.-](\d{6})",  # 格式：YYYYMMDD_HHMMSS
        r"(\d{14})",  # 格式：YYYYMMDDHHMMSS
        r"(?<!\d)((?:19|20)\d{2})[ _\.-](\d{1,2})[ _\.-](\d{1,2})(?!\d)",  # 格式：YYYY-MM-DD / YYYY.M.D
        r"(?<!\d)((?:19|20)\d{2})([01]\d)([0-3]\d)(?!\d)",  # 格式：YYYYMMDD
        r"(\d{13}|\d{10})",  # 格式：TIMESTAMP (13位毫秒级时间戳)
    ]
    try:
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                # 根据匹配的模式提取日期和时间
                if len(match.groups()) == 2:  # 格式：YYYYMMDD_HHMMSS
                    date_str = match.group(1)
                    time_str = match.group(2)
                    dt = datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H%M%S")
                    return dt
                elif len(match.groups()) == 1:  # 格式：TIMESTAMP
                    timestamp = match.group(1)
                    if len(timestamp) == 14:
                        datetime_str = match.group(1)
                        dt = datetime.strptime(datetime_str, "%Y%m%d%H%M%S")
                        return dt
                    else:
                        return is_valid_timestamp(timestamp, filename)
                elif len(match.groups()) == 3:  # 格式：YYYY-MM-DD / YYYYMMDD
                    year, month, day = match.groups()
                    dt = datetime(int(year), int(month), int(day))
                    return dt
                elif len(match.groups()) == 4:  # 格式：YYYY-MM-DD HHMMSS
                    year, month, day, time_str = match.groups()
                    if len(year) == 4:
                        # 格式：YYYY-MM-DD_HHMMSS YYYY-MM-DD HHMMSS
                        dt = datetime.strptime(f"{year}-{month}-{day} {time_str}", "%Y-%m-%d %H%M%S")
                    elif len(year) == 8:
                        # 格式：YYYYMMDD_HH-MM-SS
                        dt = datetime.strptime(f"{year} {month}-{day}-{time_str}", "%Y%m%d %H-%-M-%S")
                    else:
                        # DD-MM-YYYY_HHMMSS
                        dt = datetime.strptime(f"{year}-{month}-{day} {time_str}", "%m-%d-%Y %H%M%S")
                    return dt
                elif len(match.groups()) == 6:  # 格式：YYYY_MM_DD_HH-MM-SS
                    year, month, day, hour, minute, second = match.groups()
                    dt = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
                    return dt
        return None  # 如果没有匹配到任何模式，返回 None
    except:
        return None  # 如果没有匹配到任何模式，返回 None


def extract_datetime_from_filename(filename) -> datetime | None:
    file_time = _extract_datetime_from_filename(filename)
    if file_time and is_within_range(file_time, start_time, end_time):
        return file_time
    return None

if __name__ == "__main__":
    test_filenames = [
        "video_2023-10-15_14-30-00.mp4",
        "image_20231015_143000.jpg",
        "snapshot_15-10-2023_143000.png",
        "recording_20231015-143000.avi",
        "photo_20231015143000.jpeg",
        "log_1697365800000.txt",  # 13位时间戳
        "data_1697365800.csv",    # 10位时间戳
        "invalid_9999999999999.txt",  # 超出范围的时间戳
        "corrupt_file_name.txt",   # 无时间信息
        "4d8556446a26ba09225472152f9a35e2.mp4",
        "qxlarge-dsc-11EB02359837030BCECC2CD10B0227EF.jpg",
        "IMG_20230505_161512_122_01683274513117.webp",
        "Image_175817265083468.png",
        "share_132748871793053520.png",
        "IMG_20220821_121750_866_01661055471248.jpeg"
    ]

    for filename in test_filenames:
        dt = extract_datetime_from_filename(filename)
        print(f"Filename: {filename} -> Extracted Datetime: {dt}")
