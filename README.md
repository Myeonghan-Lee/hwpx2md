# 📝 HWPX → Markdown 변환기

한글(HWPX) 문서를 Markdown으로 변환하는 웹 애플리케이션입니다.

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| 📄 단일 파일 변환 | Markdown 렌더링 미리보기 + 소스코드 뷰 |
| 📦 다중 파일 변환 | 일괄 변환 후 ZIP 다운로드 |
| 🎨 서식 보존 | 제목, **굵게**, *기울임*, ~~취소선~~, 표 |
| 🖼️ 이미지 추출 | BinData 내 이미지를 ZIP으로 함께 제공 |

## 🚀 배포 방법

### Streamlit Cloud

1. 이 저장소를 Fork 또는 Clone
2. [share.streamlit.io](https://share.streamlit.io) 접속
3. Repository 선택 → Deploy

### 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 📁 프로젝트 구조

```
├── app.py                ← Streamlit 웹앱
├── hwpx_converter.py     ← HWPX→MD 변환 엔진
├── requirements.txt      ← 의존성
├── .streamlit/
│   └── config.toml       ← 테마 설정
└── README.md
```

## 🔧 지원 서식

- `# ~ ######` 제목 (개요/Heading 스타일 자동 감지)
- `**굵게**`, `*기울임*`, `~~취소선~~`
- Markdown 테이블 (`| 열1 | 열2 |`)
- `<sup>`, `<sub>` 위/아래 첨자
- 이미지 추출 (PNG, JPG 등)

## ⚠️ 참고사항

- `.hwp` (구형 바이너리 포맷)는 지원하지 않습니다. `.hwpx`만 지원됩니다.
- 복잡한 레이아웃(다단, 머리글/바닥글 등)은 단순 텍스트로 변환됩니다.
