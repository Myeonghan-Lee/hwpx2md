"""
🔄 HWPX → Markdown 변환기  |  Streamlit Web App
"""

import streamlit as st
import zipfile
import io
import os
from datetime import datetime
from hwpx_converter import HwpxToMarkdown, ConvertResult

# ─────────────────────────────────────
#  페이지 설정
# ─────────────────────────────────────
st.set_page_config(
    page_title="HWPX → Markdown 변환기",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────
#  커스텀 CSS
# ─────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A5F;
        text-align: center;
        padding: 1rem 0 0.5rem 0;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #6B7280;
        text-align: center;
        margin-bottom: 2rem;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #D1FAE5;
        border-left: 4px solid #10B981;
        margin: 1rem 0;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #FEE2E2;
        border-left: 4px solid #EF4444;
        margin: 1rem 0;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #DBEAFE;
        border-left: 4px solid #3B82F6;
        margin: 1rem 0;
    }
    .stDownloadButton > button {
        width: 100%;
        background-color: #2563EB;
        color: white;
        border: none;
        padding: 0.75rem;
        font-size: 1rem;
        font-weight: 600;
    }
    .stDownloadButton > button:hover {
        background-color: #1D4ED8;
        color: white;
    }
    div[data-testid="stFileUploader"] {
        border: 2px dashed #93C5FD;
        border-radius: 1rem;
        padding: 1rem;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────
#  헤더
# ─────────────────────────────────────
st.markdown('<div class="main-header">📝 HWPX → Markdown 변환기</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">한컴 HWPX 파일을 Markdown(.md)으로 간편하게 변환하세요</div>', unsafe_allow_html=True)


# ─────────────────────────────────────
#  사이드바
# ─────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정")

    include_images = st.checkbox("🖼️ 이미지 포함", value=True, help="문서 내 이미지를 함께 추출합니다.")
    show_raw = st.checkbox("📄 Raw Markdown 표시", value=False, help="렌더링 대신 원본 텍스트를 표시합니다.")

    st.divider()

    st.header("📖 사용 방법")
    st.markdown("""
    1. **파일 1개** 업로드 → 미리보기 + 다운로드
    2. **파일 여러 개** 업로드 → ZIP으로 일괄 다운로드

    지원 형식: `.hwpx`
    """)

    st.divider()

    st.markdown("""
    <div style='text-align:center; color:#9CA3AF; font-size:0.85rem;'>
        Made with ❤️ using Streamlit<br>
        HWPX → Markdown Converter
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────
#  파일 업로드
# ─────────────────────────────────────
st.markdown("### 📁 HWPX 파일 업로드")

uploaded_files = st.file_uploader(
    "HWPX 파일을 드래그 앤 드롭하거나 클릭하여 선택하세요",
    type=["hwpx"],
    accept_multiple_files=True,
    help="하나 또는 여러 개의 .hwpx 파일을 업로드할 수 있습니다.",
)


# ─────────────────────────────────────
#  변환 처리
# ─────────────────────────────────────
if uploaded_files:
    converter = HwpxToMarkdown()
    results: list[ConvertResult] = []

    # 프로그레스 바
    progress = st.progress(0, text="변환 중...")

    for i, uf in enumerate(uploaded_files):
        file_bytes = uf.read()
        fname = os.path.splitext(uf.name)[0]
        result = converter.convert_bytes(file_bytes, fname)
        results.append(result)
        progress.progress((i + 1) / len(uploaded_files), text=f"변환 중... ({i+1}/{len(uploaded_files)})")

    progress.empty()

    # 성공/실패 카운트
    success_results = [r for r in results if r.success]
    failed_results  = [r for r in results if not r.success]

    # 상태 요약
    col1, col2, col3 = st.columns(3)
    col1.metric("📄 전체 파일", len(results))
    col2.metric("✅ 성공", len(success_results))
    col3.metric("❌ 실패", len(failed_results))

    st.divider()

    # ─── 단일 파일: 미리보기 모드 ───
    if len(uploaded_files) == 1 and success_results:
        r = success_results[0]

        st.markdown("### 🔍 변환 결과 미리보기")

        # 탭: 렌더링 / Raw
        tab_preview, tab_raw, tab_info = st.tabs(["📖 렌더링 미리보기", "📄 Raw Markdown", "ℹ️ 파일 정보"])

        with tab_preview:
            st.markdown(r.markdown)

        with tab_raw:
            st.code(r.markdown, language="markdown", line_numbers=True)

        with tab_info:
            st.markdown(f"""
            | 항목 | 값 |
            |------|------|
            | 파일 이름 | `{r.filename}.hwpx` |
            | 변환된 줄 수 | {len(r.markdown.splitlines())} 줄 |
            | 문자 수 | {len(r.markdown):,} 자 |
            | 추출된 이미지 | {len(r.images)} 개 |
            """)

        # 다운로드 버튼
        st.divider()
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                label=f"⬇️  {r.filename}.md 다운로드",
                data=r.markdown.encode("utf-8"),
                file_name=f"{r.filename}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with col_dl2:
            if r.images and include_images:
                # 이미지 포함 ZIP
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr(f"{r.filename}.md", r.markdown)
                    for img_name, img_bytes in r.images.items():
                        zf.writestr(f"images/{img_name}", img_bytes)
                st.download_button(
                    label="🗂️  MD + 이미지 ZIP 다운로드",
                    data=zip_buf.getvalue(),
                    file_name=f"{r.filename}_md.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

    # ─── 여러 파일: 일괄 변환 모드 ───
    elif len(uploaded_files) > 1:
        st.markdown("### 📦 일괄 변환 결과")

        # 각 파일 결과 표시
        for r in results:
            if r.success:
                with st.expander(f"✅ {r.filename}.md  —  {len(r.markdown):,}자, {len(r.images)}개 이미지", expanded=False):
                    preview_tab, raw_tab = st.tabs(["📖 미리보기", "📄 Raw"])
                    with preview_tab:
                        st.markdown(r.markdown[:3000] + ("\n\n..." if len(r.markdown) > 3000 else ""))
                    with raw_tab:
                        st.code(r.markdown[:3000], language="markdown")
            else:
                st.markdown(f'<div class="error-box">❌ <b>{r.filename}.hwpx</b> — {r.error_msg}</div>', unsafe_allow_html=True)

        # ZIP 일괄 다운로드
        if success_results:
            st.divider()
            st.markdown("### ⬇️ 일괄 다운로드")

            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for r in success_results:
                    zf.writestr(f"{r.filename}.md", r.markdown)
                    if include_images and r.images:
                        for img_name, img_bytes in r.images.items():
                            zf.writestr(f"{r.filename}_images/{img_name}", img_bytes)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label=f"🗂️  변환된 {len(success_results)}개 파일 ZIP 다운로드",
                data=zip_buf.getvalue(),
                file_name=f"hwpx2md_{timestamp}.zip",
                mime="application/zip",
                use_container_width=True,
            )

    # 실패 목록 표시
    if failed_results:
        st.divider()
        st.markdown("### ⚠️ 변환 실패 파일")
        for r in failed_results:
            st.markdown(f'<div class="error-box">❌ <b>{r.filename}.hwpx</b>: {r.error_msg}</div>', unsafe_allow_html=True)

else:
    # 업로드 전 안내
    st.markdown("""
    <div class="info-box">
        💡 <b>시작하려면 위에서 HWPX 파일을 업로드하세요.</b><br><br>
        • 파일 <b>1개</b> → Markdown 미리보기 + 다운로드<br>
        • 파일 <b>여러 개</b> → 일괄 변환 후 ZIP 다운로드
    </div>
    """, unsafe_allow_html=True)

    # 데모: HWPX 구조 설명
    with st.expander("📚 HWPX 파일 구조란?"):
        st.markdown("""
        HWPX는 한컴오피스 한글의 **XML 기반 문서 포맷**으로, 실제로는 **ZIP 압축** 파일입니다.

        ```
        📁 문서.hwpx (ZIP)
        ├── mimetype
        ├── META-INF/
        │   └── manifest.xml
        ├── Contents/
        │   ├── content.hpf       ← 문서 메타정보
        │   ├── header.xml        ← 스타일/설정
        │   ├── section0.xml      ← ⭐ 본문 텍스트
        │   └── section1.xml      ← 추가 섹션
        └── BinData/              ← 이미지 등
        ```

        이 변환기는 `section*.xml` 내부의 XML을 파싱하여 **제목, 본문, 표, 서식**을 Markdown으로 변환합니다.
        """)
