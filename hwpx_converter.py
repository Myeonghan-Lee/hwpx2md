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
    # 기존 네임스페이스 동일 유지
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

    def _process_zip(self, zf: zipfile.ZipFile, filename: str) -> ConvertResult:
        file_list = zf.namelist()
        self.ns = self._detect_namespaces(zf, file_list)
        self._load_styles(zf, file_list)

        section_files = sorted([f for f in file_list if re.search(r'section\d*\.xml$', f, re.IGNORECASE)])

        md_parts = []
        
        # [보완 1] 상호 분석용 메타데이터(YAML Frontmatter) 추가
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        frontmatter = f"---\nsource_file: '{filename}'\nconverted_at: '{current_time}'\n---\n"
        md_parts.append(frontmatter)

        for sf in section_files:
            xml_bytes = zf.read(sf)
            md_parts.append(self._parse_section(xml_bytes))

        images = self._extract_images(zf, file_list)

        # [보완 3] 다중 개행 정리 및 제목 주변 여백 강제
        markdown = "\n\n".join(p for p in md_parts if p.strip())
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        # 제목(#) 앞에 빈 줄을 확실히 보장하여 섹션 구분 강화
        markdown = re.sub(r'([^\n])\n(#+ )', r'\1\n\n\2', markdown).strip()

        return ConvertResult(
            filename=filename, success=True,
            markdown=markdown, images=images
        )

    # ( _detect_namespaces, _load_styles, _extract_level 등은 기존과 완전히 동일하여 생략. 그대로 사용하시면 됩니다. )
    
    # ... [기존 코드 동일 부분 생략] ...

    def _parse_table(self, table_elem) -> str:
        rows = []
        for elem in table_elem.iter():
            tag = self._local_tag(elem.tag)
            if tag == 'tr':
                cells = []
                for cell_elem in elem.iter():
                    cell_tag = self._local_tag(cell_elem.tag)
                    if cell_tag == 'tc':
                        # [보완 2] 셀 내부 텍스트 추출 로직 개선 적용
                        cell_text = self._extract_cell_text(cell_elem)
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

        # 표 위아래로 확실한 공백 보장 (LLM 파싱 오류 방지)
        return "\n" + "\n".join(lines) + "\n"

    def _extract_cell_text(self, cell_elem) -> str:
        texts = []
        for p_elem in cell_elem.iter():
            tag = self._local_tag(p_elem.tag)
            # 셀 내부의 문단(p) 단위로 줄바꿈을 <br>로 처리하여 마크다운 표 붕괴 방지
            if tag == 'p':
                p_text = "".join(t.text for t in p_elem.iter() if self._local_tag(t.tag) == 't' and t.text)
                if p_text.strip():
                    texts.append(p_text.strip())
        
        # [보완 2] 셀 내의 여러 줄을 <br>로 연결하고 파이프(|) 기호 무력화
        return "<br>".join(texts).replace("|", "\\|")
