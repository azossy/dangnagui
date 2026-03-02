# 당나귀 게시판검색기 (dangnagui)

> 임금님귀 v1.2.3 · copyright by 챠리 (challychoi@me.com)

토픽별 핫키워드 · 네티즌 의견을 **DuckDuckGo 실시간 검색**으로 수집하여  
메신저 스타일 리포트를 생성하는 Windows 데스크톱 앱.  
Microsoft Fluent 다크 UI · USB 포터블 · Windows 10/11 지원.

---

## 설치 방법

### 방법 1 — 인스톨러 (권장)

1. **[dangnagui-setup-v1.2.3.exe](https://github.com/azossy/dangnagui/releases/latest)** 다운로드
2. 다운로드한 파일을 더블클릭하여 실행
3. 설치 경로 선택 (기본: `C:\Program Files\dangnagui`)
4. "설치" 클릭 → 완료
5. 바탕화면 또는 시작 메뉴에서 **당나귀 게시판검색기** 실행

> Windows SmartScreen 경고가 뜨면 "추가 정보" → "실행" 클릭

### 방법 2 — 포터블 ZIP (USB / 설치 없이 사용)

1. **[dangnagui-v1.2.3-portable.zip](https://github.com/azossy/dangnagui/releases/latest)** 다운로드
2. 원하는 위치(USB, 바탕화면 등)에 압축 해제
3. 폴더 안의 `dangnagui.exe` 실행

> 설정 파일이 exe와 같은 폴더에 저장되므로 USB에 담아 어디서든 사용 가능

### 방법 3 — Python 소스에서 실행 (개발자용)

```bash
git clone https://github.com/azossy/dangnagui.git
cd dangnagui
pip install -r requirements.txt
python main.py
```

---

## 주요 기능

- **스타트** — 설정된 토픽 · 시간 기준으로 DuckDuckGo 실시간 검색, 리포트 생성 + 클립보드 자동 복사
- **설정(⚙)** — 토픽 추가/삭제/순서 변경, 핫키워드 개수(1~10), 검색 기준 시간(30~100시간)
- **사이트 갱신** — 토픽별 관련 사이트 · 게시판을 DuckDuckGo 웹검색으로 최신화
- **리포트 저장(💾)** — 텍스트 파일로 저장
- **소셜 공유** — Facebook, X, 카카오톡, 텔레그램, 인스타그램, 디스코드

---

## 스크린샷

실행 화면 (다크 모드 Fluent UI):

```
┌─────────────────────────────────────┐
│  게시판 검색기    임금님귀 v1.2.3 🇰🇷 │
│  토픽별 핫키워드 · 실시간 리포트      │
│                                     │
│  [ ▶ 스타트 ] [ 📋 복사 ] [ 💾 저장 ] │
│                                     │
│  ✦ 게시판 검색기                     │
│    2026년 03월 02일 기준              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━            │
│  • 📈 주식                           │
│    · 더본코리아 (뽐뿌)               │
│    · 쿠팡 매출 근황                   │
│  • 🤖 IT AI                          │
│    · GPT-4.5                         │
│    · Claude 3.7 Sonnet               │
│  ...                                │
└─────────────────────────────────────┘
```

---

## 빌드 (배포용 EXE + 인스톨러)

```bash
build.bat
```

- PyInstaller → `dist\dangnagui\dangnagui.exe`
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) 설치 시 → `Output\dangnagui-setup-v1.2.3.exe` 자동 생성

### 프로젝트 구조

```
├── main.py               # 메인 GUI (진입점)
├── common.py             # 공통 상수 · 유틸 · 로깅
├── app_settings.py       # 설정 로드/저장, 웹검색 연동
├── report_engine.py      # 실시간 검색 + 리포트 포맷
├── dangnagui.ico         # 앱 아이콘
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
| `duckduckgo-search` | 실시간 웹검색 + 토픽 사이트 탐색 |
| `lxml` | HTML 파싱 |
| `pyinstaller` | EXE 빌드 |

---

## 라이선스

오픈 프로젝트 — 누구나 자유롭게 사용 가능  
copyright by 챠리 (challychoi@me.com)
