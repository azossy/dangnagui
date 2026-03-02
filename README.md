# 당나귀 게시판검색기 (dangnagui)

> 임금님귀 v1.2.1 · copyright by 챠리 (challychoi@me.com)

토픽별 핫키워드·네티즌 의견 실시간 리포트를 생성하는 Windows 데스크톱 앱.  
Microsoft Fluent 스타일 다크 UI · USB 포터블 · Windows 10/11 지원.

---

## 빠른 설치

**[dangnagui-setup-v1.2.1.exe](https://github.com/azossy/dangnagui/releases/latest)** 다운로드 → 실행 → 완료!

> 설치 없이 사용하려면 Releases에서 포터블 ZIP을 받아 압축을 풀고 `dangnagui.exe`를 실행하세요.

---

## 주요 기능

- **스타트** — 설정된 토픽·시간 기준 리포트 생성, 클립보드 자동 복사
- **설정(⚙)** — 토픽 추가/삭제/순서 변경, 핫키워드 개수(1~10), 검색 기준 시간(30~100시간)
- **사이트 갱신** — 토픽별 관련 사이트·게시판을 DuckDuckGo 웹검색으로 최신화
- **리포트 저장(💾)** — 텍스트 파일로 저장
- **소셜 공유** — Facebook, X, 카카오톡, 텔레그램, 인스타그램, 디스코드

---

## 개발자용

### 소스에서 실행

```bash
pip install -r requirements.txt
python main.py
```

### 빌드 (배포용 EXE + 인스톨러)

```bash
build.bat
```

- PyInstaller로 `dist\dangnagui\dangnagui.exe` 생성
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) 설치 시 `Output\dangnagui-setup-v1.2.1.exe` 인스톨러 자동 생성

### 프로젝트 구조

```
├── main.py               # 메인 GUI (진입점)
├── common.py             # 공통 상수·유틸·로깅
├── app_settings.py       # 설정 로드/저장, 웹검색 연동
├── report_engine.py      # 리포트 파싱·포맷·사이트 집계
├── sites_config.json     # 검색 대상 사이트/게시판 DB
├── 커뮤니티_핫주제_실시간.md  # 리포트 원본 데이터
├── requirements.txt      # Python 의존성
├── build.bat             # 원클릭 빌드 스크립트
├── dangnagui.iss         # Inno Setup 인스톨러 스크립트
├── readme.txt            # 배포용 사용 설명서
└── README.md             # 개발자용 문서 (본 파일)
```

### 의존성

| 패키지 | 용도 |
|--------|------|
| `pyperclip` | 클립보드 복사 |
| `duckduckgo-search` | 토픽 추가 시 웹검색 |
| `lxml` | HTML 파싱 |
| `pyinstaller` | EXE 빌드 |

---

## 라이선스

오픈 프로젝트 — 누구나 자유롭게 사용 가능  
copyright by 챠리 (challychoi@me.com)
