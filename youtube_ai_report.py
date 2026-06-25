#!/usr/bin/env python3
"""
유튜브에서 특정 키워드(기본: "ai영상")로 검색하여
'어제 업로드된' 영상 중 인기(조회수) 상위 N개를 골라
마크다운 리포트로 정리해 주는 스크립트.

YouTube Data API v3를 사용합니다. (브라우저/스크래핑이 아니라 공식 API라
안정적이고 차단 위험이 적습니다.)

사용 전 준비
-----------
1. Google Cloud Console( https://console.cloud.google.com/ )에서
   프로젝트 생성 → "YouTube Data API v3" 사용 설정 → API 키 발급
2. 발급받은 키를 환경변수로 지정:
     export YOUTUBE_API_KEY="발급받은_키"
3. 의존성 설치:
     pip install requests

실행 예시
--------
  # 기본: "ai영상", 어제 업로드, 조회수순 상위 5개
  python youtube_ai_report.py

  # 키워드/개수 바꾸기
  python youtube_ai_report.py --query "ai 영상" --top 5

  # 특정 날짜(업로드일) 기준으로 보기 (YYYY-MM-DD, 로컬 시간대 기준)
  python youtube_ai_report.py --date 2026-06-24

  # 리포트를 파일로 저장
  python youtube_ai_report.py --out report.md
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:
    sys.exit("requests 패키지가 필요합니다. 먼저 'pip install requests' 를 실행하세요.")

API_BASE = "https://www.googleapis.com/youtube/v3"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='유튜브 키워드 검색 → 특정일 업로드 → 인기순 상위 N개 리포트'
    )
    p.add_argument("--query", default="ai영상", help='검색어 (기본: "ai영상")')
    p.add_argument("--top", type=int, default=5, help="상위 몇 개를 가져올지 (기본: 5)")
    p.add_argument(
        "--date",
        default=None,
        help="업로드 기준 날짜 YYYY-MM-DD (로컬시간). 미지정 시 '어제'.",
    )
    p.add_argument("--region", default="KR", help="지역 코드 (기본: KR)")
    p.add_argument("--lang", default="ko", help="관련성 언어 (기본: ko)")
    p.add_argument("--out", default=None, help="리포트를 저장할 파일 경로 (미지정 시 화면 출력)")
    p.add_argument(
        "--api-key",
        default=os.environ.get("YOUTUBE_API_KEY"),
        help="YouTube Data API 키 (또는 환경변수 YOUTUBE_API_KEY)",
    )
    return p.parse_args()


def target_day_bounds(date_str: str | None) -> tuple[datetime, datetime, datetime]:
    """대상 날짜의 [00:00, 다음날 00:00) 구간을 UTC로 반환. (시작, 끝, 로컬기준날짜)"""
    local_tz = datetime.now().astimezone().tzinfo
    if date_str:
        day_local = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=local_tz)
    else:
        day_local = (datetime.now(local_tz) - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    start_local = day_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
        start_local,
    )


def search_videos(key: str, query: str, start_utc: datetime, end_utc: datetime,
                  region: str, lang: str) -> list[str]:
    """검색 결과(해당 구간 업로드)에서 videoId 목록을 모은다. 페이지네이션 포함."""
    video_ids: list[str] = []
    page_token = None
    # 넉넉히 모아서 나중에 조회수로 정렬 (최대 ~200개)
    for _ in range(4):
        params = {
            "key": key,
            "part": "id",
            "q": query,
            "type": "video",
            "maxResults": 50,
            "order": "viewCount",  # API단에서도 조회수순 힌트
            "publishedAfter": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "publishedBefore": end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "regionCode": region,
            "relevanceLanguage": lang,
        }
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(f"{API_BASE}/search", params=params, timeout=30)
        _check(r)
        data = r.json()
        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid:
                video_ids.append(vid)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def fetch_video_details(key: str, ids: list[str]) -> list[dict]:
    """videoId 목록의 상세정보(제목/조회수/채널/설명 등)를 가져온다."""
    details: list[dict] = []
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        params = {
            "key": key,
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(chunk),
            "maxResults": 50,
        }
        r = requests.get(f"{API_BASE}/videos", params=params, timeout=30)
        _check(r)
        details.extend(r.json().get("items", []))
    return details


def _check(resp: requests.Response) -> None:
    if resp.status_code == 403:
        sys.exit(
            "API 요청이 거부되었습니다(403). API 키가 유효한지, "
            "'YouTube Data API v3'가 활성화되어 있는지, 일일 할당량이 남았는지 확인하세요.\n"
            f"응답: {resp.text[:300]}"
        )
    if not resp.ok:
        sys.exit(f"API 오류 {resp.status_code}: {resp.text[:300]}")


def summarize_description(desc: str, limit: int = 220) -> str:
    desc = " ".join((desc or "").split())
    if not desc:
        return "(설명 없음)"
    return desc if len(desc) <= limit else desc[:limit].rstrip() + "…"


def human_int(n: str | int) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return "N/A"


def build_report(query: str, day_local: datetime, videos: list[dict], top: int) -> str:
    lines: list[str] = []
    lines.append(f'# 유튜브 "{query}" 리포트')
    lines.append("")
    lines.append(f"- **검색어**: {query}")
    lines.append(f"- **업로드 기준일**: {day_local.strftime('%Y-%m-%d')} (해당일 00:00~24:00, 로컬 기준)")
    lines.append(f"- **정렬**: 조회수(인기) 내림차순 · 상위 {top}개")
    lines.append(f"- **생성 시각**: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}")
    lines.append("")

    if not videos:
        lines.append("> 해당 조건으로 업로드된 영상을 찾지 못했습니다. "
                     "검색어나 날짜를 바꿔 다시 시도해 보세요.")
        return "\n".join(lines)

    lines.append("## 요약 표")
    lines.append("")
    lines.append("| 순위 | 제목 | 채널 | 조회수 | 좋아요 | 링크 |")
    lines.append("|---|---|---|---|---|---|")
    for idx, v in enumerate(videos, 1):
        sn = v.get("snippet", {})
        st = v.get("statistics", {})
        title = sn.get("title", "(제목없음)").replace("|", "\\|")
        channel = sn.get("channelTitle", "?").replace("|", "\\|")
        url = f"https://youtu.be/{v.get('id')}"
        lines.append(
            f"| {idx} | {title} | {channel} | {human_int(st.get('viewCount'))} "
            f"| {human_int(st.get('likeCount'))} | [열기]({url}) |"
        )
    lines.append("")

    lines.append("## 영상별 상세 및 주요 내용")
    lines.append("")
    for idx, v in enumerate(videos, 1):
        sn = v.get("snippet", {})
        st = v.get("statistics", {})
        title = sn.get("title", "(제목없음)")
        url = f"https://youtu.be/{v.get('id')}"
        published = sn.get("publishedAt", "")
        lines.append(f"### {idx}. {title}")
        lines.append("")
        lines.append(f"- **채널**: {sn.get('channelTitle', '?')}")
        lines.append(f"- **업로드**: {published}")
        lines.append(
            f"- **조회수**: {human_int(st.get('viewCount'))} · "
            f"**좋아요**: {human_int(st.get('likeCount'))} · "
            f"**댓글**: {human_int(st.get('commentCount'))}"
        )
        lines.append(f"- **링크**: {url}")
        lines.append(f"- **주요 내용(설명 발췌)**: {summarize_description(sn.get('description', ''))}")
        lines.append("")
    lines.append("---")
    lines.append("*설명 발췌는 영상 작성자가 적은 설명란 기반 요약입니다. "
                 "정확한 영상 내용은 링크에서 확인하세요.*")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    if not args.api_key:
        sys.exit(
            "API 키가 없습니다. 환경변수 YOUTUBE_API_KEY 를 설정하거나 --api-key 로 전달하세요.\n"
            "키 발급: https://console.cloud.google.com/ → YouTube Data API v3 활성화 → 사용자 인증 정보 → API 키"
        )

    start_utc, end_utc, day_local = target_day_bounds(args.date)
    print(f"[1/3] '{args.query}' 검색 중 (업로드일 {day_local:%Y-%m-%d}) ...", file=sys.stderr)
    ids = search_videos(args.api_key, args.query, start_utc, end_utc, args.region, args.lang)
    print(f"      후보 {len(ids)}개 발견", file=sys.stderr)

    if not ids:
        report = build_report(args.query, day_local, [], args.top)
    else:
        print("[2/3] 상세정보/조회수 수집 중 ...", file=sys.stderr)
        details = fetch_video_details(args.api_key, ids)
        # 조회수 기준 내림차순 정렬 후 상위 N개
        details.sort(
            key=lambda v: int(v.get("statistics", {}).get("viewCount", 0) or 0),
            reverse=True,
        )
        top_videos = details[: args.top]
        print("[3/3] 리포트 생성 중 ...", file=sys.stderr)
        report = build_report(args.query, day_local, top_videos, args.top)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"리포트를 저장했습니다: {args.out}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
