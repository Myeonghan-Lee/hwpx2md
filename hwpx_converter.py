"""
hwpx_converter.py
HWPX → Markdown 변환 엔진
"""

import zipfile
import io
import os
import re
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

    # 한컴 HWPX 네임스페이스 (버전별로 다를 수 있음)
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
        self.ns = {}           # 실제 사용된 네임스페이스
        self.style_map = {}    # 스타일ID → 스타일명 맵
        self.heading_ids = {}  # 제목 스타일ID → 레벨

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
        for sf in section_files:
            xml_bytes = zf.read(sf)
            md_parts.append(self._parse_section(xml_bytes))

        # 4) 이미지 추출
        images = self._extract_images(zf, file_list)

        # 5) 최종 Markdown 조립
        markdown = "\n\n".join(p for p in md_parts if p.strip())
        markdown = re.sub(r'\n{3,}', '\n\n', markdown).strip()

        return ConvertResult(
            filename=filename, success=True,
            markdown=markdown, images=images
        )

    # ─────────────── 네임스페이스 감지 ───────────────

    def _detect_namespaces(self, zf, file_list) -> dict:
        """XML에서 실제 사용되는 네임스페이스를 감지"""
        ns = {}
        # section 파일 하나를 읽어서 네임스페이스 추출
        sample_files = [f for f in file_list if 'section' in f.lower() and f.endswith('.xml')]
        if not sample_files:
            return ns
        try:
            content = zf.read(sample_files[0]).decode('utf-8')
            # xmlns:접두어="URI" 패턴 추출
            for match in re.finditer(r'xmlns:(\w+)="([^"]+)"', content):
                prefix, uri = match.group(1), match.group(2)
                ns[prefix] = uri
        except:
            pass
        return ns

    # ─────────────── 스타일 로드 ───────────────

    def _load_styles(self, zf, file_list):
        """header.xml에서 스타일 정보 로드"""
        self.style_map = {}
        self.heading_ids = {}

        header_files = [f for f in file_list if 'header.xml' in f.lower()]
        if not header_files:
            return

        try:
            xml_bytes = zf.read(header_files[0])
            root = ET.fromstring(xml_bytes)

            # 모든 style 요소 탐색
            for elem in root.iter():
                tag = self._local_tag(elem.tag)
                if tag == 'style':
                    style_id = elem.get('id', '')
                    style_name = elem.get('name', elem.get('engName', ''))
                    style_type = elem.get('type', '')

                    if style_id:
                        self.style_map[style_id] = style_name

                    # 개요/제목 스타일 감지
                    name_lower = style_name.lower()
                    if '개요' in name_lower or 'outline' in name_lower or '제목' in name_lower or 'heading' in name_lower:
                        level = self._extract_level(style_name, style_id)
                        if level:
                            self.heading_ids[style_id] = level
        except:
            pass

    def _extract_level(self, name: str, style_id: str) -> Optional[int]:
        """스타일명/ID에서 제목 레벨 추출"""
        # '개요 1', 'Heading 2', '제목3' 등에서 숫자 추출
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
        """section XML 전체를 파싱하여 Markdown 반환"""
        root = ET.fromstring(xml_bytes)
        lines = []
        self._walk_elements(root, lines)
        return "\n".join(lines)

    def _walk_elements(self, elem, lines: list):
        """재귀적으로 요소를 순회하며 Markdown 라인 생성"""
        tag = self._local_tag(elem.tag)

        if tag == 'p':
            line = self._parse_paragraph(elem)
            lines.append(line)
            return  # <p> 내부는 이미 처리됨

        if tag in ('table', 'tbl'):
            table_md = self._parse_table(elem)
            lines.append(table_md)
            return

        # 자식 요소 재귀 탐색
        for child in elem:
            self._walk_elements(child, lines)

    # ─────────────── 문단(Paragraph) 파싱 ───────────────

    def _parse_paragraph(self, p_elem) -> str:
        """<p> 요소 → Markdown 한 줄"""
        # 제목 레벨 확인
        heading_level = self._get_heading_level(p_elem)

        # 텍스트 추출
        runs = []
        self._collect_runs(p_elem, runs)
        text = "".join(runs).strip()

        if not text:
            return ""

        # 제목이면 # 접두어 추가
        if heading_level and heading_level > 0:
            return f"{'#' * heading_level} {text}"

        return text

    def _collect_runs(self, elem, runs: list):
        """<run> 및 하위 텍스트/서식 요소를 순회하며 텍스트 수집"""
        tag = self._local_tag(elem.tag)

        if tag == 'run':
            run_text = self._extract_run(elem)
            runs.append(run_text)
            return

        if tag == 't' and elem.text:
            runs.append(elem.text)
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
        """<run> 요소에서 텍스트 + 서식 추출"""
        # 텍스트 수집
        texts = []
        for elem in run_elem.iter():
            tag = self._local_tag(elem.tag)
            if tag == 't' and elem.text:
                texts.append(elem.text)
            elif tag == 'tab':
                texts.append("    ")
            elif tag in ('lineBreak', 'softHyphen'):
                texts.append("  \n")

        text = "".join(texts)
        if not text.strip():
            return text

        # 서식 확인 (charPr)
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

        # Markdown 서식 적용
        stripped = text.strip()
        leading = text[:len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]

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

    # ─────────────── 제목 감지 ───────────────

    def _get_heading_level(self, p_elem) -> int:
        """문단의 스타일을 분석하여 제목 레벨 반환 (0=본문)"""
        # 방법 1: styleIDRef / paraPrIDRef 속성 확인
        for attr_name in p_elem.attrib:
            local = self._local_tag(attr_name)
            if local in ('styleIDRef', 'paraPrIDRef', 'style'):
                val = p_elem.get(attr_name)
                if val in self.heading_ids:
                    return self.heading_ids[val]

        # 방법 2: 하위 paraPr의 style 참조 확인
        for elem in p_elem.iter():
            tag = self._local_tag(elem.tag)
            if tag in ('paraPr', 'pPr'):
                style_ref = elem.get('styleIDRef', elem.get('style', ''))
                if style_ref in self.heading_ids:
                    return self.heading_ids[style_ref]

                # outlineLevel 직접 지정
                outline = elem.get('outlineLevel', elem.get('level', ''))
                if outline and outline.isdigit():
                    level = int(outline)
                    if 1 <= level <= 6:
                        return level

        return 0

    # ─────────────── 테이블 파싱 ───────────────

    def _parse_table(self, table_elem) -> str:
        """<table> → Markdown 테이블"""
        rows = []

        for elem in table_elem.iter():
            tag = self._local_tag(elem.tag)
            if tag == 'tr':
                cells = []
                for cell_elem in elem.iter():
                    cell_tag = self._local_tag(cell_elem.tag)
                    if cell_tag == 'tc':
                        cell_text = self._extract_cell_text(cell_elem)
                        cells.append(cell_text)
                if cells:
                    rows.append(cells)

        if not rows:
            return ""

        # 컬럼 수 통일
        max_cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < max_cols:
                r.append("")

        # Markdown 테이블 생성
        lines = []
        # 헤더
        header = "| " + " | ".join(rows[0]) + " |"
        separator = "| " + " | ".join(["---"] * max_cols) + " |"
        lines.append(header)
        lines.append(separator)

        # 본문
        for row in rows[1:]:
            line = "| " + " | ".join(row) + " |"
            lines.append(line)

        return "\n".join(lines)

    def _extract_cell_text(self, cell_elem) -> str:
        """셀 내 텍스트 추출"""
        texts = []
        for elem in cell_elem.iter():
            tag = self._local_tag(elem.tag)
            if tag == 't' and elem.text:
                texts.append(elem.text.strip())
        return " ".join(texts).replace("|", "\\|")

    # ─────────────── 이미지 추출 ───────────────

    def _extract_images(self, zf, file_list) -> Dict[str, bytes]:
        """BinData 폴더에서 이미지 파일 추출"""
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
        """'{namespace}localName' → 'localName'"""
        if '}' in tag:
            return tag.split('}', 1)[1]
        return tag


# ─────────────── 편의 함수 ───────────────

def convert_hwpx_to_md(data: bytes, filename: str = "document") -> ConvertResult:
    """단일 함수로 HWPX → Markdown 변환"""
    converter = HwpxToMarkdown()
    return converter.convert_bytes(data, filename)
