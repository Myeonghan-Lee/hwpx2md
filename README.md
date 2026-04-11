# 📝 HWPX → Markdown 변환기

한컴오피스 한글의 HWPX 파일을 Markdown(.md)으로 변환하는 웹 앱입니다.

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| 📄 단일 파일 변환 | HWPX 1개 업로드 → Markdown **미리보기** + 다운로드 |
| 📦 일괄 변환 | HWPX 여러 개 업로드 → **ZIP으로 일괄 다운로드** |
| 🖼️ 이미지 추출 | 문서 내 이미지를 함께 추출하여 ZIP에 포함 |
| 📊 표 변환 | HWPX 테이블 → Markdown 테이블 자동 변환 |
| ✏️ 서식 지원 | **굵게**, *기울임*, ~~취소선~~ 등 서식 유지 |

## 🚀 배포 방법

### 1. GitHub 저장소 생성

```bash
git init
git add .
git commit -m "Initial commit: HWPX to Markdown converter"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/hwpx2md.git
git push -u origin main
```

### 2. Streamlit Cloud 배포

1. [share.streamlit.io](https://share.streamlit.io) 접속
2. **New app** 클릭
3. GitHub 저장소 연결
4. Main file: `app.py` 선택
5. **Deploy!** 클릭

## 📁 프로젝트 구조

```
hwpx2md/
├── app.py                  # Streamlit 메인 앱
├── hwpx_converter.py       # HWPX→MD 변환 엔진
├── requirements.txt        # Python 의존성
├── .streamlit/
│   └── config.toml         # Streamlit 테마 설정
└── README.md               # 이 문서
```

## 🛠️ 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 📋 지원 범위

- ✅ 제목 (Heading 1~6)
- ✅ 본문 텍스트
- ✅ 굵게 / 기울임 / 취소선
- ✅ 표 (Table)
- ✅ 이미지 추출
- ⚠️ 각주/미주 (제한적)
- ⚠️ 복잡한 수식 (미지원)
