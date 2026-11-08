"""
Arena Scenario Runner - Executes test scenarios against agents
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from .config import ArenaConfig
from .scenario import AgentOutput, ExpectedOutput, Metrics, Scenario, ScenarioResult

logger = logging.getLogger(__name__)


class ScenarioRunner:
    """Runs test scenarios against Vetrelay agents."""

    def __init__(self, config: ArenaConfig | None = None):
        self.config = config or ArenaConfig.default()
        self._agent_cache = {}

    def _get_agent(self, agent_name: str):
        """Get or create an agent function."""
        if agent_name not in self._agent_cache:
            # Import agent functions dynamically
            if agent_name == "triage_agent":
                from backend.agents.triage_agent import evaluate_triage
                self._agent_cache[agent_name] = evaluate_triage
            elif agent_name == "soap_agent":
                from backend.agents.soap_agent import build_soap_summary
                self._agent_cache[agent_name] = build_soap_summary
            elif agent_name == "front_desk_agent":
                from backend.agents.booking_agent import route_booking
                self._agent_cache[agent_name] = route_booking
            elif agent_name == "vetrelay_coordinator":
                # For coordinator, we'll use a wrapper that chains the agents
                from backend.agents.booking_agent import route_booking
                from backend.agents.soap_agent import build_soap_summary
                from backend.agents.triage_agent import evaluate_triage

                async def coordinator_process(input_data):
                    """Process through full workflow: triage -> soap -> booking."""
                    from backend.schemas import PetIntakeInput, SOAPRequest

                    # Build intake from input
                    meta = input_data.get("metadata", {})
                    ctx = input_data.get("context", {})
                    intake = PetIntakeInput(
                        owner_name=meta.get("owner_name", "Unknown"),
                        pet_name=meta.get("pet_name", "Unknown"),
                        species=meta.get("species", "canine"),
                        age_years=meta.get("age"),
                        reported_symptoms=[input_data.get("transcript", "")]
                        if input_data.get("transcript")
                        else meta.get("reported_symptoms", ["unspecified"]),
                        duration_hours=ctx.get("duration_hours"),
                        suspected_toxicity=ctx.get("suspected_toxicity", False),
                    )

                    # Step 1: Triage
                    triage_result = await evaluate_triage(intake)

                    # Step 2: SOAP
                    soap_request = SOAPRequest(
                        species=input_data.get("metadata", {}).get("species", "canine"),
                        age_years=input_data.get("metadata", {}).get("age"),
                        owner_statement=input_data.get("transcript", ""),
                    )
                    soap_result = await build_soap_summary(soap_request)

                    # Step 3: Booking
                    booking_result = await route_booking(intake, triage_result)

                    # Combine results
                    return {
                        "urgency": triage_result.triage_level.value,
                        "escalate": triage_result.is_emergency,
                        "recommended_actions": [triage_result.action_required],
                        "handoff_to": "front_desk_agent" if not triage_result.is_emergency else None,
                        "soap_note": {
                            "subjective": soap_result.soap.subjective,
                            "objective": soap_result.soap.objective,
                            "assessment": soap_result.soap.assessment,
                            "plan": soap_result.soap.plan,
                        },
                        "tools_called": ["evaluate_triage", "build_soap_summary", "route_booking"],
                        "raw_response": f"Triage: {triage_result.triage_level.value}\nSOAP: {soap_result.soap.subjective[:50]}...\nBooking: {booking_result.clinic_name}",
                        "custom": {
                            "severity_score": triage_result.severity_score,
                            "soap_confidence": soap_result.confidence_score,
                            "clinic_name": booking_result.clinic_name,
                            "scheduled_slot": booking_result.scheduled_slot,
                        }
                    }

                self._agent_cache[agent_name] = coordinator_process
            else:
                raise ValueError(f"Unknown agent: {agent_name}")
        return self._agent_cache[agent_name]

    async def run_async(self, scenario: Scenario, model: str | None = None) -> ScenarioResult:
        """Run a scenario asynchronously."""
        model = model or self.config.default_model
        start_time = time.time()

        try:
            agent = self._get_agent(scenario.agent)

            # Prepare input for the agent
            input_data = {
                "transcript": scenario.input.transcript,
                "metadata": scenario.input.metadata,
                "context": scenario.input.context
            }

            # Run the agent - agents are now async functions
            if asyncio.iscoroutinefunction(agent):
                result = await agent(input_data)
            else:
                result = agent(input_data)

            # Extract output
            output = AgentOutput(
                urgency=result.get("urgency"),
                escalate=result.get("escalate"),
                recommended_actions=result.get("recommended_actions", []),
                handoff_to=result.get("handoff_to"),
                soap_note=result.get("soap_note"),
                tools_called=result.get("tools_called", []),
                raw_response=result.get("raw_response", ""),
                custom={k: v for k, v in result.items()
                       if k not in ["urgency", "escalate", "recommended_actions",
                                   "handoff_to", "soap_note", "tools_called", "raw_response"]}
            )

            # Calculate metrics
            latency_ms = (time.time() - start_time) * 1000
            metrics = self._calculate_metrics(scenario.expected, output, latency_ms)

            # Determine if passed
            passed = metrics.accuracy >= self.config.evaluation.similarity_threshold

            # Generate diff if not passed
            diff = None if passed else self._generate_diff(scenario.expected, output)

            return ScenarioResult(
                scenario=scenario,
                agent=scenario.agent,
                model=model,
                timestamp=datetime.utcnow().isoformat() + "Z",
                output=output,
                expected=scenario.expected,
                metrics=metrics,
                passed=passed,
                diff=diff
            )

        except Exception as e:
            logger.error(f"Error running scenario {scenario.name}: {e}")
            return ScenarioResult(
                scenario=scenario,
                agent=scenario.agent,
                model=model,
                timestamp=datetime.utcnow().isoformat() + "Z",
                output=AgentOutput(),
                expected=scenario.expected,
                metrics=Metrics(),
                passed=False,
                error=str(e)
            )

    def run(self, scenario: Scenario, model: str | None = None) -> ScenarioResult:
        """Run a scenario synchronously."""
        return asyncio.run(self.run_async(scenario, model))

    def _calculate_metrics(self, expected: ExpectedOutput, actual: AgentOutput,
                          latency_ms: float) -> Metrics:
        """Calculate accuracy and other metrics."""
        metrics = Metrics(latency_ms=latency_ms)

        # Accuracy: compare expected vs actual fields
        matches = 0
        total = 0

        # Check urgency
        if expected.urgency is not None:
            total += 1
            if actual.urgency == expected.urgency:
                matches += 1

        # Check escalate
        if expected.escalate is not None:
            total += 1
            if actual.escalate == expected.escalate:
                matches += 1

        # Check handoff
        if expected.handoff_to is not None:
            total += 1
            if actual.handoff_to == expected.handoff_to:
                matches += 1
                metrics.handoff_correctness = 1.0
            else:
                metrics.handoff_correctness = 0.0

        # Check recommended actions (set comparison)
        if expected.recommended_actions:
            total += 1
            expected_set = set(expected.recommended_actions)
            actual_set = set(actual.recommended_actions)
            if expected_set == actual_set:
                matches += 1
            elif expected_set & actual_set:
                matches += 0.5  # Partial match

        # Check SOAP note
        if expected.soap_note is not None:
            total += 1
            if actual.soap_note and self._compare_soap(expected.soap_note, actual.soap_note):
                matches += 1

        # Check tool usage
        # (simplified - would need more detailed tracking)
        metrics.tool_usage_correctness = 1.0  # Placeholder

        metrics.accuracy = matches / total if total > 0 else 1.0

        # Estimate token count (rough approximation)
        metrics.token_count = len(str(actual.raw_response)) // 4

        return metrics

    def _compare_soap(self, expected: dict, actual: dict) -> bool:
        """Compare SOAP notes for structural similarity."""
        expected_keys = set(expected.keys())
        actual_keys = set(actual.keys())

        # Check all expected sections exist
        if not expected_keys.issubset(actual_keys):
            return False

        # Check content similarity for each section
        for key in expected_keys:
            if isinstance(expected[key], str) and isinstance(actual[key], str):
                # Simple string similarity
                if not self._strings_similar(expected[key], actual[key]):
                    return False

        return True

    def _strings_similar(self, a: str, b: str, threshold: float = 0.7) -> bool:
        """Simple string similarity check."""
        if a == b:
            return True
        # Simple word overlap
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return False
        overlap = len(words_a & words_b) / len(words_a | words_b)
        return overlap >= threshold

    def _generate_diff(self, expected: ExpectedOutput, actual: AgentOutput) -> dict[str, Any]:
        """Generate a diff between expected and actual output."""
        diff = {}

        if expected.urgency != actual.urgency:
            diff['urgency'] = {'expected': expected.urgency, 'actual': actual.urgency}

        if expected.escalate != actual.escalate:
            diff['escalate'] = {'expected': expected.escalate, 'actual': actual.escalate}

        if expected.handoff_to != actual.handoff_to:
            diff['handoff_to'] = {'expected': expected.handoff_to, 'actual': actual.handoff_to}

        expected_actions = set(expected.recommended_actions)
        actual_actions = set(actual.recommended_actions)
        if expected_actions != actual_actions:
            diff['recommended_actions'] = {
                'expected': list(expected_actions),
                'actual': list(actual_actions),
                'missing': list(expected_actions - actual_actions),
                'extra': list(actual_actions - expected_actions)
            }

        if expected.soap_note and actual.soap_note:
            soap_diff = {}
            for key in expected.soap_note:
                if key not in actual.soap_note:
                    soap_diff[key] = {'expected': expected.soap_note[key], 'actual': None}
                elif expected.soap_note[key] != actual.soap_note[key]:
                    soap_diff[key] = {'expected': expected.soap_note[key], 'actual': actual.soap_note[key]}
            if soap_diff:
                diff['soap_note'] = soap_diff

        return diff

