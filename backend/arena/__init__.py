"""
Arena - Agent Testing & Benchmarking Module for Vetrelay AI

This module provides a simulated environment for testing, benchmarking,
and evaluating the Vetrelay AI agents against realistic veterinary scenarios.
"""

__version__ = "0.1.0"
__author__ = "Vetrelay AI Team"

from .config import ArenaConfig
from .scenario import Scenario, ScenarioResult
from .runner import ScenarioRunner
from .benchmark import Benchmark
from .evaluator import Evaluator

__all__ = [
    "ArenaConfig",
    "Scenario",
    "ScenarioResult",
    "ScenarioRunner",
    "Benchmark",
    "Evaluator",
]