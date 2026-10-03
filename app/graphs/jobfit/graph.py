# 组装 JobFit LangGraph 工作流。

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.graphs.jobfit.nodes import (
    agent_decide,
    assess_evidence,
    cancel,
    execute_tools,
    finalize,
    human_confirmation,
    load_context,
    prepare_run,
    route_after_agent,
    route_after_confirmation,
    route_after_tools,
    save_report,
)
from app.graphs.jobfit.runtime import JobFitGraphContext
from app.graphs.jobfit.state import JobFitGraphState


def build_jobfit_graph(checkpointer: Any | None = None):
    """构建并编译 JobFit Graph。

    真实 LLM、工具注册表和 ToolContext 工厂通过运行时的 context 注入。
    """

    builder = StateGraph(
        JobFitGraphState,
        context_schema=JobFitGraphContext,
    )

    builder.add_node("prepare_run", prepare_run)
    builder.add_node("load_context", load_context)
    builder.add_node("agent_decide", agent_decide)
    builder.add_node("execute_tools", execute_tools)
    builder.add_node("assess_evidence", assess_evidence)
    builder.add_node("human_confirmation", human_confirmation)
    builder.add_node("save_report", save_report)
    builder.add_node("finalize", finalize)
    builder.add_node("cancel", cancel)

    builder.add_edge(START, "prepare_run")
    builder.add_edge("prepare_run", "load_context")
    builder.add_edge("load_context", "agent_decide")
    builder.add_conditional_edges(
        "agent_decide",
        route_after_agent,
        {
            "execute_tools": "execute_tools",
            "assess_evidence": "assess_evidence",
        },
    )
    builder.add_conditional_edges(
        "execute_tools",
        route_after_tools,
        {
            "agent_decide": "agent_decide",
            "assess_evidence": "assess_evidence",
        },
    )
    builder.add_edge("assess_evidence", "human_confirmation")
    builder.add_conditional_edges(
        "human_confirmation",
        route_after_confirmation,
        {
            "save_report": "save_report",
            "cancel": "cancel",
        },
    )
    builder.add_edge("save_report", "finalize")
    builder.add_edge("finalize", END)
    builder.add_edge("cancel", END)

    return builder.compile(checkpointer=checkpointer)


__all__ = ["build_jobfit_graph"]
