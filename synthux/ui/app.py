"""SYNTH UX — Gradio MVP.

Runs entirely on the mock orchestrator (no models, no keys) so the study
workflow and report design can be iterated first. Swapping in the live
runner changes nothing in this file except the `run_study` import.

    pip install -e "../backend[dev]" gradio
    python app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import gradio as gr

from synthux.models import SessionMetrics, SessionTelemetry, StudyReport
from synthux.orchestrator import run_mock_study

_STATE: dict = {"sessions": [], "metrics": {}}


def _bar(share: float, width: int = 20) -> str:
    filled = round(share * width)
    return "█" * filled + "░" * (width - filled)


def _render_report(report: StudyReport) -> str:
    md = [
        f"> ⚠️ {report.disclaimer}",
        "",
        "## Task success",
        "```",
        f"{_bar(report.success_rate)} {report.success_rate:.0%}",
        f"success   {report.success_rate:.0%}   (95% CI {report.success_ci[0]:.0%}–{report.success_ci[1]:.0%})",
        f"partial   {report.partial_rate:.0%}",
        f"failed    {report.failure_rate:.0%}",
        f"abandoned {report.abandon_rate:.0%}",
        "```",
        f"**Median actions:** {report.median_actions:.0f} · "
        f"**Optimal:** {report.optimal_actions} · "
        f"**Sessions with backtracking:** {report.backtrack_rate:.0%}",
        "",
        "## Primary issues",
    ]
    for i, issue in enumerate(report.issues, 1):
        share = issue.affected_participants / issue.total_participants
        md += [
            f"### {i}. {issue.title}  `{issue.severity.value}`",
            f"`{_bar(share, 16)}` {issue.affected_participants}/{issue.total_participants} participants "
            f"· category **{issue.category.value}**",
            "",
            issue.statement,
            "",
        ]
        if issue.cohort_shares:
            worst = max(issue.cohort_shares, key=issue.cohort_shares.get)
            md.append(f"Most affected cohort: **{worst}** ({issue.cohort_shares[worst]:.0%})")
        for q in issue.quotes:
            md.append(f"> “{q}”")
        md += ["", f"**Recommendation:** {issue.recommendation}", ""]

    md += ["## Cohort comparison", "", "| Cohort | n | Success | 95% CI | Median actions |", "|---|---:|---:|---|---:|"]
    for c in report.cohorts:
        md.append(
            f"| {c.cohort} | {c.n} | {c.success_rate:.0%} | "
            f"{c.ci_low:.0%}–{c.ci_high:.0%} | {c.median_actions:.0f} |"
        )
    return "\n".join(md)


def _render_session(session: SessionTelemetry, metrics: SessionMetrics) -> str:
    lines = [
        f"### Participant {session.participant_id}",
        f"Cohort **{session.cohorts[0]}** · outcome **{metrics.success.value}** · "
        f"{metrics.actual_actions} actions (optimal {metrics.optimal_actions}) · "
        f"lostness {metrics.lostness:.2f} · confidence {metrics.confidence_band}",
        "",
        "```",
    ]
    t = 0.0
    for step in session.steps:
        t += step.dwell_seconds
        target = f" → {step.action.target_label}" if step.action.target_label else ""
        lines.append(f"{int(t)//60:02d}:{int(t)%60:02d}  [{step.screen_id}] {step.action.type}{target}")
        lines.append(f'       USER: "{step.thinking_aloud}"  (confidence {step.confidence:.0%})')
    lines.append("```")
    return "\n".join(lines)


def run_study(input_kind, source, product, audience, n_participants, task):
    report, sessions, metrics = run_mock_study(n_participants=int(n_participants))
    _STATE["sessions"] = sessions
    _STATE["metrics"] = metrics
    choices = [
        f"{s.participant_id} · {s.cohorts[0]} · {metrics[s.session_id].success.value}"
        for s in sessions
    ]
    return (
        _render_report(report),
        gr.update(choices=choices, value=choices[0], visible=True),
        _render_session(sessions[0], metrics[sessions[0].session_id]),
    )


def show_session(choice: str) -> str:
    pid = choice.split(" · ")[0]
    for s in _STATE["sessions"]:
        if s.participant_id == pid:
            return _render_session(s, _STATE["metrics"][s.session_id])
    return "Session not found."


with gr.Blocks(title="SYNTH UX") as demo:
    gr.Markdown("# SYNTH UX\n**Synthetic UX Research Engine** — predictive usability testing "
                "(mock runner: fixture billing app, no models attached)")
    with gr.Row():
        with gr.Column(scale=1):
            input_kind = gr.Radio(["Website URL", "Figma prototype", "Screenshots"],
                                  value="Website URL", label="Upload")
            source = gr.Textbox(label="Source", placeholder="https://…")
            product = gr.Textbox(label="Product context", value="Electricity billing app")
            audience = gr.Textbox(label="Target audience",
                                  value="Indian consumers, age 30–65")
            n_participants = gr.Slider(5, 100, value=25, step=5, label="Participants")
            task = gr.Textbox(label="Task",
                              value="Find and change your payment method from card to direct debit.")
            run_btn = gr.Button("Run Synthetic Test", variant="primary")
        with gr.Column(scale=2):
            report_md = gr.Markdown("*Configure a study and run it.*")
    gr.Markdown("---\n## Watch participant")
    session_picker = gr.Dropdown(label="Participant", choices=[], visible=False)
    session_md = gr.Markdown("")

    run_btn.click(run_study,
                  inputs=[input_kind, source, product, audience, n_participants, task],
                  outputs=[report_md, session_picker, session_md])
    session_picker.change(show_session, inputs=session_picker, outputs=session_md)


if __name__ == "__main__":
    demo.launch()
