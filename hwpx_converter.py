"""
hwpx_converter.py
HWPX → Markdown 변환 엔진 (데이터 분석 최적화 버전)
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
    """변환 결과 데이터 클래스"""
    filename: str
    success: bool
    markdown: str = ""
    images: Dict[str, bytes] = field(default_factory=dict)
    error: str = ""


class HwpxToMarkdown:
    """HWPX 파일을 Markdown으로 변환하는 엔진"""

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
        """바이트 데이터를 받아 Markdown으로 변환"""
        try:
            buf = io.BytesIO(data)
            if not zipfile.is_zipfile(buf):
                return ConvertResult(filename=filename, success=False,
                                     error="유효한 HWPX(ZIP) 파일이 아닙니다.")
            buf.seek(0)
            with zipfile.ZipFile(buf, 'r') as zf:
                return self._process_zip(zf, filename)
        except Exception as e:
            return ConvertResult(filename=filename, success=False, error=str(e))

    def convert_file(self, filepath: str) -> ConvertResult:
        """파일 경로를 받아 Markdown으로 변환"""
        filename = os.path.basename(filepath)
        with open(filepath, 'rb') as f:
            return self.convert_bytes(f.read(), filename)

    # ─────────────── 내부 처리 ───────────────

    def _process_zip(self, zf: zipfile.ZipFile, filename: str) -> ConvertResult:
        """ZIP 내부 구조 탐색 → 변환"""
        file_list = zf.namelist()

        # 1) 네임스페이스 감지
        self.ns = self._detect_namespaces(zf, file_list)

        # 2) 스타일 맵 로드 (header.xml)
        self._load_styles(zf, file_list)

        # 3) section*.xml 파싱
        section_files = sorted([
            f for f in file_list
            if re.search(r'section\d*\.xml$', f, re.IGNORECASE)
        ])

        md_parts = []
        
        # [분석용] 상호 분석용 메타데이터(YAML Frontmatter) 추가
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        frontmatter = f"---\nsource_file: '{filename}'\nconverted_at: '{current_time}'\n---\n"
        md_parts.append(frontmatter)

        for sf in section_files:
            xml_bytes = zf.read(sf)
            md_parts.append(self._parse_section(xml_bytes))

        # 4) 이미지 추출
        images = self._extract_images(zf, file_list)

        # 5) 최종 Markdown 조립 (여백 및 줄바꿈 정제)
        markdown = "\n\n".join(p for p in md_parts if p.strip())
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        # 제목(#) 앞에 빈 줄을 확실히 보장하여 섹션 구분 강화
        markdown = re.sub(r'([^\n])\n(#+ )', r'\1\n\n\2', markdown).strip()

        return ConvertResult(
            filename=filename, success=True,
            markdown=markdown, images=images
        )

    # ─────────────── 네임스페이스 및 스타일 로드 ───────────────

    def _detect_namespaces(self, zf, file_list) -> dict:
        ns = {}
        sample_files = [f for f in file_list if 'section' in f.lower() and f.endswith('.xml')]
        if not sample_files:
            return ns
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
        if not header_files:
            return

        try:
            xml_bytes = zf.read(header_files[0])
            root = ET.fromstring(xml_bytes)

            for elem in root.iter():
                tag = self._local_tag(elem.tag)
                if tag == 'style':
                    style_id = elem.get('id', '')
                    style_name = elem.get('name', elem.get('engName', ''))
                    
                    if style_id:
                        self.style_map[style_id] = style_name

                    name_lower = style_name.lower()
                    if '개요' in name_lower or 'outline' in name_lower or '제목' in name_lower or 'heading' in name_lower:
                        level = self._extract_level(style_name, style_id)
                        if level:
                            self.heading_ids[style_id] = level
        except:
            pass

    def _extract_level(self, name: str, style_id: str) -> Optional[int]:
        m = re.search(r'(\d+)', name)
        if m:
            level = int(m.group(1))
            return min(level, 6)
        m = re.search(r'(\d+)', style_id)
        if m:
            level = int(m.group(1))
            return min(level, 6)
        return 1

    # ─────────────── 섹션 파싱 ───────────────

    def _parse_section(self, xml_bytes: bytes) -> str:
        root = ET.fromstring(xml_bytes)
        lines = []
        self._walk_elements(root, lines)
        return "\n".join(lines)

    def _walk_elements(self, elem, lines: list):
        tag = self._local_tag(elem.tag)

        if tag == 'p':
            line = self._parse_paragraph(elem)
            lines.append(line)
            return

        if tag in ('table', 'tbl'):
            table_md = self._parse_table(elem)
            lines.append(table_md)
            return

        for child in elem:
            self._walk_elements(child, lines)

    # ─────────────── 문단(Paragraph) 파싱 ───────────────

    def _parse_paragraph(self, p_elem) -> str:
        heading_level = self._get_heading_level(p_elem)
        runs = []
        self._collect_runs(p_elem, runs)
        text = "".join(runs).strip()

        if not text:
            return ""

        if heading_level and heading_level > 0:
            return f"{'#' * heading_level} {text}"

        return text

    def _collect_runs(self, elem, runs: list):
        tag = self._local_tag(elem.tag)

        if tag == 'run':
            run_text = self._extract_run(elem)
            runs.append(run_text)
            return

        if tag == 't' and elem.text:
            # [보완] 물결표(~)가 마크다운 취소선으로 인식되지 않도록 이스케이프(\~) 처리
            runs.append(elem.text.replace("~", "\\~"))
            return

        if tag == 'tab':
            runs.append("    ")
            return

        if tag in ('lineBreak', 'softHyphen'):
            runs.append("  \n")
            return

        for child in elem:
            self._collect_runs(child, runs)

    def _extract_run(self, run_elem) -> str:
        texts = []
        for elem in run_elem.iter():
            tag = self._local_tag(elem.tag)
            if tag == 't' and elem.text:
                # [보완] 물결표(~) 이스케이프 처리
                texts.append(elem.text.replace("~", "\\~"))
            elif tag == 'tab':
                texts.append("    ")
            elif tag in ('lineBreak', 'softHyphen'):
                texts.append("  \n")

        text = "".join(texts)
        if not text.strip():
            return text

        bold = False
        italic = False
        strike = False
        superscript = False
        subscript = False

        for elem in run_elem.iter():
            tag = self._local_tag(elem.tag)
            if tag in ('charPr', 'rPr', 'rPrChange'):
                bold = bold or elem.get('bold', '').lower() in ('true', '1')
                italic = italic or elem.get('italic', '').lower() in ('true', '1')
                strike = strike or elem.get('strikeout', elem.get('strikethrough', '')).lower() in ('true', '1')
                superscript = superscript or elem.get('superscript', '').lower() in ('true', '1')
                subscript = subscript or elem.get('subscript', '').lower() in ('true', '1')

        stripped = text.strip()
        leading = text[:len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]

        # 실제 HWPX 서식 속성으로 지정된 취소선인 경우에만 양옆에 ~~ 적용
        if strike:
            stripped = f"~~{stripped}~~"
        if bold and italic:
            stripped = f"***{stripped}***"
        elif bold:
            stripped = f"**{stripped}**"
        elif italic:
            stripped = f"*{stripped}*"
        if superscript:
            stripped = f"<sup>{stripped}</sup>"
        if subscript:
            stripped = f"<sub>{stripped}</sub>"

        return leading + stripped + trailing

    def _get_heading_level(self, p_elem) -> int:
        for attr_name in p_elem.attrib:
            local = self._local_tag(attr_name)
            if local in ('styleIDRef', 'paraPrIDRef', 'style'):
                val = p_elem.get(attr_name)
                if val in self.heading_ids:
                    return self.heading_ids[val]

        for elem in p_elem.iter():
            tag = self._local_tag(elem.tag)
            if tag in ('paraPr', 'pPr'):
                style_ref = elem.get('styleIDRef', elem.get('style', ''))
                if style_ref in self.heading_ids:
                    return self.heading_ids[style_ref]

                outline = elem.get('outlineLevel', elem.get('level', ''))
                if outline and outline.isdigit():
                    level = int(outline)
                    if 1 <= level <= 6:
                        return level
        return 0

    # ─────────────── 테이블 파싱 (표 안의 표 지원) ───────────────

    def _parse_table(self, table_elem) -> str:
        tr_elems = []
        
        # 부모 표의 행(tr)만 찾고 중첩된 표의 행은 무시하기 위한 재귀 함수
        def find_rows(node):
            for child in node:
                tag = self._local_tag(child.tag)
                if tag == 'tr':
                    tr_elems.append(child)
                elif tag not in ('table', 'tbl'):
                    find_rows(child)
                    
        find_rows(table_elem)
        
        rows = []
        for tr in tr_elems:
            tc_elems = []
            def find_cells(node):
                for child in node:
                    tag = self._local_tag(child.tag)
                    if tag == 'tc':
                        tc_elems.append(child)
                    elif tag not in ('table', 'tbl'):
                        find_cells(child)
            find_cells(tr)
            
            cells = []
            for tc in tc_elems:
                cell_text = self._extract_cell_text(tc)
                cells.append(cell_text)
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
            
        return "\n" + "\n".join(lines) + "\n"

    def _parse_nested_table(self, table_elem) -> str:
        """[보완] 표 안의 표를 HTML <table> 구조로 반환 (마크다운 충돌 방지)"""
        tr_elems = []
        
        def find_rows(node):
            for child in node:
                tag = self._local_tag(child.tag)
                if tag == 'tr':
                    tr_elems.append(child)
                elif tag not in ('table', 'tbl'):
                    find_rows(child)
                    
        find_rows(table_elem)
        
        html = ["<table border='1'>"]
        for tr in tr_elems:
            html.append("<tr>")
            
            tc_elems = []
            def find_cells(node):
                for child in node:
                    tag = self._local_tag(child.tag)
                    if tag == 'tc':
                        tc_elems.append(child)
                    elif tag not in ('table', 'tbl'):
                        find_cells(child)
            find_cells(tr)
            
            for tc in tc_elems:
                cell_text = self._extract_cell_text(tc)
                html.append(f"<td>{cell_text}</td>")
            html.append("</tr>")
        html.append("</table>")
        
        return "".join(html)

    def _extract_cell_blocks(self, elem, parts: list):
        tag = self._local_tag(elem.tag)
        
        if tag == 'p':
            p_text = self._parse_paragraph(elem)
            if p_text.strip():
                parts.append(p_text.strip())
            return
            
        if tag in ('table', 'tbl'):
            # [보완] 셀 내부에 또 다른 표가 있는 경우 감지하여 HTML 표로 렌더링
            nested_html = self._parse_nested_table(elem)
            parts.append(nested_html)
            return
            
        for child in elem:
            self._extract_cell_blocks(child, parts)

    def _extract_cell_text(self, cell_elem) -> str:
        parts = []
        self._extract_cell_blocks(cell_elem, parts)
        
        # [보완] 마크다운 표가 깨지지 않도록 모든 실제 줄바꿈을 <br>로 변경
        text = "<br>".join(parts)
        text = text.replace("\n", "<br>")
        text = re.sub(r'(<br>\s*)+', '<br>', text)
        return text.replace("|", "\\|")

    # ─────────────── 이미지 추출 ───────────────

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

    # ─────────────── 유틸리티 ───────────────

    @staticmethod
    def _local_tag(tag: str) -> str:
        if '}' in tag:
            return tag.split('}', 1)[1]
        return tag


# ─────────────── 편의 함수 ───────────────

def convert_hwpx_to_md(data: bytes, filename: str = "document") -> ConvertResult:
    converter = HwpxToMarkdown()
    return converter.convert_bytes(data, filename)
