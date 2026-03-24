"""Claude Code Usage Monitor - 실시간 터미널 대시보드

~/.claude/projects/**/*.jsonl 파싱으로 세션별 사용량을 표시합니다.
별도 설정 없이 Claude Code가 저장하는 대화 로그를 직접 읽습니다.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widgets import Footer, Header, Rule, Static

PROJECTS_DIR = Path.home() / ".claude" / "projects"
REFRESH_INTERVAL = 10  # seconds

# ---------------------------------------------------------------------------
# 임계값 설정 (일별 기준) — 직접 편집으로 조정
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "input_tokens":  500_000,
    "output_tokens": 200_000,
    "cost_usd":      5.0,
}

# ---------------------------------------------------------------------------
# 모델별 단가 (per 1M tokens): (input, output, cache_write, cache_read)
# ---------------------------------------------------------------------------
MODEL_PRICING: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-4-6":           (15.00, 75.00, 18.75, 1.50),
    "claude-opus-4-5":           (15.00, 75.00, 18.75, 1.50),
    "claude-sonnet-4-6":         ( 3.00, 15.00,  3.75, 0.30),
    "claude-sonnet-4-5":         ( 3.00, 15.00,  3.75, 0.30),
    "claude-haiku-4-5":          ( 0.80,  4.00,  1.00, 0.08),
    "claude-haiku-4-5-20251001": ( 0.80,  4.00,  1.00, 0.08),
}
_DEFAULT_PRICING = (3.00, 15.00, 3.75, 0.30)


# ---------------------------------------------------------------------------
# JSONL 파서
# ---------------------------------------------------------------------------

_session_cache: dict[str, tuple[float, dict]] = {}  # path → (mtime, data)


def _ts_to_local_date(ts: str) -> str:
    """UTC ISO 타임스탬프 → 로컬 날짜 'YYYY-MM-DD'."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _calc_cost(model: str, inp: int, out: int, cw: int, cr: int) -> float:
    p = MODEL_PRICING.get(model, _DEFAULT_PRICING)
    return (inp * p[0] + out * p[1] + cw * p[2] + cr * p[3]) / 1_000_000


def _project_label(cwd: str) -> str:
    """cwd → 읽기 쉬운 프로젝트 레이블."""
    home = str(Path.home())
    rel  = cwd[len(home):].lstrip("/") if cwd.startswith(home) else cwd

    if not rel:
        return "~"

    # worktree: path/.claude/worktrees/{name}
    if "/.claude/worktrees/" in rel:
        proj, wt = rel.split("/.claude/worktrees/", 1)
        return f"{Path(proj).name}/{wt}"

    # 일반 프로젝트: 마지막 2개 컴포넌트
    parts = Path(rel).parts
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1] if parts else rel


def _parse_file(path: Path) -> dict | None:
    """
    JSONL 파일 파싱 → 날짜별 집계 포함 세션 dict.
    daily: { 'YYYY-MM-DD': {cost, input, output, cache_write, cache_read, turns} }
    """
    daily: dict[str, dict] = defaultdict(lambda: dict(cost=0.0, input=0, output=0,
                                                        cache_write=0, cache_read=0, turns=0))
    models: dict[str, int] = defaultdict(int)
    timestamps: list[str] = []
    cwd = ""

    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not cwd and entry.get("cwd"):
                    cwd = entry["cwd"]

                if entry.get("type") != "assistant":
                    continue
                msg = entry.get("message")
                if not isinstance(msg, dict):
                    continue
                usage = msg.get("usage")
                if not usage:
                    continue

                model = msg.get("model", "unknown")
                i   = int(usage.get("input_tokens", 0))
                o   = int(usage.get("output_tokens", 0))
                cw  = int(usage.get("cache_creation_input_tokens", 0))
                cr  = int(usage.get("cache_read_input_tokens", 0))
                ts  = entry.get("timestamp", "")
                date = _ts_to_local_date(ts) if ts else ""

                if date:
                    d = daily[date]
                    d["cost"]        += _calc_cost(model, i, o, cw, cr)
                    d["input"]       += i
                    d["output"]      += o
                    d["cache_write"] += cw
                    d["cache_read"]  += cr
                    d["turns"]       += 1

                models[model] += 1
                if ts:
                    timestamps.append(ts)

    except Exception:
        return None

    if not daily:
        return None

    timestamps.sort()

    return {
        "session_id": path.stem,
        "project":    _project_label(cwd),
        "daily":      dict(daily),
        "models":     dict(models),
        "first_ts":   timestamps[0]  if timestamps else "",
        "last_ts":    timestamps[-1] if timestamps else "",
    }


def load_sessions() -> list[dict]:
    """전체 세션 로드. 변경 없는 파일은 캐시 재사용."""
    sessions: list[dict] = []
    for path in PROJECTS_DIR.glob("*/*.jsonl"):
        key = str(path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        cached = _session_cache.get(key)
        if cached and cached[0] == mtime:
            sessions.append(cached[1])
            continue
        data = _parse_file(path)
        if data:
            _session_cache[key] = (mtime, data)
            sessions.append(data)
    return sessions


# ---------------------------------------------------------------------------
# 포맷 헬퍼
# ---------------------------------------------------------------------------

def fmt_tokens(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(n))


def fmt_duration(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m = rem // 60
    return f"{h}h {m}m" if h > 0 else f"{m}m"


def _seconds_ago(ts_str: str) -> float:
    """UTC ISO 타임스탬프 → 현재로부터 경과 초."""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except Exception:
        return float("inf")


def fmt_ago(ts_str: str) -> str:
    try:
        dt  = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        s   = int(diff.total_seconds())
        if s < 60:   return f"{s}s ago"
        if s < 3600: return f"{s // 60}m ago"
        return f"{s // 3600}h ago"
    except Exception:
        return ""


def make_bar(value: float, total: float, width: int = 20) -> str:
    pct    = value / total if total > 0 else 0.0
    filled = int(min(pct, 1.0) * width)
    bar    = "█" * filled + "░" * (width - filled)
    if pct >= 1.0:  return f"[red]{bar}[/red]"
    if pct >= 0.8:  return f"[yellow]{bar}[/yellow]"
    return f"[green]{bar}[/green]"


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class SummaryCard(Static):
    DEFAULT_CSS = """
    SummaryCard {
        border: solid $primary;
        padding: 0 1;
        height: 4;
        width: 1fr;
        content-align: center middle;
        text-align: center;
    }
    """

    def set_card(self, label: str, value: str, value_style: str = "bold") -> None:
        # height:3 → border(1) + label(1) + value(1)
        self.update(f"[dim]{label}[/dim]\n[{value_style}]{value}[/{value_style}]")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class Dashboard(App):
    CSS = """
    Screen { background: $surface; }

    #summary-row  { height: 4; }
    #token-header { padding: 0 2; color: $text-muted; height: 1; }
    .tok-row      { height: 2; padding: 0 2; }
    #session-table { padding: 0 2; }
    #bottom-bar   { height: 1; color: $text-muted; padding: 0 2; }
    """

    BINDINGS = [
        ("q", "quit",    "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal(id="summary-row"):
                yield SummaryCard(id="card-cost")
                yield SummaryCard(id="card-tokens")
                yield SummaryCard(id="card-sessions")
            yield Rule()
            yield Static("", id="token-header")
            yield Static("", id="tok-input",  classes="tok-row")
            yield Static("", id="tok-output", classes="tok-row")
            yield Static("", id="tok-cache",  classes="tok-row")
            yield Rule()
            yield Static("", id="session-table")
            yield Rule()
            yield Static("", id="bottom-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Claude Code Monitor"
        self.refresh_metrics()
        self.set_interval(REFRESH_INTERVAL, self.refresh_metrics)

    def action_refresh(self) -> None:
        self.refresh_metrics()

    def refresh_metrics(self) -> None:
        all_sessions = load_sessions()
        now          = datetime.now()
        today        = now.strftime("%Y-%m-%d")
        month_prefix = now.strftime("%Y-%m")
        now_str      = now.strftime("%H:%M:%S")
        self.sub_title = now_str

        # 오늘 / 이번달 활동 세션
        today_sessions = [s for s in all_sessions if today in s["daily"]]
        month_sessions = [s for s in all_sessions
                          if any(d.startswith(month_prefix) for d in s["daily"])]

        if not today_sessions:
            for cid, lbl in [("card-cost","COST"),("card-tokens","TOKENS"),("card-sessions","SESSIONS")]:
                self._card(cid).set_card(lbl, "[dim]--[/dim]")
            for w in ("token-header","tok-input","tok-output","tok-cache","session-table"):
                self._set(w, "")
            self._set("bottom-bar",
                f"[dim]No activity today — {len(all_sessions)} total sessions[/dim]   Updated: {now_str}")
            return

        # --- 오늘 합계 ---
        def day_sum(key: str) -> float:
            return sum(s["daily"][today][key] for s in today_sessions)

        today_cost    = day_sum("cost")
        today_input   = day_sum("input")
        today_output  = day_sum("output")
        today_cache_w = day_sum("cache_write")
        today_cache_r = day_sum("cache_read")
        today_cache   = today_cache_w + today_cache_r
        today_tokens  = today_input + today_output + today_cache

        # --- 이번달 합계 ---
        def month_sum(key: str) -> float:
            return sum(
                v[key]
                for s in month_sessions
                for d, v in s["daily"].items()
                if d.startswith(month_prefix)
            )

        month_cost   = month_sum("cost")
        month_input  = month_sum("input")
        month_output = month_sum("output")
        month_cache  = month_sum("cache_write") + month_sum("cache_read")
        month_tokens = month_input + month_output + month_cache

        # --- COST 카드: 오늘 / 이번달 ---
        thr = THRESHOLDS["cost_usd"]
        if today_cost >= thr * 2:
            cost_style = "red bold"
        elif today_cost >= thr:
            cost_style = "yellow bold"
        else:
            cost_style = "bold"
        self._card("card-cost").set_card(
            "COST (equiv.)", f"${today_cost:.2f} / ${month_cost:.2f}", cost_style,
        )

        # --- TOKENS 카드: 오늘 / 이번달 ---
        self._card("card-tokens").set_card(
            "TOKENS", f"{fmt_tokens(today_tokens)} / {fmt_tokens(month_tokens)}",
        )


        # --- SESSIONS 카드: 현재 활성 세션 (최근 30분 이내) ---
        active_sessions = [s for s in all_sessions if _seconds_ago(s["last_ts"]) < 1800]
        self._card("card-sessions").set_card("ACTIVE SESSIONS", str(len(active_sessions)))

        # --- 동적 바 폭 ---
        bar_width = max(8, min(20, self.size.width - 28))

        # --- 토큰 행 ---
        in_thr  = THRESHOLDS["input_tokens"]
        out_thr = THRESHOLDS["output_tokens"]
        self._set("token-header",
            f"[dim]Thr: In {fmt_tokens(in_thr)} / Out {fmt_tokens(out_thr)}[/dim]")
        self._set("tok-input",  self._tok_line("Input",  today_input,  in_thr,  bar_width))
        self._set("tok-output", self._tok_line("Output", today_output, out_thr, bar_width))
        # Cache: 적중률 = cache_read / (input + cache_read)
        self._set("tok-cache",  self._cache_line(today_cache_r, today_input, today_cache_w, bar_width))

        # --- 오늘 세션 테이블 (top 5) ---
        top = sorted(today_sessions,
                     key=lambda s: s["daily"][today]["cost"], reverse=True)[:5]
        max_cost = top[0]["daily"][today]["cost"] if top else 1.0
        proj_w   = max(8, min(14, self.size.width - 50))
        lines = [
            "[bold]Today's Sessions[/bold]",
            f"[dim] #  {'ID':<7} {'Project':<{proj_w}}  Cost    Tokens   Last[/dim]",
        ]
        for i, s in enumerate(top, 1):
            d      = s["daily"][today]
            sid    = s["session_id"][:6]
            proj   = s["project"][:proj_w]
            tok    = fmt_tokens(d["input"] + d["output"] + d["cache_write"] + d["cache_read"])
            filled = int(d["cost"] / max_cost * 6) if max_cost > 0 else 0
            mini   = "[green]" + "█" * filled + "[/green]" + "░" * (6 - filled)
            ago    = fmt_ago(s["last_ts"])
            lines.append(
                f" {i:>2}  [dim]{sid}[/dim]  {proj:<{proj_w}}  ${d['cost']:5.2f}  {tok:>6}  {mini}  {ago}"
            )
        self._set("session-table", "\n".join(lines))

        # --- 하단 바: 모델 + 세션 수 + 갱신 시각 ---
        model_totals: dict[str, int] = defaultdict(int)
        for s in today_sessions:
            for m, c in s["models"].items():
                model_totals[m] += c
        top_model = max(model_totals, key=lambda k: model_totals[k]) if model_totals else "--"
        self._set("bottom-bar",
            f"[dim]Model: {top_model.replace('claude-', '')}  ·  "
            f"All-time: {len(all_sessions)} sessions  ·  "
            f"Updated: {now_str}[/dim]")

    # --- helpers ---

    @staticmethod
    def _tok_line(label: str, value: float, threshold: float, bar_w: int = 20) -> str:
        pct  = value / threshold if threshold > 0 else 0.0
        warn = " ⚠" if pct >= 1.0 else ""
        return (f"{label:<7}  {make_bar(value, threshold, width=bar_w)}"
                f"  {fmt_tokens(value):>6}   {int(pct * 100):>3}%{warn}")

    @staticmethod
    def _cache_line(cache_r: float, inp: float, cache_w: float, bar_w: int = 20) -> str:
        """캐시 적중률: cache_read / (input + cache_read) = 신규 입력 대비 캐시 재사용 비율."""
        denom = inp + cache_r
        hit   = cache_r / denom if denom > 0 else 0.0
        filled = int(hit * bar_w)
        bar   = f"[cyan]{'█' * filled}{'░' * (bar_w - filled)}[/cyan]"
        return (f"Cache    {bar}  {fmt_tokens(cache_r):>6}   {int(hit * 100):>3}% hit"
                f"  [dim](+{fmt_tokens(cache_w)} write)[/dim]")

    def _card(self, widget_id: str) -> SummaryCard:
        return self.query_one(f"#{widget_id}", SummaryCard)

    def _set(self, widget_id: str, text: str) -> None:
        try:
            self.query_one(f"#{widget_id}").update(text)
        except NoMatches:
            pass


if __name__ == "__main__":
    Dashboard().run()
