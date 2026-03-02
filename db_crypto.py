#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
게시판 검색기 — 암호화 파일 DB 모듈 (db_crypto.py)
═══════════════════════════════════════════════════════
Fernet(AES-128-CBC + HMAC-SHA256) 대칭 암호화를 사용하여
사이트/게시판 데이터를 안전하게 저장·로드합니다.

■ 암호화 흐름:
  dict → JSON 문자열 → zlib 압축 → Fernet 암호화 → .enc 파일

■ 복호화 흐름:
  .enc 파일 → Fernet 복호화 → zlib 해제 → JSON 파싱 → dict

■ 키 파생:
  머신 고유값(hostname + machine type) + 앱 시크릿 문자열을
  SHA-256으로 해시하여 Fernet 호환 32바이트 키를 생성합니다.
  같은 PC에서는 항상 동일한 키가 생성되므로 별도 키 파일 불필요.

■ 라이선스:
  cryptography 라이브러리 — Apache 2.0 / BSD 듀얼 (상용 자유)

copyright by 챠리 (challychoi@me.com)
"""
from __future__ import annotations

import json
import zlib
import hashlib
import base64
import platform
import tempfile
import os
from pathlib import Path
from typing import Any

from common import log, BASE

# ═══════════════════════════════════════════════════
#  cryptography 라이브러리 로딩 (선택적 의존성)
#  설치되지 않은 경우 평문 JSON 폴백으로 동작
# ═══════════════════════════════════════════════════
_HAS_CRYPTO = True
try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    _HAS_CRYPTO = False
    InvalidToken = Exception  # type: ignore[misc]
    log.warning(
        "cryptography 미설치 — 암호화 DB 비활성. "
        "pip install cryptography 로 설치하세요."
    )

# ═══════════════════════════════════════════════════
#  암호화 DB 파일 경로 상수
# ═══════════════════════════════════════════════════
# 암호화된 사이트 DB 파일 (.enc 확장자)
SITES_DB_ENC = BASE / "sites_db.enc"

# 평문 시드 DB (앱 배포 시 포함, 첫 실행 / 폴백용)
SITES_SEED_FILE = BASE / "korean_sites_seed.json"

# 앱 고유 시크릿 (키 파생에 사용, 코드 내장)
_APP_SECRET = "dangnagui-board-searcher-v1.3-charly"


# ═══════════════════════════════════════════════════
#  키 파생 (Key Derivation)
# ═══════════════════════════════════════════════════
def derive_db_key() -> bytes:
    """
    머신 고유 식별자 + 앱 시크릿으로 Fernet 호환 암호화 키를 파생합니다.

    ■ 동작 원리:
      1. platform.node() → 컴퓨터 호스트명 (예: "DESKTOP-ABC123")
      2. platform.machine() → CPU 아키텍처 (예: "AMD64")
      3. 위 값 + 앱 시크릿을 결합하여 SHA-256 해시 생성
      4. 해시 결과(32바이트)를 base64 URL-safe 인코딩 → Fernet 키

    ■ 특징:
      - 같은 PC에서는 항상 동일한 키 → 별도 키 파일 보관 불필요
      - 다른 PC로 이동 시 키가 달라짐 → 시드DB로 자동 폴백
      - 키 자체는 메모리에서만 존재, 파일로 저장하지 않음

    Returns:
        bytes: Fernet 호환 44바이트 base64 인코딩 키
    """
    # 머신 고유 정보 수집 (호스트명 + CPU 아키텍처)
    machine_id = platform.node() + "|" + platform.machine()

    # 앱 시크릿과 결합하여 원본 문자열 생성
    raw_material = f"{machine_id}:{_APP_SECRET}"

    # SHA-256 해시로 정확히 32바이트 키 소재 생성
    key_bytes = hashlib.sha256(raw_material.encode("utf-8")).digest()

    # Fernet은 base64 URL-safe 인코딩된 32바이트 키를 요구
    fernet_key = base64.urlsafe_b64encode(key_bytes)

    return fernet_key


# ═══════════════════════════════════════════════════
#  암호화 저장 (Save)
# ═══════════════════════════════════════════════════
def save_encrypted_db(data: dict, path: Path | None = None) -> bool:
    """
    딕셔너리 데이터를 암호화하여 파일로 저장합니다.

    ■ 처리 순서:
      1. dict → JSON 문자열 (ensure_ascii=False, 한글 그대로)
      2. JSON 바이트 → zlib 압축 (level=6, 속도/크기 균형)
      3. 압축 데이터 → Fernet 암호화
      4. 암호화 데이터 → 원자적 파일 쓰기 (임시파일 → rename)

    ■ 안전 장치:
      - 기존 파일이 있으면 .bak 백업 생성
      - 임시 파일에 먼저 쓰고 rename → 중간 실패 시 원본 보존
      - cryptography 미설치 시 평문 JSON으로 폴백 저장

    Args:
        data: 저장할 딕셔너리 (사이트 DB 전체)
        path: 저장 경로 (기본값: SITES_DB_ENC)

    Returns:
        bool: 저장 성공 여부
    """
    if path is None:
        path = SITES_DB_ENC

    path = Path(path)

    try:
        # Step 1: dict → JSON 문자열 → UTF-8 바이트
        json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        raw_bytes = json_str.encode("utf-8")

        if _HAS_CRYPTO:
            # Step 2: zlib 압축 (level=6: 속도/크기 최적 균형)
            compressed = zlib.compress(raw_bytes, level=6)
            log.debug(
                "DB 압축: %s → %s (%.1f%% 절감)",
                _fmt_size(len(raw_bytes)),
                _fmt_size(len(compressed)),
                (1 - len(compressed) / max(len(raw_bytes), 1)) * 100,
            )

            # Step 3: Fernet 암호화
            key = derive_db_key()
            encrypted = Fernet(key).encrypt(compressed)

            # Step 4: 원자적 파일 쓰기 (바이너리)
            _atomic_write_bytes(path, encrypted)
            log.info(
                "암호화 DB 저장 완료: %s (%s)",
                path.name, _fmt_size(len(encrypted)),
            )
        else:
            # cryptography 미설치 — 평문 JSON으로 폴백
            fallback_path = path.with_suffix(".json")
            _atomic_write_bytes(fallback_path, raw_bytes)
            log.warning(
                "cryptography 미설치 → 평문 JSON 저장: %s", fallback_path.name
            )

        return True

    except Exception as e:
        log.error("암호화 DB 저장 실패: %s", e)
        return False


# ═══════════════════════════════════════════════════
#  복호화 로드 (Load)
# ═══════════════════════════════════════════════════
def load_encrypted_db(path: Path | None = None) -> dict:
    """
    암호화된 파일 DB를 복호화하여 딕셔너리로 반환합니다.

    ■ 폴백 전략 (우선순위):
      1. 암호화 DB 파일 (sites_db.enc) → 복호화 시도
      2. 복호화 실패 시 → 평문 폴백 파일 (sites_db.json) 시도
      3. 둘 다 없으면 → 시드 DB (korean_sites_seed.json) 로드
      4. 시드 DB도 없으면 → 빈 딕셔너리 반환

    ■ 복호화 실패 원인:
      - 다른 PC에서 생성된 .enc 파일 (키 불일치)
      - 파일 손상
      - cryptography 미설치

    Args:
        path: 로드 경로 (기본값: SITES_DB_ENC)

    Returns:
        dict: 사이트 DB 딕셔너리 (빈 dict 가능)
    """
    if path is None:
        path = SITES_DB_ENC

    path = Path(path)

    # ── 시도 1: 암호화 DB 파일 로드 ──
    if path.exists() and _HAS_CRYPTO:
        try:
            encrypted = path.read_bytes()
            key = derive_db_key()

            # Fernet 복호화
            compressed = Fernet(key).decrypt(encrypted)

            # zlib 압축 해제
            raw_bytes = zlib.decompress(compressed)

            # JSON 파싱
            data = json.loads(raw_bytes.decode("utf-8"))
            log.info(
                "암호화 DB 로드 성공: %s (%s → %s 복원)",
                path.name,
                _fmt_size(len(encrypted)),
                _fmt_size(len(raw_bytes)),
            )
            return data

        except InvalidToken:
            # 키 불일치 (다른 PC에서 생성된 파일)
            log.warning(
                "암호화 DB 키 불일치 — 다른 PC에서 생성된 파일일 수 있습니다. "
                "시드 DB로 폴백합니다."
            )
        except zlib.error as e:
            log.error("암호화 DB zlib 해제 실패: %s", e)
        except json.JSONDecodeError as e:
            log.error("암호화 DB JSON 파싱 실패: %s", e)
        except Exception as e:
            log.error("암호화 DB 로드 실패: %s", e)

    # ── 시도 2: 평문 폴백 파일 (cryptography 미설치 시 저장된 파일) ──
    fallback_json = path.with_suffix(".json")
    if fallback_json.exists():
        try:
            data = json.loads(fallback_json.read_text(encoding="utf-8"))
            log.info("평문 폴백 DB 로드: %s", fallback_json.name)
            return data
        except Exception as e:
            log.error("평문 폴백 DB 로드 실패: %s", e)

    # ── 시도 3: 시드 DB (앱 배포 시 포함된 초기 데이터) ──
    if SITES_SEED_FILE.exists():
        try:
            data = json.loads(SITES_SEED_FILE.read_text(encoding="utf-8"))
            log.info("시드 DB 로드 (초기 데이터): %s", SITES_SEED_FILE.name)
            return data
        except Exception as e:
            log.error("시드 DB 로드 실패: %s", e)

    # ── 시도 4: 모두 실패 — 빈 딕셔너리 ──
    log.warning("사용 가능한 사이트 DB 없음 — 빈 상태로 시작")
    return {}


# ═══════════════════════════════════════════════════
#  DB 무결성 검증
# ═══════════════════════════════════════════════════
def verify_db_integrity(data: dict) -> tuple[bool, str]:
    """
    사이트 DB의 기본 무결성을 검증합니다.

    ■ 검증 항목:
      - 필수 키 존재 여부 (meta, sites)
      - meta.version 존재
      - sites가 리스트인지
      - 사이트 항목에 최소 필수 필드 존재 (id, name, domain)

    Args:
        data: 검증할 사이트 DB 딕셔너리

    Returns:
        tuple[bool, str]: (통과 여부, 결과 메시지)
    """
    if not isinstance(data, dict):
        return False, "DB가 딕셔너리가 아닙니다"

    # meta 섹션 검증
    meta = data.get("meta")
    if not isinstance(meta, dict):
        return False, "meta 섹션이 없거나 올바르지 않습니다"

    if "version" not in meta:
        return False, "meta.version이 없습니다"

    # sites 섹션 검증
    sites = data.get("sites")
    if not isinstance(sites, list):
        return False, "sites 섹션이 리스트가 아닙니다"

    if len(sites) == 0:
        return False, "sites가 비어 있습니다"

    # 첫 10개 사이트 샘플 검증
    required_fields = {"id", "name", "domain"}
    for i, site in enumerate(sites[:10]):
        if not isinstance(site, dict):
            return False, f"sites[{i}]가 딕셔너리가 아닙니다"
        missing = required_fields - set(site.keys())
        if missing:
            return False, f"sites[{i}]에 필수 필드 누락: {missing}"

    total_sites = len(sites)
    total_boards = sum(
        len(s.get("boards", []))
        for s in sites
        if isinstance(s, dict)
    )

    return True, f"검증 통과: {total_sites:,}개 사이트, {total_boards:,}개 게시판"


# ═══════════════════════════════════════════════════
#  DB 통계 요약
# ═══════════════════════════════════════════════════
def get_db_summary(data: dict) -> dict:
    """
    사이트 DB의 통계 요약을 반환합니다.
    UI 표시용 및 로깅용으로 사용.

    Returns:
        dict: {
            "total_sites": int,
            "total_boards": int,
            "categories": dict[str, int],  # 카테고리별 사이트 수
            "has_dc_galleries": bool,
            "news_sites": int,
        }
    """
    sites = data.get("sites", [])
    total_boards = 0
    categories: dict[str, int] = {}

    for s in sites:
        if not isinstance(s, dict):
            continue
        boards = s.get("boards", [])
        total_boards += len(boards) if isinstance(boards, list) else 0

        cat = s.get("category", "기타")
        categories[cat] = categories.get(cat, 0) + 1

    has_dc = any(
        s.get("id") == "dcinside" or s.get("domain", "").endswith("dcinside.com")
        for s in sites
        if isinstance(s, dict)
    )

    news_sites = data.get("news_sites", [])

    return {
        "total_sites": len(sites),
        "total_boards": total_boards,
        "categories": categories,
        "has_dc_galleries": has_dc,
        "news_sites": len(news_sites) if isinstance(news_sites, list) else 0,
    }


# ═══════════════════════════════════════════════════
#  내부 유틸리티
# ═══════════════════════════════════════════════════
def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """
    바이너리 데이터를 원자적으로 파일에 씁니다.
    임시 파일에 먼저 쓰고 rename하여 중간 실패 시 원본을 보존합니다.

    ■ 안전 장치:
      1. 기존 파일이 있으면 .bak 백업 생성
      2. 임시 파일 생성 → 데이터 쓰기
      3. os.replace()로 원자적 이름 변경
      4. 실패 시 임시 파일 정리
    """
    path = Path(path)

    # 기존 파일 백업
    if path.exists():
        bak = path.with_suffix(path.suffix + ".bak")
        try:
            bak.write_bytes(path.read_bytes())
        except Exception as e:
            log.warning("DB 백업 실패 (%s): %s", path.name, e)

    # 임시 파일에 쓰기 → 원자적 교체
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, data)
        os.close(fd)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _fmt_size(size_bytes: int) -> str:
    """바이트 크기를 사람이 읽기 쉬운 형태로 변환 (예: 1.5MB)"""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
