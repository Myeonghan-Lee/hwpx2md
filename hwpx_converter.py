"""
HWPX → Markdown 변환 엔진
HWPX(ZIP) 내부의 section*.xml을 파싱하여 Markdown으로 변환합니다.
"""

import zipfile
import xml.etree.ElementTree as ET
import os
import re
import io
from dataclasses import dataclass, field


@dataclass
class ConvertResult:
    """변환 결과를 담는 데이터 클래스"""
    filename: str = ""
    markdown: str = ""
    images: dict = field(default_factory=dict)  # {이미지이름: bytes}
    success: bool = True
    error_msg: str = ""


class HwpxToMarkdown:
    """HWPX 파일을 Markdown으로 변환하는 클래스"""

    # HWPX에서 사용하는 XML 네임스페이스 매핑
    NS_PATTERNS = {
        'paragraph': 'http://www.hancom.co.kr/hwpml/2011/paragraph',
        'core':      'http://www.hancom.co.kr/hwpml/2011/core',
        'table':     'http://www.hancom.co.kr/hwpml/2011/table',
        'head':      'http://www.hancom.co.kr/hwpml/2011/head',
        'masterpage':'http://www.hancom.co.kr/hwpml/2011/master-page',
    }

    # 개요(Outline) 스타일 → 제목 레벨 매핑
    OUTLINE_HEADING_MAP = {
        'Outline 1': 1, 'Outline 2': 2, 'Outline 3': 3,
        'Outline 4': 4, 'Outline 5': 5, 'Outline 6': 6,
        '개요 1': 1, '개요 2': 2, '개요 3': 3,
        '개요 4': 4, '개요 5': 5, '개요 6': 6,
    }

    def __init__(self):
        self.style_map = {}  # styleIDRef → 스타일 이름 매핑

    # ─────────────────────────────────────
    #  공개 API
    # ─────────────────────────────────────
    def convert_bytes(self, file_bytes: bytes, filename: str = "document") -> ConvertResult:
        """바이트 데이터로부터 변환 (Streamlit 업로드용)"""
        result = ConvertResult(filename=filename)
        try:
            bio = io.BytesIO(file_bytes)
            if not zipfile.is_zipfile(bio):
                result.success = False
                result.error_msg = "유효한 HWPX(ZIP) 파일이 아닙니다."
                return result
            bio.seek(0)
            result.markdown, result.images = self._process_zip(bio)
        except Exception as e:
            result.success = False
            result.error_msg = str(e)
        return result

    def convert_file(self, filepath: str) -> ConvertResult:
        """파일 경로로부터 변환"""
        filename = os.path.splitext(os.path.basename(filepath))[0]
        with open(filepath, 'rb') as f:
            return self.convert_bytes(f.read(), filename)

    # ─────────────────────────────────────
    #  내부 처리
    # ─────────────────────────────────────
    def _process_zip(self, file_obj) -> tuple:
        """ZIP(HWPX)을 열어 Markdown 텍스트와 이미지 딕셔너리 반환"""
        md_lines = []
        images = {}

        with zipfile.ZipFile(file_obj, 'r') as zf:
            file_list = zf.namelist()

            # ① 스타일 맵 구축 (header.xml / content.hpf)
            self._build_style_map(zf, file_list)

            # ② section*.xml 파일을 정렬하여 순서대로 파싱
            section_files = sorted([
                f for f in file_list
                if re.search(r'section\d*\.xml$', f, re.IGNORECASE)
            ])

            for sf in section_files:
                xml_bytes = zf.read(sf)
                lines = self._parse_section(xml_bytes)
                md_lines.extend(lines)

            # ③ 이미지 추출
            img_exts = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.tif', '.tiff')
            for f in file_list:
                if any(f.lower().endswith(e) for e in img_exts):
                    img_name = os.path.basename(f)
                    images[img_name] = zf.read(f)

        # 후처리: 연속 빈 줄 정리
        md_text = '\n'.join(md_lines)
        md_text = re.sub(r'\n{3,}', '\n\n', md_text).strip()
        return md_text, images

    # ─────────────────────────────────────
    #  스타일 맵
    # ─────────────────────────────────────
    def _build_style_map(self, zf, file_list):
        """header.xml 등에서 스타일 ID → 이름 매핑 구축"""
        self.style_map = {}
        header_candidates = [f for f in file_list if 'header.xml' in f.lower()]
        for hf in header_candidates:
            try:
                root = ET.fromstring(zf.read(hf))
                for elem in root.iter():
                    tag = self._local(elem.tag)
                    if tag == 'style':
                        sid = elem.attrib.get('id', '')
                        sname = elem.attrib.get('name', '')
                        if sid:
                            self.style_map[sid] = sname
            except Exception:
                pass

    # ─────────────────────────────────────
    #  섹션 파싱
    # ─────────────────────────────────────
    def _parse_section(self, xml_bytes: bytes) -> list:
        """하나의 section XML → Markdown 줄 리스트"""
        root = ET.fromstring(xml_bytes)
        lines = []
        for elem in root.iter():
            tag = self._local(elem.tag)
            if tag == 'p':
                line = self._parse_paragraph(elem)
                lines.append(line)
            elif tag == 'table':
                table_md = self._parse_table(elem)
                lines.append(table_md)
        return lines

    def _parse_paragraph(self, p_elem) -> str:
        """<p> 요소 → Markdown 한 줄"""
        # 제목 레벨 감지
        heading = self._detect_heading(p_elem)

        # 텍스트 조각 수집
        segments = []
        for child in p_elem.iter():
            tag = self._local(child.tag)

            if tag == 'run':
                run_text = self._extract_run(child)
                if run_text:
                    segments.append(run_text)
            elif tag == 't' and child.text:
                # 직접 <t> 태그
                if not any(self._local(p.tag) == 'run' for p in self._iter_parents(child, p_elem)):
                    segments.append(child.text)
            elif tag == 'tab':
                segments.append('  ')
            elif tag in ('lineBreak', 'linebreak'):
                segments.append('  \n')
            elif tag == 'image':
                # 이미지 참조
                img_id = child.attrib.get('binaryItemIDRef', '')
                if img_id:
                    segments.append(f'![{img_id}]({img_id})')

        text = ''.join(segments).strip()
        if not text:
            return ''

        # 제목이면 # 추가
        if heading and 1 <= heading <= 6:
            return f'\n{"#" * heading} {text}\n'

        return text

    def _extract_run(self, run_elem) -> str:
        """<run> 요소에서 텍스트 + 서식(bold/italic) 추출"""
        bold = False
        italic = False
        strike = False

        for child in run_elem.iter():
            tag = self._local(child.tag)
            if tag in ('charPr', 'charProperties'):
                bold = child.attrib.get('bold', '0') in ('1', 'true', 'True')
                italic = child.attrib.get('italic', '0') in ('1', 'true', 'True')
                strike = child.attrib.get('strikeout', '0') in ('1', 'true', 'True')

        # 텍스트 수집
        texts = []
        for child in run_elem.iter():
            tag = self._local(child.tag)
            if tag == 't' and child.text:
                texts.append(child.text)
            elif tag == 'tab':
                texts.append('  ')

        text = ''.join(texts)
        if not text.strip():
            return text

        # 서식 적용
        if bold and italic:
            text = f'***{text.strip()}*** '
        elif bold:
            text = f'**{text.strip()}** '
        elif italic:
            text = f'*{text.strip()}* '
        if strike:
            text = f'~~{text.strip()}~~ '

        return text

    def _detect_heading(self, p_elem) -> int:
        """문단의 제목 레벨 감지 (0이면 본문)"""
        # 방법 1: 속성에서 직접 찾기
        for attr_name, attr_value in p_elem.attrib.items():
            local = self._local(attr_name)

            # 스타일 ID로 매핑
            if local in ('paraPrIDRef', 'styleIDRef', 'style'):
                style_name = self.style_map.get(attr_value, attr_value)
                for key, level in self.OUTLINE_HEADING_MAP.items():
                    if key.lower() in style_name.lower():
                        return level

            # 숫자 ID가 직접 제목 레벨인 경우 (일부 HWPX)
            if local == 'paraPrIDRef' and attr_value.isdigit():
                num = int(attr_value)
                if 1 <= num <= 6:
                    return num

        # 방법 2: 하위 요소에서 outlineLevel 찾기
        for child in p_elem.iter():
            tag = self._local(child.tag)
            if tag in ('paraPr', 'paraProperties'):
                ol = child.attrib.get('outlineLevel', '')
                if ol.isdigit() and 1 <= int(ol) <= 6:
                    return int(ol)

        return 0

    # ─────────────────────────────────────
    #  테이블 파싱
    # ─────────────────────────────────────
    def _parse_table(self, table_elem) -> str:
        """<table> 요소 → Markdown 테이블"""
        rows = []
        for elem in table_elem.iter():
            tag = self._local(elem.tag)
            if tag == 'tr':
                cells = []
                for cell_elem in elem.iter():
                    cell_tag = self._local(cell_elem.tag)
                    if cell_tag == 'tc':
                        cell_text = self._extract_cell_text(cell_elem)
                        cells.append(cell_text)
                if cells:
                    rows.append(cells)

        if not rows:
            return ''

        # Markdown 테이블 생성
        col_count = max(len(r) for r in rows)
        md_rows = []
        for i, row in enumerate(rows):
            # 열 수 맞추기
            while len(row) < col_count:
                row.append('')
            md_rows.append('| ' + ' | '.join(row) + ' |')
            if i == 0:
                md_rows.append('| ' + ' | '.join(['---'] * col_count) + ' |')

        return '\n' + '\n'.join(md_rows) + '\n'

    def _extract_cell_text(self, tc_elem) -> str:
        """테이블 셀에서 텍스트 추출"""
        texts = []
        for child in tc_elem.iter():
            tag = self._local(child.tag)
            if tag == 't' and child.text:
                texts.append(child.text)
        return ' '.join(texts).strip().replace('|', '\\|')

    # ─────────────────────────────────────
    #  유틸리티
    # ─────────────────────────────────────
    @staticmethod
    def _local(tag: str) -> str:
        """'{namespace}localName' → 'localName'"""
        if '}' in tag:
            return tag.split('}', 1)[1]
        return tag

    @staticmethod
    def _iter_parents(child, root):
        """간단한 부모 탐색 (제한적)"""
        return []
