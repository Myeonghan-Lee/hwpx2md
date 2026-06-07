"""
hwpx_converter.py
HWPX → Markdown 변환 엔진 (병합 셀 자동 채우기 완벽 지원 버전)
"""

import zipfile
import io
import os
import re
import datetime
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


@dataclass
class ConvertResult:
    filename: str
    success: bool
    markdown: str = ""
    images: Dict[str, bytes] = field(default_factory=dict)
    error: str = ""


class HwpxToMarkdown:
    KNOWN_NAMESPACES = [
        "http://www.hancom.co.kr/hwpml/2011/paragraph",
        "http://www.hancom.co.kr/hwpml/2011/core",
        "http://www.hancom.co.kr/hwpml/2011/head",
        "http://www.hancom.co.kr/hwpml/2011/table",
        "http://www.hancom.co.kr/hwpml/2011/master-page",
        "urn:oasis:names:tc:opendocument:xmlns:container",
        "http://www.hancom.co.kr/hwpml/2016/paragraph",
        "http://www.hancom.co.kr/hwpml/2016/core",
        "http://www.hancom.co.kr/hwpml/2016/head",
        "http://www.hancom.co.kr/hwpml/2016/table",
    ]

    def __init__(self):
        self.ns = {}           
        self.style_map = {}    
        self.heading_ids = {}  

    # ─────────────── 공개 API ───────────────

    def convert_bytes(self, data: bytes, filename: str = "document") -> ConvertResult:
        try:
            buf = io.BytesIO(data)
            if not zipfile.is_zipfile(buf):
                return ConvertResult(filename=filename, success=False, error="유효한 HWPX(ZIP) 파일이 아닙니다.")
            buf.seek(0)
            with zipfile.ZipFile(buf, 'r') as zf:
                return self._process_zip(zf, filename)
        except Exception as e:
            return ConvertResult(filename=filename, success=False, error=str(e))

    def convert_file(self, filepath: str) -> ConvertResult:
        filename = os.path.basename(filepath)
        with open(filepath, 'rb') as f:
            return self.convert_bytes(f.read(), filename)

    # ─────────────── 내부 처리 ───────────────

    def _process_zip(self, zf: zipfile.ZipFile, filename: str) -> ConvertResult:
        file_list = zf.namelist()
        self.ns = self._detect_namespaces(zf, file_list)
        self._load_styles(zf, file_list)

        section_files = sorted([f for f in file_list if re.search(r'section\d*\.xml$', f, re.IGNORECASE)])

        md_parts = []
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        frontmatter = f"---\nsource_file: '{filename}'\nconverted_at: '{current_time}'\n---\n"
        md_parts.append(frontmatter)

        for sf in section_files:
            xml_bytes = zf.read(sf)
            md_parts.append(self._parse_section(xml_bytes))

        images = self._extract_images(zf, file_list)

        markdown = "\n\n".join(p for p in md_parts if p.strip())
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        markdown = re.sub(r'([^\n])\n(#+ )', r'\1\n\n\2', markdown).strip()

        return ConvertResult(filename=filename, success=True, markdown=markdown, images=images)

    # ─────────────── 네임스페이스 및 스타일 ───────────────

    def _detect_namespaces(self, zf, file_list) -> dict:
        ns = {}
        sample_files = [f for f in file_list if 'section' in f.lower() and f.endswith('.xml')]
        if not sample_files: return ns
        try:
            content = zf.read(sample_files[0]).decode('utf-8')
            for match in re.finditer(r'xmlns:(\w+)="([^"]+)"', content):
                prefix, uri = match.group(1), match.group(2)
                ns[prefix] = uri
        except:
            pass
        return ns

    def _load_styles(self, zf, file_list):
        self.style_map = {}
        self.heading_ids = {}
        header_files = [f for f in file_list if 'header.xml' in f.lower()]
        if not header_files: return
        try:
            xml_bytes = zf.read(header_files[0])
            root = ET.fromstring(xml_bytes)
            for elem in root.iter():
                tag = self._local_tag(elem.tag)
                if tag == 'style':
                    style_id = elem.get('id', '')
                    style_name = elem.get('name', elem.get('engName', ''))
                    if style_id: self.style_map[style_id] = style_name
                    name_lower = style_name.lower()
                    if '개요' in name_lower or 'outline' in name_lower or '제목' in name_lower or 'heading' in name_lower:
                        level = self._extract_level(style_name, style_id)
                        if level: self.heading_ids[style_id] = level
        except:
            pass

    def _extract_level(self, name: str, style_id: str) -> Optional[int]:
        m = re.search(r'(\d+)', name)
        if m: return min(int(m.group(1)), 6)
        m = re.search(r'(\d+)', style_id)
        if m: return min(int(m.group(1)), 6)
        return 1

    # ─────────────── 섹션 및 문단 파싱 ───────────────

    def _parse_section(self, xml_bytes: bytes) -> str:
        root = ET.fromstring(xml_bytes)
        lines = []
        self._walk_elements(root, lines)
        return "\n".join(lines)

    def _walk_elements(self, elem, lines: list):
        tag = self._local_tag(elem.tag)

        if tag in ('table', 'tbl'):
            lines.append(self._parse_table(elem))
            return

        if tag == 'p':
            self._parse_paragraph_and_tables(elem, lines, in_cell=False)
            return

        for child in elem:
            self._walk_elements(child, lines)

    def _parse_paragraph_and_tables(self, p_elem, lines: list, in_cell: bool):
        heading_level = 0 if in_cell else self._get_heading_level(p_elem)
        current_texts = []
        
        def flush_text():
            text = "".join(current_texts).strip()
            if text:
                if heading_level and heading_level > 0:
                    text = f"{'#' * heading_level} {text}"
                if in_cell:
                    text = text.replace("|", r"\|")
                lines.append(text)
            current_texts.clear()

        for run_elem in p_elem:
            tag = self._local_tag(run_elem.tag)
            
            if tag == 'run':
                run_text, run_tables = self._extract_run_and_tables(run_elem)
                if run_text:
                    current_texts.append(run_text)
                
                if run_tables:
                    flush_text()
                    for t in run_tables:
                        if in_cell:
                            lines.append(self._parse_nested_table(t))
                        else:
                            lines.append(self._parse_table(t))
            elif tag in ('table', 'tbl'):
                flush_text()
                if in_cell:
                    lines.append(self._parse_nested_table(run_elem))
                else:
                    lines.append(self._parse_table(run_elem))
            else:
                pass
        
        flush_text()

    def _extract_run_and_tables(self, run_elem) -> Tuple[str, List[ET.Element]]:
        texts = []
        tables = []
        
        def walk_run(el):
            tag = self._local_tag(el.tag)
            if tag in ('table', 'tbl'):
                tables.append(el)
                return 
            if tag == 't' and el.text:
                texts.append(el.text)
            elif tag == 'tab':
                texts.append("    ")
            elif tag in ('lineBreak', 'softHyphen'):
                texts.append("  \n")
            for child in el:
                walk_run(child)
        
        for child in run_elem:
            walk_run(child)
            
        text = "".join(texts)
        if not text.strip():
            return text, tables
            
        text = text.replace("~", r"\~")
        
        bold = italic = strike = sup = sub = False
        for elem in run_elem:
            tag = self._local_tag(elem.tag)
            if tag in ('charPr', 'rPr', 'rPrChange'):
                bold = bold or elem.get('bold', '').lower() in ('true', '1')
                italic = italic or elem.get('italic', '').lower() in ('true', '1')
                strike = strike or elem.get('strikeout', elem.get('strikethrough', '')).lower() in ('true', '1')
                sup = sup or elem.get('superscript', '').lower() in ('true', '1')
                sub = sub or elem.get('subscript', '').lower() in ('true', '1')
        
        stripped = text.strip()
        leading = text[:len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]

        if strike: stripped = f"<del>{stripped}</del>"
        if bold and italic: stripped = f"***{stripped}***"
        elif bold: stripped = f"**{stripped}**"
        elif italic: stripped = f"*{stripped}*"
        if sup: stripped = f"<sup>{stripped}</sup>"
        if sub: stripped = f"<sub>{stripped}</sub>"
        
        return leading + stripped + trailing, tables

    def _get_heading_level(self, p_elem) -> int:
        for attr_name in p_elem.attrib:
            local = self._local_tag(attr_name)
            if local in ('styleIDRef', 'paraPrIDRef', 'style'):
                val = p_elem.get(attr_name)
                if val in self.heading_ids: return self.heading_ids[val]
        for elem in p_elem.iter():
            tag = self._local_tag(elem.tag)
            if tag in ('paraPr', 'pPr'):
                style_ref = elem.get('styleIDRef', elem.get('style', ''))
                if style_ref in self.heading_ids: return self.heading_ids[style_ref]
                outline = elem.get('outlineLevel', elem.get('level', ''))
                if outline and outline.isdigit():
                    level = int(outline)
                    if 1 <= level <= 6: return level
        return 0

    # ─────────────── 병합 정보 추출 유틸리티 ───────────────

    def _get_span_values(self, tc_elem) -> Tuple[int, int]:
        """HWPX의 복잡한 구조(<cellAddr> 등)를 뚫고 정확한 병합 행/열 개수를 추출"""
        rowspan, colspan = 1, 1
        
        # 1. tc 태그 자체 속성 검사
        for k, v in tc_elem.attrib.items():
            if k.lower().endswith('rowspan'): rowspan = max(1, int(v))
            elif k.lower().endswith('colspan'): colspan = max(1, int(v))
            
        # 2. tc의 하위 태그(주로 <hc:cellAddr>) 속성 정밀 검사
        for child in tc_elem:
            for k, v in child.attrib.items():
                if k.lower().endswith('rowspan'): rowspan = max(1, int(v))
                elif k.lower().endswith('colspan'): colspan = max(1, int(v))
                
        return rowspan, colspan

    # ─────────────── 테이블 파싱 (행/열 병합 셀 반복 채우기) ───────────────

    def _parse_table(self, table_elem) -> str:
        """최상위 표를 Markdown 문법으로 변환 (병합된 셀 내용 자동 반복)"""
        rows = []
        active_spans = {}  # 병합 정보 기억 딕셔너리

        for tr_elem in table_elem:
            tag = self._local_tag(tr_elem.tag)
            if tag != 'tr': continue

            current_row = []
            col_idx = 0
            
            tc_elems = [e for e in tr_elem if self._local_tag(e.tag) == 'tc']
            tc_iter = iter(tc_elems)
            tc_elem = next(tc_iter, None)

            while True:
                # 1. 윗줄에서 병합(rowspan)되어 내려온 데이터가 있다면 먼저 채움
                while col_idx in active_spans and active_spans[col_idx]["count"] > 0:
                    current_row.append(active_spans[col_idx]["text"])
                    active_spans[col_idx]["count"] -= 1
                    if active_spans[col_idx]["count"] == 0:
                        del active_spans[col_idx]
                    col_idx += 1

                # 2. 이번 줄에서 더 이상 읽을 셀이 없을 때의 종료 조건
                if tc_elem is None:
                    max_active_col = max(active_spans.keys()) if active_spans else -1
                    if col_idx > max_active_col:
                        break
                    else:
                        # 병합 셀이 뒤에 남아있는데 중간 셀이 누락된 경우(HWP 특수오류 방어) 공백 삽입
                        if col_idx not in active_spans:
                            current_row.append("")
                            col_idx += 1
                        continue

                # 3. 새로운 셀 데이터 및 병합 정보 추출
                cell_text = self._extract_cell_text(tc_elem)
                rowspan, colspan = self._get_span_values(tc_elem)

                # 4. 열 병합(colspan)만큼 가로로 복제 & 행 병합(rowspan) 아래로 예약
                for _ in range(colspan):
                    current_row.append(cell_text)
                    if rowspan > 1:
                        active_spans[col_idx] = {"text": cell_text, "count": rowspan - 1}
                    col_idx += 1

                tc_elem = next(tc_iter, None)

            if current_row:
                rows.append(current_row)

        if not rows:
            return ""

        max_cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < max_cols:
                r.append("")

        lines = []
        header = "| " + " | ".join(rows[0]) + " |"
        separator = "| " + " | ".join(["---"] * max_cols) + " |"
        lines.append(header)
        lines.append(separator)

        for row in rows[1:]:
            line = "| " + " | ".join(row) + " |"
            lines.append(line)

        return "\n\n" + "\n".join(lines) + "\n\n"

    def _parse_nested_table(self, table_elem) -> str:
        """표 안의 표(Nested Table)를 HTML <table> 태그로 변환"""
        html_parts = ["<table border='1'>"]
        for elem in table_elem:
            tag = self._local_tag(elem.tag)
            if tag == 'tr':
                html_parts.append("<tr>")
                for cell_elem in elem:
                    cell_tag = self._local_tag(cell_elem.tag)
                    if cell_tag == 'tc':
                        cell_text = self._extract_cell_text(cell_elem)
                        rowspan, colspan = self._get_span_values(cell_elem)
                        
                        attrs = ""
                        if rowspan > 1: attrs += f" rowspan='{rowspan}'"
                        if colspan > 1: attrs += f" colspan='{colspan}'"
                        
                        html_parts.append(f"<td{attrs}>{cell_text}</td>")
                html_parts.append("</tr>")
        html_parts.append("</table>")
        return "".join(html_parts)

    def _extract_cell_text(self, cell_elem) -> str:
        parts = []
        def walk(el):
            tag = self._local_tag(el.tag)
            if tag == 'p':
                p_lines = []
                self._parse_paragraph_and_tables(el, p_lines, in_cell=True)
                joined = "<br>".join(p_lines)
                if joined.strip():
                    parts.append(joined.strip())
                return
            elif tag in ('tbl', 'table'):
                html_table = self._parse_nested_table(el)
                parts.append(html_table)
                return
            for child in el:
                walk(child)
        walk(cell_elem)
        return "<br>".join(parts)

    # ─────────────── 이미지 및 유틸리티 ───────────────

    def _extract_images(self, zf, file_list) -> Dict[str, bytes]:
        images = {}
        img_exts = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.tif', '.tiff')
        for f in file_list:
            if any(f.lower().endswith(ext) for ext in img_exts):
                try:
                    images[os.path.basename(f)] = zf.read(f)
                except:
                    pass
        return images

    @staticmethod
    def _local_tag(tag: str) -> str:
        if '}' in tag:
            return tag.split('}', 1)[1]
        return tag

# ─────────────── 편의 함수 ───────────────

def convert_hwpx_to_md(data: bytes, filename: str = "document") -> ConvertResult:
    converter = HwpxToMarkdown()
    return converter.convert_bytes(data, filename)
