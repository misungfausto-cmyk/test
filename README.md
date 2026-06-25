# test

## youtube_ai_report.py — 유튜브 키워드 인기 영상 리포트

유튜브에서 키워드(기본: `ai영상`)로 검색해 **특정일(기본: 어제)에 업로드된** 영상 중
**조회수(인기) 상위 N개**를 골라 마크다운 리포트로 정리합니다.
브라우저 스크래핑이 아니라 **YouTube Data API v3**를 사용해 안정적입니다.

### 준비

1. [Google Cloud Console](https://console.cloud.google.com/) 에서
   프로젝트 생성 → **YouTube Data API v3** 활성화 → **API 키** 발급
2. 키를 환경변수로 설정하고 의존성 설치:
   ```bash
   export YOUTUBE_API_KEY="발급받은_키"
   pip install requests
   ```

### 사용법

```bash
# 기본: "ai영상", 어제 업로드, 조회수순 상위 5개 → 화면 출력
python youtube_ai_report.py

# 파일로 저장
python youtube_ai_report.py --out report.md

# 검색어/개수/날짜 변경
python youtube_ai_report.py --query "ai 영상" --top 5 --date 2026-06-24
```

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--query` | 검색어 | `ai영상` |
| `--top` | 상위 개수 | `5` |
| `--date` | 업로드 기준일 `YYYY-MM-DD` (로컬시간) | 어제 |
| `--region` | 지역 코드 | `KR` |
| `--lang` | 관련성 언어 | `ko` |
| `--out` | 저장 파일 경로 | (화면 출력) |

> 참고: 이 스크립트는 유튜브에 접속 가능한 네트워크 환경(예: 본인 PC)에서 실행하세요.
> 결과는 영상 설명란 기반 요약이며, 정확한 내용은 각 영상 링크에서 확인하시기 바랍니다.
