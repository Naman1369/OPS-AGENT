"""Versioned system prompts, one module per agent.

Prompts are held apart from agent logic so that Week 5-7 prompt tuning changes
exactly one file and the version string recorded in the trace tells you which
prompt produced any given run.
"""

from . import governance, intake, mast, resolution, single_agent

__all__ = ["intake", "resolution", "governance", "single_agent", "mast"]
