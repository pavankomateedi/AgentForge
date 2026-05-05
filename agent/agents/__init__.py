"""Multi-agent layer (Week 2).

Outer graph:
  START -> supervisor -> [intake_extractor || evidence_retriever]
        -> answer_pipeline (Week 1, wrapped) -> END

The Week 1 11-node pipeline is wrapped as ONE node here. We do not
modify it — the verifier, tools, RBAC, and audit log all behave
identically inside the wrapper.
"""

from agent.agents.supervisor import RoutingDecision, call_supervisor

__all__ = ["RoutingDecision", "call_supervisor"]
