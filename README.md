# 당나귀 게시판검색기 (dangnagui)

> 임금님귀 v1.3.2 · copyright by 챠리 (challychoi@me.com)

**국내 1,000+ 사이트 / 60,000+ 게시판** 실시간 분석 엔진.  
토픽별 핫키워드 · 네티즌 의견을 **DuckDuckGo 실시간 검색**으로 수집하여  
신문기사/보도자료 스타일의 리포트를 생성하는 Windows 데스크톱 앱.  
Microsoft Fluent 다크 UI · USB 포터블 · Windows 10/11 지원.

---

## v1.3.0 핵심 기능

### 대규모 사이트 DB — 1,000+ 사이트 / 60,000+ 게시판

- **3계층 자동 탐색 시스템**: 내장 시드 DB(200+) → API/파싱(52,000+ DC갤러리) → DuckDuckGo 동적 확장
- **암호화 파일 DB**: Fernet(AES-128-CBC + HMAC-SHA256) 암호화로 안전한 데이터 관리
- 네이버 카페, 디시인사이드, 클리앙, 루리웹, 뽐뿌 등 국내 주요 커뮤니티 + 80개 이상 뉴스 사이트 내장

### 광고/스팸 3중 필터링 엔진

| 계층 | 방식 | 설명 |
|------|------|------|
| Layer 1 | **키워드 블랙리스트** | 50+ 한국 커뮤니티 광고/스팸 키워드 자동 감지 |
| Layer 2 | **URL 패턴 필터** | 쇼핑 직링크, 단축URL, 제휴링크 15+ 패턴 차단 |
| Layer 3 | **스팸 스코어링** | 키워드 밀도 + URL + 특수문자 + 전화번호 + 가격 패턴 복합 점수제 (3점 이상 제거) |

오탐(false positive) 최소화 설계: 키워드 1개만으로는 제거되지 않아 정상 뉴스 보호

### 통계 대시보드 + PDF 내보내기

- **Buzz Score (회자 점수)**: 소스 다양성(30) + 검색 순위(25) + 토픽 관련도(25) + 최신성(20) = 0~100
- **6개 섹션 대시보드**: 검색 개요, Buzz Score 순위, 토픽별 비교, 필터링 분석, 도메인 TOP 15, 상세 테이블
- **PDF 리포트**: matplotlib 기반 4페이지 전문 통계 PDF 생성 (한글 폰트 자동 감지)

---

## 설치 방법

### 방법 1 — 인스톨러 (권장)

1. **[dangnagui-setup-v1.3.2.exe](https://github.com/azossy/dangnagui/releases/latest)** 다운로드
2. 다운로드한 파일을 더블클릭하여 실행
3. 설치 경로 선택 (기본: `C:\Program Files\dangnagui`)
4. "설치" 클릭 → 완료
5. 바탕화면 또는 시작 메뉴에서 **당나귀 게시판검색기** 실행

> **Windows SmartScreen 경고가 뜨는 경우** — 아래 [SmartScreen 안내](#smartscreen-안내) 참조

### 방법 2 — 포터블 ZIP (USB / 설치 없이 사용)

1. **[dangnagui-v1.3.2-portable.zip](https://github.com/azossy/dangnagui/releases/latest)** 다운로드
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
- **광고/스팸 3중 필터** — 키워드 블랙리스트 + URL 패턴 + 복합 스코어링으로 깨끗한 결과만 수집
- **1,000+ 사이트 DB** — 3계층 자동 탐색으로 국내 커뮤니티/뉴스 사이트 대규모 수집, 암호화 저장
- **통계 대시보드** — Buzz Score 순위, 필터링 효과, 도메인 분포 등 전문 통계 차트 + PDF 내보내기
- **언어 필터** — 한국어/영어 결과만 수집, 중국어·일본어 등 타국어 자동 배제
- **자동 번역** — 한국어 데이터 부족 시 영문 결과를 DuckDuckGo 번역으로 자동 한국어 변환
- **리포트 헤더 편집** — 설정에서 리포트 상단 헤더를 자유롭게 커스터마이즈
- **설정(⚙)** — 토픽 추가/삭제/순서 변경, 핫키워드 개수(1~10), 검색 기준 시간(30~100시간, 30/48/72/100 프리셋), 설정 내보내기/가져오기, 토픽당 최대 결과(50/100/200), PDF 기본 폴더
- **사이트 갱신** — 3계층 탐색(시드DB → API/파싱 → DDG)으로 사이트 DB 최신화, 암호화 자동 저장
- **리포트 저장(💾)** — 텍스트 파일로 저장
- **리포트 이력** — 최근 5개 이력, ◀ 이전 / 다음 ▶ 버튼으로 탐색
- **소셜 공유** — Facebook, X, 카카오톡, 텔레그램, 인스타그램, 디스코드

---

## 빌드 (배포용 EXE + 인스톨러)

```bash
build.bat
```

- PyInstaller → `dist\dangnagui\dangnagui.exe`
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) 설치 시 → `Output\dangnagui-setup-v1.3.2.exe` 자동 생성

### 프로젝트 구조

```
├── main.py               # 메인 GUI (진입점)
├── common.py             # 공통 상수 · 유틸 · 로깅
├── app_settings.py       # 설정 로드/저장, 3계층 사이트 탐색 연동
├── report_engine.py      # 실시간 검색 + 3중 필터 + 통계 수집 + 리포트 포맷
├── db_crypto.py          # 암호화 파일 DB (Fernet AES + zlib)
├── site_discovery.py     # 3계층 사이트 자동 탐색 (DC API + BS4 + DDG)
├── stats_engine.py       # 통계 엔진 (Buzz Score + 도메인 집계)
├── stats_window.py       # 통계 대시보드 UI (matplotlib + PDF)
├── korean_sites_seed.json # 내장 시드 DB (200+ 사이트 + 80+ 뉴스)
├── dangnagui.ico         # 앱 아이콘 (투명 배경)
├── requirements.txt      # Python 의존성
├── build.bat             # 원클릭 빌드 스크립트
├── dangnagui.iss         # Inno Setup 인스톨러 스크립트
├── readme.txt            # 배포용 사용 설명서
└── README.md             # 개발자용 문서 (본 파일)
```

### 의존성

| 패키지 | 용도 | 라이선스 |
|--------|------|----------|
| `pyperclip` | 클립보드 복사 | BSD |
| `duckduckgo-search` | 실시간 웹검색 + 번역 | MIT |
| `lxml` | HTML 파싱 | BSD |
| `cryptography` | Fernet 암호화 (AES-128-CBC) | Apache 2.0 / BSD |
| `beautifulsoup4` | 게시판 목록 HTML 파싱 | MIT |
| `requests` | HTTP 요청 | Apache 2.0 |
| `matplotlib` | 통계 차트 + PDF 생성 | BSD (PSF compatible) |
| `pyinstaller` | EXE 빌드 | GPL (빌드 도구, 런타임 제한 없음) |

---

## SmartScreen 안내

설치 파일 실행 시 **"Windows의 PC 보호"** 파란색 경고 화면이 나타날 수 있습니다.

**왜 나타나나요?**
- 코드 서명 인증서가 아직 적용되지 않은 프로그램에 공통적으로 나타나는 Windows 정상 경고입니다.
- 본 프로그램은 악성코드와 무관하며, 전체 소스코드가 이 GitHub 저장소에 공개되어 있습니다.

**해결 방법:**
1. 파란 화면에서 **"추가 정보"** 텍스트를 클릭합니다.
2. 하단에 나타나는 **"실행"** 버튼을 클릭합니다.

> 코드 서명 인증서 적용은 향후 업데이트에서 진행 예정입니다.

---

## 변경 이력

### v1.3.2
- **검색 기준 시간 프리셋**: 30h / 48h / 72h / 100h 버튼으로 빠른 설정
- **설정 내보내기/가져오기**: JSON으로 설정 백업·복원
- **토픽당 최대 결과**: 제한없음 / 50 / 100 / 200 옵션
- **리포트 이력**: 최근 5개 이력, ◀ 이전 / 다음 ▶ 버튼으로 탐색
- **PDF 기본 폴더**: 설정에서 통계 PDF 저장 경로 지정
- UI 개선: 상태바, 툴팁, 진행률 %, 설정 구역 구분선, 데이터 없음 안내

### v1.3.1
- QA 개선: 단축키·검색 리셋·예외 로깅·설정 잠금·스팸 키워드 정리
- SmartScreen 대응: VersionInfo 메타데이터, 문서 안내 보강

### v1.3.0
- **1,000+ 사이트 / 60,000+ 게시판**: 3계층 자동 탐색 시스템 (시드DB → DC API 52K갤러리 → DDG 확장)
- **암호화 파일 DB**: Fernet(AES-128-CBC + HMAC-SHA256)으로 사이트 데이터 암호화 저장
- **광고/스팸 3중 필터**: 키워드 블랙리스트 + URL 패턴 + 복합 스코어링 (오탐 최소화)
- **통계 대시보드**: Buzz Score 순위, 6개 섹션 차트, PDF 내보내기 (matplotlib)
- **site: 타겟 검색**: 알려진 주요 사이트에서 직접 검색하여 결과 품질 향상
- 전체 코드 리팩토링 및 주석 강화

### v1.2.4
- 앱 아이콘 투명 배경으로 수정
- 검색 결과 언어 필터링 (한국어/영어만, 중국어·일본어 배제)
- 한국어 데이터 부족 시 영문 결과 자동 번역 (DuckDuckGo Translate)
- 리포트 헤더 사용자 편집 기능 (설정 UI)

### v1.2.3
- 앱 아이콘 추가 (당나귀 캐릭터)
- README/readme.txt 상세 설치 안내

### v1.2.2
- Inno Setup 인스톨러 빌드 포함

---

## 라이선스

오픈 프로젝트 — 누구나 자유롭게 사용 가능  
copyright by 챠리 (challychoi@me.com)
