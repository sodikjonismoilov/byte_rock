"""Planner, researcher, and critic components for legal due diligence."""

if __package__ and __package__.startswith("agents.legal_agent"):
    from ..agents.critic import critique_draft
else:
    from agents.critic import critique_draft
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..agents.planner import make_plan
else:
    from agents.planner import make_plan
if __package__ and __package__.startswith("agents.legal_agent"):
    from ..agents.researcher import research
else:
    from agents.researcher import research

__all__ = ["critique_draft", "make_plan", "research"]
