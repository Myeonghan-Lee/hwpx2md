"""
hwpx_converter.py
HWPX → Markdown 변환 엔진 (단락 내장 표 완벽 분리 및 중첩 표 지원 버전)
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

        # 독립된 표 감지
        if tag in ('table', 'tbl'):
            lines.append(self._parse_table(elem))
            return

        # 문단 내부 감지 (내부에 표가 섞여있을 수 있음)
        if tag == 'p':
            self._parse_paragraph_and_tables(elem, lines, in_cell=False)
            return

        for child in elem:
            self._walk_elements(child, lines)

    def _parse_paragraph_and_tables(self, p_elem, lines: list, in_cell: bool):
        """문단을 파싱하되, 내부에 표가 있으면 텍스트를 끊고 표를 별도로 추출"""
        heading_level = self._get_heading_level(p_elem)
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

        # 문단 내부의 run과 table을 순차적으로 탐색
        for run_elem in p_elem:
            tag = self._local_tag(run_elem.tag)
            
            if tag == 'run':
                run_text, run_tables = self._extract_run_and_tables(run_elem)
                if run_text:
                    current_texts.append(run_text)
                
                # run 내부에 표가 숨어있다면 텍스트를 비우고 표를 삽입
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
        """<run> 태그 내의 텍스트와 숨겨진 표를 분리하여 반환"""
        texts = []
        tables = []
        
        def walk_run(el):
            tag = self._local_tag(el.tag)
            
            # 표를 만나면 텍스트 추출을 중단하고 테이블 리스트에 담음
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
            
        # ~ 기호 이스케이프 (취소선 방어)
        text = text.replace("~", r"\~")
        
        # 서식 추출
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

    # ─────────────── 테이블 파싱 (바깥 표 & 중첩 표) ───────────────

    def _parse_table(self, table_elem) -> str:
        """최상위 표를 Markdown 문법으로 변환"""
        rows = []
        for elem in table_elem:
            tag = self._local_tag(elem.tag)
            if tag == 'tr':
                cells = []
                for cell_elem in elem:
                    cell_tag = self._local_tag(cell_elem.tag)
                    if cell_tag == 'tc':
                        cells.append(self._extract_cell_text(cell_elem))
                if cells:
                    rows.append(cells)

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
        """표 안의 표(Nested Table)를 HTML <table> 태그로 안전하게 변환"""
        html_parts = ["<table border='1'>"]
        for elem in table_elem:
            tag = self._local_tag(elem.tag)
            if tag == 'tr':
                html_parts.append("<tr>")
                for cell_elem in elem:
                    cell_tag = self._local_tag(cell_elem.tag)
                    if cell_tag == 'tc':
                        cell_text = self._extract_cell_text(cell_elem)
                        rowspan = cell_elem.get('rowSpan', cell_elem.get('rowspan', '1'))
                        colspan = cell_elem.get('colSpan', cell_elem.get('colspan', '1'))
                        
                        attrs = ""
                        if rowspan and rowspan != '1': attrs += f" rowspan='{rowspan}'"
                        if colspan and colspan != '1': attrs += f" colspan='{colspan}'"
                        
                        html_parts.append(f"<td{attrs}>{cell_text}</td>")
                html_parts.append("</tr>")
        html_parts.append("</table>")
        return "".join(html_parts)

    def _extract_cell_text(self, cell_elem) -> str:
        """셀 내부 텍스트 추출"""
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
