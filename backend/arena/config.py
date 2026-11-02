"""
Arena Configuration Module
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EvaluationConfig:
    """Evaluation settings for scenario comparison."""
    similarity_threshold: float = 0.85
    metrics: list = field(default_factory=lambda: [
        "accuracy",
        "latency_ms",
        "token_count",
        "handoff_correctness",
        "tool_usage_correctness"
    ])


@dataclass
class ArenaConfig:
    """Main configuration for the Arena testing framework."""
    default_model: str = "claude-sonnet-5-5"
    baseline_dir: str = "arena/baselines"
    results_dir: str = "arena/results"
    scenarios_dir: str = "arena/scenarios"
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    parallel_workers: int = 4
    scenario_timeout: int = 60

    @classmethod
    def from_yaml(cls, path: str) -> "ArenaConfig":
        """Load configuration from YAML file."""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        # Handle nested evaluation config
        if 'evaluation' in data and isinstance(data['evaluation'], dict):
            data['evaluation'] = EvaluationConfig(**data['evaluation'])

        return cls(**data.get('arena', data))

    def to_yaml(self, path: str) -> None:
        """Save configuration to YAML file."""
        data = {
            'default_model': self.default_model,
            'baseline_dir': self.baseline_dir,
            'results_dir': self.results_dir,
            'scenarios_dir': self.scenarios_dir,
            'evaluation': {
                'similarity_threshold': self.evaluation.similarity_threshold,
                'metrics': self.evaluation.metrics
            },
            'parallel_workers': self.parallel_workers,
            'scenario_timeout': self.scenario_timeout
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            yaml.dump({'arena': data}, f, default_flow_style=False)

    @classmethod
    def default(cls) -> "ArenaConfig":
        """Return default configuration."""
        return cls()