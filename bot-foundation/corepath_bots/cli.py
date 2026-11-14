"""Local command-line entry point; never sends notifications or deploys services."""

import argparse
import json
from pathlib import Path

from .contracts import Source
from .demo import DemoProvider, demo_sources
from .provider import OpenAIProvider
from .registry import BUILDER_STAGES, instructions, policy_hash, roles
from .team import Team


def main():
    parser = argparse.ArgumentParser(description="CorePath bot foundation (development/review)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalogue", help="List approved role definitions and policy hashes")
    export = commands.add_parser("export-instructions", help="Export the exact versioned bot instructions")
    export.add_argument("directory")
    demo = commands.add_parser("demo", help="Run a synthetic offline all-eleven discussion")
    demo.add_argument("--output")
    discuss = commands.add_parser("discuss", help="Run a real model discussion with supplied approved sources")
    discuss.add_argument("--mode", choices=["auto", "full"], default="auto")
    discuss.add_argument("--max-specialists", type=int, choices=range(1, 12), default=11,
                         help="Spending ceiling, not a quota; all eleven remain available")
    discuss.add_argument("--peer-review", action="store_true", help="Request a second review round")
    discuss.add_argument("--question", required=True)
    discuss.add_argument("--sources", required=True, help="JSON array of approved public Source objects")
    discuss.add_argument("--approve-team-question", action="store_true")
    discuss.add_argument("--allow-model-processing", action="store_true")
    discuss.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "catalogue":
        print(json.dumps({key: {**value, "policy_hash": policy_hash(key)} for key, value in roles().items()}, indent=2))
    elif args.command == "export-instructions":
        destination = Path(args.directory)
        destination.mkdir(parents=True, exist_ok=True)
        for key in roles():
            (destination / (key + ".md")).write_text(instructions(key) + "\n")
            for stage in sorted(BUILDER_STAGES.get(key, set())):
                (destination / (key + "--" + stage + ".md")).write_text(instructions(key, stage) + "\n")
        print(f"Exported {len(roles())} roles and their stage-specific draft instructions.")
    else:
        if args.command == "demo":
            report = Team(DemoProvider()).discuss("Demonstrate the all-eleven collaboration workflow.", demo_sources(),
                                                  approved_for_all_specialists=True, mode="full")
        else:
            if not args.approve_team_question:
                parser.error("Review the exact question, then supply --approve-team-question")
            provider = OpenAIProvider(allow_model_processing=args.allow_model_processing)
            sources = [Source.model_validate(s) for s in json.loads(Path(args.sources).read_text())]
            report = Team(provider).discuss(args.question, sources, approved_for_all_specialists=True,
                                            mode=args.mode, max_specialists=args.max_specialists,
                                            review_round=args.peer_review)
        output = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(output + "\n")
            print(f"Saved {report['state']} discussion draft ({report['calls_attempted']} calls attempted).")
        else:
            print(output)


if __name__ == "__main__":
    main()
