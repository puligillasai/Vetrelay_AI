"""
Tests for the Arena module
"""

import pytest
import tempfile
import os
from pathlib import Path

from backend.arena.config import ArenaConfig, EvaluationConfig
from backend.arena.scenario import (
    Scenario, ScenarioInput, ExpectedOutput, AgentOutput,
    Metrics, ScenarioResult
)
from backend.arena.evaluator import (
    Evaluator, AccuracyMetric, ClinicalAccuracyMetric,
    HandoffCorrectnessMetric, ToolUsageCorrectnessMetric
)


class TestArenaConfig:
    """Tests for ArenaConfig."""

    def test_default_config(self):
        config = ArenaConfig.default()
        assert config.default_model == "claude-sonnet-5-5"
        assert config.parallel_workers == 4
        assert config.scenario_timeout == 60
        assert config.evaluation.similarity_threshold == 0.85

    def test_config_yaml_roundtrip(self):
        config = ArenaConfig.default()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config.to_yaml(f.name)
            temp_path = f.name

        try:
            loaded = ArenaConfig.from_yaml(temp_path)
            assert loaded.default_model == config.default_model
            assert loaded.parallel_workers == config.parallel_workers
        finally:
            os.unlink(temp_path)


class TestScenario:
    """Tests for Scenario data structures."""

    def test_scenario_creation(self):
        scenario = Scenario(
            name="test_scenario",
            description="Test scenario",
            agent="triage_agent",
            input=ScenarioInput(transcript="Test transcript"),
            expected=ExpectedOutput(urgency="EMERGENCY")
        )

        assert scenario.name == "test_scenario"
        assert scenario.agent == "triage_agent"
        assert scenario.input.transcript == "Test transcript"
        assert scenario.expected.urgency == "EMERGENCY"

    def test_scenario_yaml_roundtrip(self):
        scenario = Scenario(
            name="test_yaml",
            description="Test YAML roundtrip",
            agent="soap_agent",
            input=ScenarioInput(
                transcript="Test",
                metadata={"key": "value"},
                context={"ctx": "data"}
            ),
            expected=ExpectedOutput(
                urgency="URGENT",
                escalate=True,
                recommended_actions=["Action 1", "Action 2"],
                handoff_to="front_desk_agent",
                soap_note={"subjective": "Test", "objective": "Test"}
            ),
            tags=["test", "yaml"]
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            scenario.to_yaml(f.name)
            temp_path = f.name

        try:
            loaded = Scenario.from_yaml(temp_path)
            assert loaded.name == scenario.name
            assert loaded.agent == scenario.agent
            assert loaded.input.transcript == scenario.input.transcript
            assert loaded.input.metadata == scenario.input.metadata
            assert loaded.expected.urgency == scenario.expected.urgency
            assert loaded.expected.escalate == scenario.expected.escalate
            assert loaded.expected.recommended_actions == scenario.expected.recommended_actions
            assert loaded.expected.handoff_to == scenario.expected.handoff_to
            assert loaded.tags == scenario.tags
        finally:
            os.unlink(temp_path)


class TestScenarioResult:
    """Tests for ScenarioResult."""

    def test_result_creation(self):
        scenario = Scenario(
            name="test",
            description="Test",
            agent="triage_agent",
            input=ScenarioInput(),
            expected=ExpectedOutput(urgency="EMERGENCY")
        )

        result = ScenarioResult(
            scenario=scenario,
            agent="triage_agent",
            model="claude-sonnet-5-5",
            timestamp="2026-10-28T10:00:00Z",
            output=AgentOutput(urgency="EMERGENCY", escalate=True),
            expected=ExpectedOutput(urgency="EMERGENCY", escalate=True),
            metrics=Metrics(accuracy=1.0, latency_ms=100, token_count=50),
            passed=True
        )

        assert result.passed is True
        assert result.metrics.accuracy == 1.0

    def test_result_json_roundtrip(self):
        scenario = Scenario(
            name="test_json",
            description="Test JSON",
            agent="triage_agent",
            input=ScenarioInput(transcript="Test"),
            expected=ExpectedOutput(urgency="EMERGENCY")
        )

        result = ScenarioResult(
            scenario=scenario,
            agent="triage_agent",
            model="claude-sonnet-5-5",
            timestamp="2026-10-28T10:00:00Z",
            output=AgentOutput(urgency="EMERGENCY"),
            expected=ExpectedOutput(urgency="EMERGENCY"),
            metrics=Metrics(accuracy=1.0, latency_ms=100),
            passed=True
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            result.save(f.name)
            temp_path = f.name

        try:
            loaded = ScenarioResult.load(temp_path)
            assert loaded.scenario.name == result.scenario.name
            assert loaded.agent == result.agent
            assert loaded.metrics.accuracy == result.metrics.accuracy
            assert loaded.passed == result.passed
        finally:
            os.unlink(temp_path)


class TestEvaluator:
    """Tests for evaluation metrics."""

    def test_accuracy_metric(self):
        metric = AccuracyMetric()

        # Exact match
        assert metric.evaluate("hello", "hello", {}) == 1.0

        # Dict similarity
        assert metric.evaluate({"a": 1, "b": 2}, {"a": 1, "b": 2}, {}) == 1.0
        assert metric.evaluate({"a": 1, "b": 2}, {"a": 1, "b": 3}, {}) == 0.5

        # List similarity
        assert metric.evaluate([1, 2, 3], [1, 2, 3], {}) == 1.0
        assert metric.evaluate([1, 2], [2, 3], {}) == 1/3  # intersection/union

    def test_clinical_accuracy_metric(self):
        metric = ClinicalAccuracyMetric()

        expected = {
            "urgency": "EMERGENCY",
            "escalate": True,
            "handoff_to": "front_desk_agent",
            "recommended_actions": ["Action 1", "Action 2"],
            "soap_note": {"subjective": "Test", "objective": "Test"}
        }

        # Perfect match
        assert metric.evaluate(expected, expected, {}) == 1.0

        # Wrong urgency (critical field)
        actual = expected.copy()
        actual["urgency"] = "URGENT"
        assert metric.evaluate(expected, actual, {}) < 1.0

        # Partial actions match
        actual = expected.copy()
        actual["recommended_actions"] = ["Action 1"]
        score = metric.evaluate(expected, actual, {})
        assert 0.0 < score < 1.0

    def test_handoff_correctness_metric(self):
        metric = HandoffCorrectnessMetric()

        # Match
        assert metric.evaluate({"handoff_to": "agent_a"}, {"handoff_to": "agent_a"}, {}) == 1.0

        # Mismatch
        assert metric.evaluate({"handoff_to": "agent_a"}, {"handoff_to": "agent_b"}, {}) == 0.0

        # No handoff expected, none given
        assert metric.evaluate({}, {}, {}) == 1.0

        # No handoff expected, but given
        assert metric.evaluate({}, {"handoff_to": "agent_a"}, {}) == 0.5

        # Handoff expected, none given
        assert metric.evaluate({"handoff_to": "agent_a"}, {}, {}) == 0.0

    def test_tool_usage_metric(self):
        metric = ToolUsageCorrectnessMetric()

        # All expected tools called
        assert metric.evaluate(
            {"tools_called": ["tool_a", "tool_b"]},
            {"tools_called": ["tool_a", "tool_b", "tool_c"]},
            {}
        ) == 1.0

        # Partial match
        assert metric.evaluate(
            {"tools_called": ["tool_a", "tool_b"]},
            {"tools_called": ["tool_a"]},
            {}
        ) == 0.5

        # No tools expected
        assert metric.evaluate({}, {"tools_called": ["tool_a"]}, {}) == 1.0

        # Tools expected, none called
        assert metric.evaluate({"tools_called": ["tool_a"]}, {}, {}) == 0.0

    def test_evaluator_aggregate(self):
        evaluator = Evaluator()

        expected = {
            "urgency": "EMERGENCY",
            "escalate": True,
            "handoff_to": "front_desk_agent",
            "recommended_actions": ["Action 1"],
            "tools_called": ["tool_a"]
        }
        actual = expected.copy()

        scores = evaluator.evaluate(expected, actual, {})
        assert "accuracy" in scores
        assert "clinicalaccuracy" in scores
        assert "handoffcorrectness" in scores
        assert "toolusagecorrectness" in scores

        agg = evaluator.aggregate_score(scores)
        assert agg == 1.0  # Perfect match should give 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])