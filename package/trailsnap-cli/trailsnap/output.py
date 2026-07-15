import json
import csv
import io
import sys
from typing import Any, List, Dict, Optional


class OutputFormatter:
    """统一输出格式化器，支持多种输出格式"""

    FORMAT_JSON = "json"
    FORMAT_PRETTY = "pretty"
    FORMAT_TABLE = "table"
    FORMAT_NDJSON = "ndjson"
    FORMAT_CSV = "csv"

    SUPPORTED_FORMATS = [FORMAT_JSON, FORMAT_PRETTY, FORMAT_TABLE, FORMAT_NDJSON, FORMAT_CSV]

    def __init__(self, format: str = FORMAT_JSON):
        self.format = format

    def output(self, data: Any, fields: Optional[List[str]] = None, headers: Optional[Dict[str, str]] = None):
        """根据格式输出数据"""
        if data is None:
            print("无数据")
            return

        if self.format == self.FORMAT_JSON:
            self._output_json(data)
        elif self.format == self.FORMAT_PRETTY:
            self._output_pretty(data)
        elif self.format == self.FORMAT_TABLE:
            self._output_table(data, fields, headers)
        elif self.format == self.FORMAT_NDJSON:
            self._output_ndjson(data)
        elif self.format == self.FORMAT_CSV:
            self._output_csv(data, fields, headers)
        else:
            self._output_json(data)

    def _output_json(self, data: Any):
        """输出标准 JSON"""
        print(json.dumps(data, indent=2, ensure_ascii=False))

    def _output_pretty(self, data: Any):
        """输出人性化的格式化数据"""
        if isinstance(data, list):
            for i, item in enumerate(data):
                print(f"--- [{i + 1}] ---")
                self._print_dict(item)
                print()
        elif isinstance(data, dict):
            self._print_dict(data)
        else:
            print(data)

    def _print_dict(self, d: Dict, indent: int = 0):
        """递归打印字典"""
        for key, value in d.items():
            if isinstance(value, dict):
                print(f"{'  ' * indent}{key}:")
                self._print_dict(value, indent + 1)
            elif isinstance(value, list):
                print(f"{'  ' * indent}{key}: [{len(value)} items]")
                for i, item in enumerate(value[:5]):
                    if isinstance(item, dict):
                        self._print_dict(item, indent + 1)
                    else:
                        print(f"{'  ' * (indent + 1)}- {item}")
                    if i >= 4 and len(value) > 5:
                        print(f"{'  ' * (indent + 1)}... and {len(value) - 5} more")
                        break
            else:
                print(f"{'  ' * indent}{key}: {value}")

    def _output_table(self, data: Any, fields: Optional[List[str]] = None, headers: Optional[Dict[str, str]] = None):
        """输出表格格式"""
        import unicodedata
        import shutil

        def display_width(s: str) -> int:
            return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in str(s))

        def ljust_wide(s: str, width: int) -> str:
            w = display_width(s)
            return str(s) + ' ' * max(0, width - w)

        def truncate_wide(s: str, width: int) -> str:
            s = str(s)
            if display_width(s) <= width:
                return s
            if width <= 3:
                return "." * width
            res = ""
            current_w = 0
            for c in s:
                cw = 2 if unicodedata.east_asian_width(c) in 'WF' else 1
                if current_w + cw > width - 3: # reserve 3 for '...'
                    break
                res += c
                current_w += cw
            return res + "..."

        if not isinstance(data, list):
            data = [data]

        if not data:
            print("无数据")
            return

        # 如果没有指定 fields，尝试从第一条数据中提取
        if fields is None:
            if isinstance(data[0], dict):
                fields = list(data[0].keys())
            else:
                fields = ["value"]

        # 如果没有指定 headers，使用字段名作为标题
        if headers is None:
            headers = {f: f for f in fields}

        # 计算每列的需要宽度
        col_widths = {}
        for field in fields:
            header = headers.get(field, field)
            col_widths[field] = display_width(header)

        for row in data:
            if isinstance(row, dict):
                for field in fields:
                    value = row.get(field, "")
                    col_widths[field] = max(col_widths[field], display_width(str(value)))

        # 列宽跟随终端
        term_width = shutil.get_terminal_size((80, 20)).columns
        separator_width = len(fields) * 3 - 1
        total_content_width = sum(col_widths.values())
        
        if total_content_width + separator_width > term_width:
            # 需要截断
            avail_width = term_width - separator_width
            avg_width = avail_width // len(fields)
            
            # 重新分配宽度
            for field in fields:
                if col_widths[field] > avg_width:
                    col_widths[field] = avg_width

        # 输出表头
        header_line = " | ".join(ljust_wide(truncate_wide(headers.get(f, f), col_widths[f]), col_widths[f]) for f in fields)
        print(header_line)
        print("-+-".join("-" * col_widths[f] for f in fields))

        # 输出数据行
        for row in data:
            if isinstance(row, dict):
                row_line = " | ".join(ljust_wide(truncate_wide(str(row.get(f, "")), col_widths[f]), col_widths[f]) for f in fields)
                print(row_line)
            else:
                print(str(row))

    def _output_ndjson(self, data: Any):
        """输出换行分隔的 JSON (Newline-Delimited JSON)"""
        if isinstance(data, list):
            for item in data:
                print(json.dumps(item, ensure_ascii=False))
        else:
            print(json.dumps(data, ensure_ascii=False))

    def _output_csv(self, data: Any, fields: Optional[List[str]] = None, headers: Optional[Dict[str, str]] = None):
        """输出 CSV 格式"""
        if not isinstance(data, list):
            data = [data]

        if not data:
            print("无数据")
            return

        # 如果没有指定 fields，尝试从第一条数据中提取
        if fields is None:
            if isinstance(data[0], dict):
                fields = list(data[0].keys())
            else:
                fields = ["value"]

        # 如果没有指定 headers，使用字段名作为标题
        if headers is None:
            headers = {f: f for f in fields}

        output = io.StringIO()
        writer = csv.writer(output)

        # 写入表头
        writer.writerow([headers.get(f, f) for f in fields])

        # 写入数据行
        for row in data:
            if isinstance(row, dict):
                writer.writerow([row.get(f, "") for f in fields])
            else:
                writer.writerow([row])

        print(output.getvalue().strip())


# 全局输出格式化器实例
_formatter: Optional[OutputFormatter] = None


def get_formatter() -> OutputFormatter:
    """获取全局输出格式化器实例"""
    global _formatter
    if _formatter is None:
        _formatter = OutputFormatter()
    return _formatter


def set_formatter(format: str):
    """设置全局输出格式化器的格式"""
    global _formatter
    if not format:
        format = "json"
    get_formatter().format = format


def output(data: Any, fields: Optional[List[str]] = None, headers: Optional[Dict[str, str]] = None):
    """使用全局格式化器输出数据"""
    get_formatter().output(data, fields, headers)


def output_error(message: str):
    """输出错误信息"""
    print(f"错误: {message}", file=sys.stderr)


def output_success(message: str):
    """输出成功信息"""
    print(message)
