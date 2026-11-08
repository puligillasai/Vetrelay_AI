"""
Arena Scenario Module - Data structures for test scenarios and results
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ScenarioInput:
    """Input data for a test scenario."""
    transcript: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExpectedOutput:
    """Expected output for a test scenario."""
    urgency: str | None = None
    escalate: bool | None = None
    recommended_actions: list[str] = field(default_factory=list)
    handoff_to: str | None = None
    soap_note: dict[str, Any] | None = None
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentOutput:
    """Actual output from an agent."""
    urgency: str | None = None
    escalate: bool | None = None
    recommended_actions: list[str] = field(default_factory=list)
    handoff_to: str | None = None
    soap_note: dict[str, Any] | None = None
    tools_called: list[str] = field(default_factory=list)
    raw_response: str = ""
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class Metrics:
    """Performance and accuracy metrics for a scenario run."""
    accuracy: float = 0.0
    latency_ms: float = 0.0
    token_count: int = 0
    handoff_correctness: float = 0.0
    tool_usage_correctness: float = 0.0
    custom: dict[str, float] = field(default_factory=dict)


@dataclass
class Scenario:
    """A complete test scenario definition."""
    name: str
    description: str
    agent: str
    input: ScenarioInput
    expected: ExpectedOutput
    tags: list[str] = field(default_factory=list)
    timeout: int = 60

    @classmethod
    def from_yaml(cls, path: str) -> "Scenario":
        """Load scenario from YAML file."""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)

        # Parse input
        input_data = data.get('input', {})
        input_obj = ScenarioInput(
            transcript=input_data.get('transcript', ''),
            metadata=input_data.get('metadata', {}),
            context=input_data.get('context', {})
        )

        # Parse expected
        expected_data = data.get('expected', {})
        expected_obj = ExpectedOutput(
            urgency=expected_data.get('urgency'),
            escalate=expected_data.get('escalate'),
            recommended_actions=expected_data.get('recommended_actions', []),
            handoff_to=expected_data.get('handoff_to'),
            soap_note=expected_data.get('soap_note'),
            custom={k: v for k, v in expected_data.items()
                   if k not in ['urgency', 'escalate', 'recommended_actions', 'handoff_to', 'soap_note']}
        )

        return cls(
            name=data.get('name', Path(path).stem),
            description=data.get('description', ''),
            agent=data.get('agent', ''),
            input=input_obj,
            expected=expected_obj,
            tags=data.get('tags', []),
            timeout=data.get('timeout', 60)
        )

    def to_yaml(self, path: str) -> None:
        """Save scenario to YAML file."""
        import yaml
        data = {
            'name': self.name,
            'description': self.description,
            'agent': self.agent,
            'input': {
                'transcript': self.input.transcript,
                'metadata': self.input.metadata,
                'context': self.input.context
            },
            'expected': {
                'urgency': self.expected.urgency,
                'escalate': self.expected.escalate,
                'recommended_actions': self.expected.recommended_actions,
                'handoff_to': self.expected.handoff_to,
                'soap_note': self.expected.soap_note,
                **self.expected.custom
            },
            'tags': self.tags,
            'timeout': self.timeout
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)


@dataclass
class ScenarioResult:
    """Result of running a scenario."""
    scenario: Scenario
    agent: str
    model: str
    timestamp: str
    output: AgentOutput
    expected: ExpectedOutput
    metrics: Metrics
    passed: bool
    diff: dict[str, Any] | None = None
    error: str | None = None

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'scenario': self.scenario.name,
            'agent': self.agent,
            'model': self.model,
            'timestamp': self.timestamp,
            'input': {
                'transcript': self.scenario.input.transcript,
                'metadata': self.scenario.input.metadata,
                'context': self.scenario.input.context
            },
            'output': {
                'urgency': self.output.urgency,
                'escalate': self.output.escalate,
                'recommended_actions': self.output.recommended_actions,
                'handoff_to': self.output.handoff_to,
                'soap_note': self.output.soap_note,
                'tools_called': self.output.tools_called,
                'raw_response': self.output.raw_response,
                'custom': self.output.custom
            },
            'expected': {
                'urgency': self.expected.urgency,
                'escalate': self.expected.escalate,
                'recommended_actions': self.expected.recommended_actions,
                'handoff_to': self.expected.handoff_to,
                'soap_note': self.expected.soap_note,
                'custom': self.expected.custom
            },
            'metrics': {
                'accuracy': self.metrics.accuracy,
                'latency_ms': self.metrics.latency_ms,
                'token_count': self.metrics.token_count,
                'handoff_correctness': self.metrics.handoff_correctness,
                'tool_usage_correctness': self.metrics.tool_usage_correctness,
                'custom': self.metrics.custom
            },
            'passed': self.passed,
            'diff': self.diff,
            'error': self.error
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScenarioResult":
        """Create from dictionary."""
        scenario = Scenario(
            name=data['scenario'],
            description="",
            agent=data['agent'],
            input=ScenarioInput(**data['input']),
            expected=ExpectedOutput(**data['expected'])
        )

        return cls(
            scenario=scenario,
            agent=data['agent'],
            model=data['model'],
            timestamp=data['timestamp'],
            output=AgentOutput(**data['output']),
            expected=ExpectedOutput(**data['expected']),
            metrics=Metrics(**data['metrics']),
            passed=data['passed'],
            diff=data.get('diff'),
            error=data.get('error')
        )

    def save(self, path: str) -> None:
        """Save result to JSON file."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "ScenarioResult":
        """Load result from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)