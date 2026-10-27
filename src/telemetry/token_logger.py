"""Token usage logger for MCP agent runs.

Creates logs/ at the project root. Each run gets its own timestamped file:

    logs/
        2026-10-08_00-44-15.log
        2026-10-08_00-51-03.log

Per-call lines are appended as the run progresses; a summary block is
written (and printed) when finalize() is called after the run ends.
"""

from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = ROOT / "logs"


class TokenLogger:
    """Records LLM token usage for a single agent run."""

    def __init__(self, question: str, model: str) -> None:
        LOGS_DIR.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_path = LOGS_DIR / f"{timestamp}.log"
        self.question = question
        self.model = model
        self.calls: list[dict] = []

        # Write the run header once
        self._write(
            f"Timestamp : {timestamp}\n"
            f"Model     : {model}\n"
            f"Question  : {question}\n"
            f"{'─' * 52}\n\n"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        action: str | None = None,
    ) -> None:
        """Call this once per model invocation with the usage counts.

        `action` is a short description of what the model decided to do,
        e.g. 'get_file_contents(path="src/main.py")' or '[response]'.
        """
        call_n = len(self.calls) + 1
        entry = {"call": call_n, "input": input_tokens, "output": output_tokens, "total": total_tokens}
        self.calls.append(entry)
        action_col = f"  {action:<52}" if action else " " * 54
        self._write(
            f"[Call {call_n:>2}]{action_col}"
            f"  in={input_tokens:>6,}  out={output_tokens:>6,}\n"
        )

    def record_router(self, input_tokens: int, output_tokens: int, total_tokens: int) -> None:
        """Record the one-off router call separately from main agent calls."""
        self.router = {"input": input_tokens, "output": output_tokens, "total": total_tokens}
        self._write(
            f"[Router]    "
            f"input={input_tokens:>6,}  "
            f"output={output_tokens:>6,}  "
            f"total={total_tokens:>6,}\n"
        )

    def record_identity(self, login: str | None) -> None:
        """Log the user resolved in code via get_me (no LLM call, no tokens)."""
        self._write(f"[Identity]  get_me (code, not LLM) → {login or 'unknown'}\n")

    def record_tool_result(self, tool_name: str, result_summary: str) -> None:
        """Log what a tool returned, indented under the previous call line."""
        self._write(f"           ↳ {result_summary}\n")

    def finalize(self) -> None:
        """Write the summary block, print it, and report the log path."""
        if not self.calls:
            return

        total_input  = sum(c["input"]  for c in self.calls)
        total_output = sum(c["output"] for c in self.calls)
        total_total  = sum(c["total"]  for c in self.calls)

        router = getattr(self, "router", None)
        router_line = (
            f"  Router   : {router['total']:>8,} tokens  "
            f"(input {router['input']:,} + output {router['output']:,})\n"
            if router else ""
        )
        agent_total_line = (
            f"  Agent    : {total_total:>8,} tokens\n"
            if router else ""
        )
        grand_total = total_total + (router["total"] if router else 0)

        summary = (
            f"\n{'─' * 52}\n"
            f"  Run Summary\n"
            f"{'─' * 52}\n"
            f"  Model    : {self.model}\n"
            f"  Calls    : {len(self.calls)}\n"
            f"{router_line}"
            f"{agent_total_line}"
            f"  Input    : {total_input:>8,} tokens\n"
            f"  Output   : {total_output:>8,} tokens\n"
            f"  Total    : {grand_total:>8,} tokens\n"
            f"{'─' * 52}\n"
        )

        self._write(summary)
        print(summary)
        print(f"  Log → {self.log_path}\n")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write(self, text: str) -> None:
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(text)
