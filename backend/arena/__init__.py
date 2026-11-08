"""
Arena - Agent Testing & Benchmarking Module for Vetrelay AI

This module provides a simulated environment for testing, benchmarking,
and evaluating the Vetrelay AI agents against realistic veterinary scenarios.
"""

__version__ = "0.1.0"
__author__ = "Vetrelay AI Team"

from .benchmark import Benchmark
from .config import ArenaConfig
from .evaluator import Evaluator
from .runner import ScenarioRunner
from .scenario import Scenario, ScenarioResult

__all__ = [
    "ArenaConfig",
    "Scenario",
    "ScenarioResult",
    "ScenarioRunner",
    "Benchmark",
    "Evaluator",
]