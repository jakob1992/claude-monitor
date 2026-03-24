# Claude Code Monitor

실시간 터미널 대시보드 — Claude Code의 토큰 사용량, 비용, 세션 현황을 한눈에 확인합니다.

```
Claude Code Monitor                              14:32:05
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  COST           TOKENS         SESSIONS      ACTIVE
  $6.20 ⚠        1.8M           12            3h 20m

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Token Usage          Threshold: Input 500K / Output 200K
  Input   ████████████████░░░░   800K    62%
  Output  ██████░░░░░░░░░░░░░░   150K    31%
  Cache   ██░░░░░░░░░░░░░░░░░░    50K     7%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Top Sessions by Cost
   #   Session        Cost     Tokens   Chart
   1   abc12345…    $ 3.10     900K     ████████████
   2   def45678…    $ 2.10     600K     ████████

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  +1,234 added   -456 removed   12 commits   2 PRs
  Model: sonnet-4-6
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 [r] Refresh  [q] Quit                  Updated: 14:32:05
```

*(스크린샷 추후 업데이트 예정)*

---

## 요구 사항

- macOS (Linux도 동작하지만 미테스트)
- Python 3.9+
- Claude Code CLI

## 빠른 설치

```bash
curl -fsSL https://raw.githubusercontent.com/yourusername/claude-monitor/main/install.sh | bash
```

## 수동 설치

```bash
git clone https://github.com/yourusername/claude-monitor.git ~/claude-monitor
cd ~/claude-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`~/.zshrc`에 alias 추가:

```bash
alias ccm='source ~/claude-monitor/.venv/bin/activate && python ~/claude-monitor/monitor.py'
```

## Claude Code 텔레메트리 활성화

`~/.claude/settings.json`의 `env` 섹션에 아래 항목 추가:

```json
{
  "env": {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "prometheus",
    "OTEL_EXPORTER_PROMETHEUS_PORT": "9464"
  }
}
```

## 실행

```bash
ccm
```

키보드 단축키: `r` — 즉시 갱신 / `q` — 종료

## 임계값 설정

`monitor.py` 상단의 `THRESHOLDS` 딕셔너리를 직접 편집:

```python
THRESHOLDS = {
    "input_tokens":  500_000,   # 기본: 50만
    "output_tokens": 200_000,   # 기본: 20만
    "cost_usd":      5.0,       # 기본: $5
}
```

임계값 80% 이상 → 노란색 경고 / 100% 이상 → 빨간색 + ⚠

## 라이선스

MIT
