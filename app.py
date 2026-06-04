"""
app.py — HWPX to Markdown Converter (Streamlit Web App)
"""

import streamlit as st
import zipfile
import io
import os
from hwpx_converter import HwpxToMarkdown, ConvertResult

# ─────────────── 페이지 설정 ───────────────

st.set_page_config(
    page_title="HWPX → Markdown 변환기",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────── CSS ───────────────

st.markdown("""
<style>
    .main-title {
        text-align: center;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 800;
        margin-bottom: 0;
    }
    .sub-title {
        text-align: center;
        color: #888;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 8px 20px;
        border-radius: 8px 8px 0 0;
    }
    .file-info-box {
        background-color: #f8f9fa;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .success-badge {
        background-color: #d4edda;
        color: #155724;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .error-badge {
        background-color: #f8d7da;
        color: #721c24;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────── 헤더 ───────────────

st.markdown('<p class="main-title">📝 HWPX → Markdown 변환기</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">한글(HWPX) 문서를 Markdown으로 간편하게 변환하세요</p>', unsafe_allow_html=True)

# ─────────────── 파일 업로드 ───────────────

uploaded_files = st.file_uploader(
    "HWPX 파일을 드래그하거나 클릭하여 업로드하세요",
    type=["hwpx"],
    accept_multiple_files=True,
    help="여러 파일을 동시에 업로드할 수 있습니다."
)

if not uploaded_files:
    # 안내 메시지
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### 📄 단일 파일")
        st.markdown("파일 **1개** 업로드 시\nMarkdown **미리보기**를 제공합니다.")
    with col2:
        st.markdown("### 📦 다중 파일")
        st.markdown("파일 **여러 개** 업로드 시\n**ZIP으로 일괄 다운로드**할 수 있습니다.")
    with col3:
        st.markdown("### ✨ 지원 서식")
        st.markdown("제목, **굵게**, *기울임*, ~~취소선~~, 표, 이미지 추출을 지원합니다.")
    st.stop()

# ─────────────── 변환 실행 ───────────────

converter = HwpxToMarkdown()
results: list[ConvertResult] = []

progress_bar = st.progress(0, text="변환 중...")

for i, uploaded_file in enumerate(uploaded_files):
    data = uploaded_file.read()
    result = converter.convert_bytes(data, uploaded_file.name)
    results.append(result)
    progress_bar.progress((i + 1) / len(uploaded_files), 
                          text=f"변환 중... ({i+1}/{len(uploaded_files)})")

progress_bar.empty()

# 성공/실패 분류
successes = [r for r in results if r.success]
failures = [r for r in results if not r.success]

# 요약 표시
col_s, col_f = st.columns(2)
with col_s:
    st.success(f"✅ 변환 성공: **{len(successes)}개** 파일")
with col_f:
    if failures:
        st.error(f"❌ 변환 실패: **{len(failures)}개** 파일")

st.markdown("---")

# ═══════════════════════════════════════════
# 모드 A: 단일 파일 → 미리보기
# ═══════════════════════════════════════════

if len(uploaded_files) == 1 and len(successes) == 1:
    r = successes[0]
    md_filename = os.path.splitext(r.filename)[0] + ".md"

    # 3개 탭
    tab_render, tab_source, tab_info = st.tabs([
        "📄 렌더링 미리보기", "📝 Markdown 소스", "ℹ️ 파일 정보"
    ])

    #with tab_render:
        #st.markdown(r.markdown)

    with tab_render:
        st.markdown(r.markdown, unsafe_allow_html=True)
    
    with tab_source:
        st.code(r.markdown, language="markdown", line_numbers=True)

    with tab_info:
        col1, col2, col3 = st.columns(3)
        col1.metric("원본 파일", r.filename)
        col2.metric("Markdown 글자 수", f"{len(r.markdown):,}")
        col3.metric("추출된 이미지", f"{len(r.images)}개")

    # 다운로드 버튼
    st.markdown("---")
    col_dl1, col_dl2, col_dl3 = st.columns([1, 1, 2])

    with col_dl1:
        st.download_button(
            label="⬇️ .md 파일 다운로드",
            data=r.markdown.encode('utf-8'),
            file_name=md_filename,
            mime="text/markdown",
            use_container_width=True,
        )

    with col_dl2:
        # 이미지 포함 ZIP
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(md_filename, r.markdown.encode('utf-8'))
            for img_name, img_data in r.images.items():
                zf.writestr(f"images/{img_name}", img_data)

        st.download_button(
            label="📦 ZIP 다운로드 (이미지 포함)",
            data=zip_buf.getvalue(),
            file_name=os.path.splitext(r.filename)[0] + ".zip",
            mime="application/zip",
            use_container_width=True,
        )

# ═══════════════════════════════════════════
# 모드 B: 다중 파일 → 일괄 변환 + ZIP
# ═══════════════════════════════════════════

else:
    # 전체 ZIP 다운로드 (상단)
    if successes:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for r in successes:
                md_name = os.path.splitext(r.filename)[0] + ".md"
                zf.writestr(md_name, r.markdown.encode('utf-8'))
                for img_name, img_data in r.images.items():
                    folder = os.path.splitext(r.filename)[0]
                    zf.writestr(f"{folder}/images/{img_name}", img_data)

        st.download_button(
            label=f"📦 전체 ZIP 다운로드 ({len(successes)}개 파일)",
            data=zip_buf.getvalue(),
            file_name="hwpx_converted.zip",
            mime="application/zip",
            use_container_width=True,
            type="primary",
        )

    st.markdown("---")
    st.markdown("### 📋 변환 결과")

    # 성공 파일 목록
    for r in successes:
        md_name = os.path.splitext(r.filename)[0] + ".md"

        with st.expander(f"✅ {r.filename}  →  {md_name}", expanded=False):
            tab_r, tab_s = st.tabs(["📄 렌더링", "📝 소스"])
            with tab_r:
                # 긴 문서는 높이 제한
                st.markdown(r.markdown)
            with tab_s:
                st.code(r.markdown, language="markdown", line_numbers=True)

            st.download_button(
                label=f"⬇️ {md_name} 다운로드",
                data=r.markdown.encode('utf-8'),
                file_name=md_name,
                mime="text/markdown",
                key=f"dl_{r.filename}",
            )

    # 실패 파일 목록
    if failures:
        st.markdown("### ❌ 변환 실패")
        for r in failures:
            with st.expander(f"❌ {r.filename}", expanded=False):
                st.error(f"오류: {r.error}")

# ─────────────── 푸터 ───────────────

st.markdown("---")
st.markdown(
    '<p style="text-align:center; color:#aaa; font-size:0.85rem;">'
    'HWPX → Markdown Converter | '
    'Powered by Streamlit'
    '</p>',
    unsafe_allow_html=True
)
