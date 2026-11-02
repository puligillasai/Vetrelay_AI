"""
Arena Evaluator Module - Evaluation metrics and comparison logic
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class BaseMetric:
    """Base class for custom evaluation metrics."""

    def evaluate(self, expected: Any, actual: Any, context: Dict[str, Any]) -> float:
        """Evaluate and return a score between 0.0 and 1.0."""
        raise NotImplementedError


class AccuracyMetric(BaseMetric):
    """Standard accuracy metric comparing expected vs actual."""

    def evaluate(self, expected: Any, actual: Any, context: Dict[str, Any]) -> float:
        if expected == actual:
            return 1.0
        if isinstance(expected, dict) and isinstance(actual, dict):
            return self._dict_similarity(expected, actual)
        if isinstance(expected, list) and isinstance(actual, list):
            return self._list_similarity(expected, actual)
        if isinstance(expected, str) and isinstance(actual, str):
            return self._string_similarity(expected, actual)
        return 0.0

    def _dict_similarity(self, a: Dict, b: Dict) -> float:
        all_keys = set(a.keys()) | set(b.keys())
        if not all_keys:
            return 1.0
        matches = sum(1 for k in all_keys if a.get(k) == b.get(k))
        return matches / len(all_keys)

    def _list_similarity(self, a: List, b: List) -> float:
        set_a, set_b = set(a), set(b)
        if not set_a and not set_b:
            return 1.0
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    def _string_similarity(self, a: str, b: str) -> float:
        if a == b:
            return 1.0
        words_a, words_b = set(a.lower().split()), set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)


class ClinicalAccuracyMetric(BaseMetric):
    """Clinical accuracy metric for veterinary scenarios."""

    # Critical fields that must match exactly
    CRITICAL_FIELDS = ['urgency', 'escalate', 'handoff_to']

    def evaluate(self, expected: Dict[str, Any], actual: Dict[str, Any],
                context: Dict[str, Any]) -> float:
        score = 0.0
        weight_sum = 0.0

        # Critical fields (high weight)
        for field in self.CRITICAL_FIELDS:
            if field in expected:
                weight_sum += 3.0
                if expected[field] == actual.get(field):
                    score += 3.0

        # Recommended actions (medium weight)
        if 'recommended_actions' in expected:
            weight_sum += 2.0
            exp_actions = set(expected['recommended_actions'])
            act_actions = set(actual.get('recommended_actions', []))
            if exp_actions == act_actions:
                score += 2.0
            elif exp_actions & act_actions:
                score += 1.0

        # SOAP note sections (lower weight)
        if 'soap_note' in expected and expected['soap_note']:
            weight_sum += 1.0
            exp_soap = expected['soap_note']
            act_soap = actual.get('soap_note', {})
            if isinstance(exp_soap, dict) and isinstance(act_soap, dict):
                matches = sum(1 for k in exp_soap if k in act_soap)
                if matches > 0:
                    score += matches / len(exp_soap)

        return score / weight_sum if weight_sum > 0 else 0.0


class HandoffCorrectnessMetric(BaseMetric):
    """Metric for evaluating agent handoff correctness."""

    def evaluate(self, expected: Any, actual: Any, context: Dict[str, Any]) -> float:
        expected_handoff = expected.get('handoff_to') if isinstance(expected, dict) else None
        actual_handoff = actual.get('handoff_to') if isinstance(actual, dict) else None

        if expected_handoff is None:
            # No handoff expected
            return 1.0 if actual_handoff is None else 0.5

        if actual_handoff is None:
            return 0.0

        return 1.0 if expected_handoff == actual_handoff else 0.0


class ToolUsageCorrectnessMetric(BaseMetric):
    """Metric for evaluating tool usage correctness."""

    def evaluate(self, expected: Any, actual: Any, context: Dict[str, Any]) -> float:
        expected_tools = set(expected.get('tools_called', [])) if isinstance(expected, dict) else set()
        actual_tools = set(actual.get('tools_called', [])) if isinstance(actual, dict) else set()

        if not expected_tools:
            # No specific tools expected
            return 1.0

        if not actual_tools:
            return 0.0

        return len(expected_tools & actual_tools) / len(expected_tools)


class Evaluator:
    """Main evaluator that combines multiple metrics."""

    def __init__(self, metrics: Optional[List[BaseMetric]] = None):
        self.metrics = metrics or [
            AccuracyMetric(),
            ClinicalAccuracyMetric(),
            HandoffCorrectnessMetric(),
            ToolUsageCorrectnessMetric()
        ]

    def evaluate(self, expected: Any, actual: Any, context: Dict[str, Any]) -> Dict[str, float]:
        """Run all metrics and return scores."""
        results = {}
        for metric in self.metrics:
            try:
                name = metric.__class__.__name__.replace('Metric', '').lower()
                results[name] = metric.evaluate(expected, actual, context)
            except Exception as e:
                logger.error(f"Metric {metric.__class__.__name__} failed: {e}")
                results[metric.__class__.__name__.lower()] = 0.0
        return results

    def aggregate_score(self, scores: Dict[str, float],
                       weights: Optional[Dict[str, float]] = None) -> float:
        """Calculate weighted aggregate score."""
        default_weights = {
            'accuracy': 0.4,
            'clinicalaccuracy': 0.3,
            'handoffcorrectness': 0.2,
            'toolusagecorrectness': 0.1
        }
        weights = weights or default_weights

        total = 0.0
        weight_sum = 0.0
        for name, score in scores.items():
            weight = weights.get(name, 0.0)
            total += score * weight
            weight_sum += weight

        return total / weight_sum if weight_sum > 0 else 0.0