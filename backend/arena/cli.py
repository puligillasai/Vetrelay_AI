#!/usr/bin/env python3
"""
Arena CLI - Run scenarios and benchmarks from command line
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.arena.config import ArenaConfig
from backend.arena.scenario import Scenario
from backend.arena.runner import ScenarioRunner
from backend.arena.benchmark import Benchmark, compare_results, update_baseline


def run_scenario(args):
    """Run a single scenario."""
    config = ArenaConfig.default()

    # Load scenario
    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        # Try in scenarios dir
        scenario_path = Path(config.scenarios_dir) / f"{args.scenario}.yaml"
    if not scenario_path.exists():
        scenario_path = Path(config.scenarios_dir) / f"{args.scenario}.yml"

    if not scenario_path.exists():
        print(f"Error: Scenario not found: {args.scenario}")
        sys.exit(1)

    scenario = Scenario.from_yaml(str(scenario_path))
    print(f"Running scenario: {scenario.name}")
    print(f"Agent: {scenario.agent}")
    print(f"Description: {scenario.description}")
    print("-" * 50)

    runner = ScenarioRunner(config)
    result = runner.run(scenario, args.model)

    # Print results
    print(f"Status: {'PASSED' if result.passed else 'FAILED'}")
    print(f"Accuracy: {result.metrics.accuracy:.2%}")
    print(f"Latency: {result.metrics.latency_ms:.0f}ms")
    print(f"Tokens: {result.metrics.token_count}")
    print(f"Handoff Correctness: {result.metrics.handoff_correctness:.2%}")

    if result.diff:
        print("\nDifferences:")
        for key, diff in result.diff.items():
            print(f"  {key}:")
            print(f"    Expected: {diff.get('expected')}")
            print(f"    Actual:   {diff.get('actual')}")

    if result.error:
        print(f"\nError: {result.error}")

    # Save result if requested
    if args.output:
        result.save(args.output)
        print(f"\nResult saved to: {args.output}")

    # Compare with baseline if requested
    if args.compare_baseline:
        baseline_path = Path(config.baseline_dir) / f"{scenario.name}.json"
        if baseline_path.exists():
            baseline_result = ScenarioResult.load(str(baseline_path))
            print(f"\nBaseline Comparison:")
            print(f"  Baseline Accuracy: {baseline_result.metrics.accuracy:.2%}")
            print(f"  Current Accuracy:  {result.metrics.accuracy:.2%}")
            diff = result.metrics.accuracy - baseline_result.metrics.accuracy
            print(f"  Difference: {diff:+.2%}")
        else:
            print(f"\nNo baseline found at {baseline_path}")

    sys.exit(0 if result.passed else 1)


def run_benchmark(args):
    """Run full benchmark suite."""
    config = ArenaConfig.default()

    if args.config:
        config = ArenaConfig.from_yaml(args.config)

    benchmark = Benchmark(config)

    # Discover scenarios
    scenarios = benchmark.discover_scenarios(args.scenarios_dir)
    print(f"Found {len(scenarios)} scenarios")

    if not scenarios:
        print("No scenarios found!")
        sys.exit(1)

    # Filter by agent if specified
    if args.agent:
        scenarios = [s for s in scenarios if s.agent == args.agent]
        print(f"Filtered to {len(scenarios)} scenarios for agent: {args.agent}")

    # Filter by tags if specified
    if args.tags:
        tag_set = set(args.tags)
        scenarios = [s for s in scenarios if tag_set & set(s.tags)]
        print(f"Filtered to {len(scenarios)} scenarios with tags: {args.tags}")

    # Run benchmark
    print(f"Running benchmark with {config.parallel_workers} workers...")
    results = benchmark.run(scenarios, args.model, config.parallel_workers)

    # Print summary
    summary = benchmark.get_summary()
    print("\n" + "=" * 50)
    print("BENCHMARK SUMMARY")
    print("=" * 50)
    print(f"Total Scenarios: {summary['total_scenarios']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Pass Rate: {summary['pass_rate']:.2%}")
    print(f"Avg Accuracy: {summary['avg_accuracy']:.2%}")
    print(f"Avg Latency: {summary['avg_latency_ms']:.0f}ms")
    print(f"Total Tokens: {summary['total_tokens']}")

    # Save results
    output_path = args.output or f"arena/results/benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    benchmark.save_results(output_path)
    print(f"\nResults saved to: {output_path}")

    # Save individual results if requested
    if args.save_individual:
        benchmark.save_individual_results(config.results_dir)
        print(f"Individual results saved to: {config.results_dir}")

    # Fail on regression if requested
    if args.fail_on_regression:
        baseline_path = Path(config.baseline_dir) / "main.json"
        if baseline_path.exists():
            comparison = compare_results(str(baseline_path), output_path,
                                       config.evaluation.similarity_threshold)
            if comparison['summary']['regressed'] > 0:
                print(f"\n⚠️  REGRESSION DETECTED: {comparison['summary']['regressed']} scenarios regressed")
                for name, data in comparison['scenarios'].items():
                    if data['status'] == 'regressed':
                        print(f"  - {name}: {data['baseline_accuracy']:.2%} → {data['current_accuracy']:.2%} ({data['diff']:+.2%})")
                sys.exit(1)
            else:
                print("\n✓ No regressions detected")
        else:
            print("\nNo baseline found for regression check")

    sys.exit(0 if summary['failed'] == 0 else 1)


def compare_cmd(args):
    """Compare two result files."""
    comparison = compare_results(args.baseline, args.current, args.threshold)

    print("=" * 50)
    print("COMPARISON RESULTS")
    print("=" * 50)
    print(f"Baseline: {comparison['baseline_file']}")
    print(f"Current:  {comparison['current_file']}")
    print(f"Threshold: {comparison['threshold']}")
    print()
    print(f"Total Scenarios: {comparison['summary']['total']}")
    print(f"  Improved:   {comparison['summary']['improved']}")
    print(f"  Regressed:  {comparison['summary']['regressed']}")
    print(f"  Unchanged:  {comparison['summary']['unchanged']}")
    print(f"  New:        {comparison['summary']['new']}")
    print(f"  Removed:    {comparison['summary']['removed']}")
    print()

    for name, data in comparison['scenarios'].items():
        if data['status'] != 'unchanged':
            status_icon = {'improved': '↑', 'regressed': '↓', 'new': '+', 'removed': '-'}.get(data['status'], '?')
            if data['status'] in ['improved', 'regressed']:
                print(f"  {status_icon} {name}: {data['baseline_accuracy']:.2%} → {data['current_accuracy']:.2%} ({data['diff']:+.2%})")
            else:
                print(f"  {status_icon} {name}: {data['status']}")

    if args.output:
        import json
        with open(args.output, 'w') as f:
            json.dump(comparison, f, indent=2, default=str)
        print(f"\nComparison saved to: {args.output}")

    sys.exit(0 if comparison['summary']['regressed'] == 0 else 1)


def update_baseline_cmd(args):
    """Update baseline with current results."""
    update_baseline(args.source, args.target)
    print(f"Baseline updated: {args.target}")


def list_scenarios(args):
    """List all available scenarios."""
    config = ArenaConfig.default()
    benchmark = Benchmark(config)
    scenarios = benchmark.discover_scenarios(args.dir)

    print(f"Available Scenarios ({len(scenarios)}):")
    print()

    # Group by agent
    by_agent = {}
    for s in scenarios:
        by_agent.setdefault(s.agent, []).append(s)

    for agent, agent_scenarios in sorted(by_agent.items()):
        print(f"  {agent}:")
        for s in sorted(agent_scenarios, key=lambda x: x.name):
            tags = f" [{', '.join(s.tags)}]" if s.tags else ""
            print(f"    - {s.name}{tags}: {s.description}")
        print()


def init_config(args):
    """Initialize default configuration file."""
    config = ArenaConfig.default()
    config.to_yaml(args.output)
    print(f"Default configuration saved to: {args.output}")


def main():
    parser = argparse.ArgumentParser(description="Arena - Vetrelay AI Agent Testing & Benchmarking")
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # run-scenario
    run_parser = subparsers.add_parser('run', help='Run a single scenario')
    run_parser.add_argument('scenario', help='Scenario name or path')
    run_parser.add_argument('--model', help='Model to use')
    run_parser.add_argument('--output', '-o', help='Output file for result')
    run_parser.add_argument('--compare-baseline', action='store_true', help='Compare with baseline')
    run_parser.set_defaults(func=run_scenario)

    # benchmark
    bench_parser = subparsers.add_parser('benchmark', help='Run full benchmark suite')
    bench_parser.add_argument('--config', '-c', help='Config file path')
    bench_parser.add_argument('--scenarios-dir', help='Scenarios directory')
    bench_parser.add_argument('--model', help='Model to use')
    bench_parser.add_argument('--output', '-o', help='Output file for results')
    bench_parser.add_argument('--save-individual', action='store_true', help='Save individual results')
    bench_parser.add_argument('--agent', help='Filter by agent')
    bench_parser.add_argument('--tags', nargs='+', help='Filter by tags')
    bench_parser.add_argument('--fail-on-regression', action='store_true', help='Fail if regression detected')
    bench_parser.set_defaults(func=run_benchmark)

    # compare
    compare_parser = subparsers.add_parser('compare', help='Compare two result files')
    compare_parser.add_argument('baseline', help='Baseline results file')
    compare_parser.add_argument('current', help='Current results file')
    compare_parser.add_argument('--threshold', type=float, default=0.85, help='Similarity threshold')
    compare_parser.add_argument('--output', '-o', help='Output file for comparison')
    compare_parser.set_defaults(func=compare_cmd)

    # update-baseline
    update_parser = subparsers.add_parser('update-baseline', help='Update baseline with current results')
    update_parser.add_argument('source', help='Source results file')
    update_parser.add_argument('target', help='Target baseline file')
    update_parser.set_defaults(func=update_baseline_cmd)

    # list
    list_parser = subparsers.add_parser('list', help='List available scenarios')
    list_parser.add_argument('--dir', help='Scenarios directory')
    list_parser.set_defaults(func=list_scenarios)

    # init-config
    init_parser = subparsers.add_parser('init-config', help='Initialize default configuration')
    init_parser.add_argument('--output', '-o', default='arena/config.yaml', help='Output file')
    init_parser.set_defaults(func=init_config)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    from datetime import datetime
    main()