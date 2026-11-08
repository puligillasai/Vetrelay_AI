"""
Arena Benchmark Module - Runs full benchmark suites
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import ArenaConfig
from .runner import ScenarioRunner
from .scenario import Scenario, ScenarioResult

logger = logging.getLogger(__name__)


class Benchmark:
    """Runs full benchmark suites against all scenarios."""

    def __init__(self, config: ArenaConfig | None = None):
        self.config = config or ArenaConfig.default()
        self.runner = ScenarioRunner(config)
        self.results: list[ScenarioResult] = []

    def discover_scenarios(self, scenarios_dir: str | None = None) -> list[Scenario]:
        """Discover all scenario files in the scenarios directory."""
        dir_path = Path(scenarios_dir or self.config.scenarios_dir)
        scenarios = []

        for yaml_file in dir_path.glob("*.yaml"):
            try:
                scenario = Scenario.from_yaml(str(yaml_file))
                scenarios.append(scenario)
                logger.info(f"Loaded scenario: {scenario.name}")
            except Exception as e:
                logger.error(f"Failed to load scenario {yaml_file}: {e}")

        for yml_file in dir_path.glob("*.yml"):
            try:
                scenario = Scenario.from_yaml(str(yml_file))
                scenarios.append(scenario)
                logger.info(f"Loaded scenario: {scenario.name}")
            except Exception as e:
                logger.error(f"Failed to load scenario {yml_file}: {e}")

        return scenarios

    async def run_async(self, scenarios: list[Scenario] | None = None,
                       model: str | None = None,
                       parallel: int | None = None) -> list[ScenarioResult]:
        """Run benchmark asynchronously."""
        if scenarios is None:
            scenarios = self.discover_scenarios()

        if not scenarios:
            logger.warning("No scenarios found to run")
            return []

        parallel = parallel or self.config.parallel_workers
        semaphore = asyncio.Semaphore(parallel)

        async def run_with_semaphore(scenario: Scenario) -> ScenarioResult:
            async with semaphore:
                return await self.runner.run_async(scenario, model)

        logger.info(f"Running {len(scenarios)} scenarios with {parallel} parallel workers")
        tasks = [run_with_semaphore(s) for s in scenarios]
        self.results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(self.results):
            if isinstance(result, Exception):
                logger.error(f"Scenario {scenarios[i].name} failed with exception: {result}")
                processed_results.append(ScenarioResult(
                    scenario=scenarios[i],
                    agent=scenarios[i].agent,
                    model=model or self.config.default_model,
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    output=None,
                    expected=scenarios[i].expected,
                    metrics=None,
                    passed=False,
                    error=str(result)
                ))
            else:
                processed_results.append(result)

        self.results = processed_results
        return self.results

    def run(self, scenarios: list[Scenario] | None = None,
           model: str | None = None,
           parallel: int | None = None) -> list[ScenarioResult]:
        """Run benchmark synchronously."""
        return asyncio.run(self.run_async(scenarios, model, parallel))

    def get_summary(self) -> dict[str, Any]:
        """Get benchmark summary statistics."""
        if not self.results:
            return {}

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        accuracies = [r.metrics.accuracy for r in self.results if r.metrics]
        latencies = [r.metrics.latency_ms for r in self.results if r.metrics]
        tokens = [r.metrics.token_count for r in self.results if r.metrics]

        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total_scenarios": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total if total > 0 else 0,
            "avg_accuracy": sum(accuracies) / len(accuracies) if accuracies else 0,
            "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
            "total_tokens": sum(tokens),
            "results": [r.to_dict() for r in self.results]
        }

    def save_results(self, output_path: str) -> None:
        """Save benchmark results to JSON file."""
        summary = self.get_summary()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        logger.info(f"Results saved to {output_path}")

    def save_individual_results(self, output_dir: str) -> None:
        """Save each scenario result individually."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        for result in self.results:
            filename = f"{result.scenario.name}_{result.timestamp.replace(':', '-').replace('.', '-')}.json"
            result.save(str(Path(output_dir) / filename))


def compare_results(baseline_path: str, current_path: str,
                   threshold: float = 0.85) -> dict[str, Any]:
    """Compare two benchmark result files."""
    with open(baseline_path) as f:
        baseline = json.load(f)

    with open(current_path) as f:
        current = json.load(f)

    baseline_results = {r['scenario']: r for r in baseline.get('results', [])}
    current_results = {r['scenario']: r for r in current.get('results', [])}

    all_scenarios = set(baseline_results.keys()) | set(current_results.keys())

    comparison = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "baseline_file": baseline_path,
        "current_file": current_path,
        "threshold": threshold,
        "scenarios": {},
        "summary": {
            "total": len(all_scenarios),
            "improved": 0,
            "regressed": 0,
            "unchanged": 0,
            "new": 0,
            "removed": 0
        }
    }

    for scenario_name in all_scenarios:
        base = baseline_results.get(scenario_name)
        curr = current_results.get(scenario_name)

        if base is None:
            comparison["scenarios"][scenario_name] = {
                "status": "new",
                "current": curr
            }
            comparison["summary"]["new"] += 1
        elif curr is None:
            comparison["scenarios"][scenario_name] = {
                "status": "removed",
                "baseline": base
            }
            comparison["summary"]["removed"] += 1
        else:
            base_acc = base.get('metrics', {}).get('accuracy', 0)
            curr_acc = curr.get('metrics', {}).get('accuracy', 0)
            diff = curr_acc - base_acc

            if diff > 0.05:  # Significant improvement
                status = "improved"
                comparison["summary"]["improved"] += 1
            elif diff < -0.05:  # Significant regression
                status = "regressed"
                comparison["summary"]["regressed"] += 1
            else:
                status = "unchanged"
                comparison["summary"]["unchanged"] += 1

            comparison["scenarios"][scenario_name] = {
                "status": status,
                "baseline_accuracy": base_acc,
                "current_accuracy": curr_acc,
                "diff": diff,
                "baseline_passed": base.get('passed', False),
                "current_passed": curr.get('passed', False)
            }

    return comparison


def update_baseline(source_path: str, target_path: str) -> None:
    """Update baseline with current results."""
    import shutil
    shutil.copy2(source_path, target_path)
    logger.info(f"Baseline updated from {source_path} to {target_path}")