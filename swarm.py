#!/usr/bin/env python3
"""
🦞 Agent Research Swarm
Multi-agent research system using local LLMs via LM Studio or Ollama.

Usage:
  python swarm.py setup                    # First-time setup wizard
  python swarm.py status                   # Check server connectivity
  python swarm.py query "your question"    # Run a research query
  python swarm.py query --pick             # Pick models interactively, then query
  python swarm.py query --preset research  # Use a preset template
  python swarm.py chat                     # Multi-turn conversation mode
  python swarm.py presets                  # List available preset templates
  python swarm.py config show              # Show current configuration
  python swarm.py config edit              # Edit configuration via wizard
"""

import click

from cli.commands import setup, status, query, chat, presets, config


@click.group(invoke_without_command=True)
@click.pass_context
@click.argument("question", required=False)
def cli(ctx, question):
    """
    🦞 Agent Research Swarm — multi-agent research using local LLMs.

    Run 'swarm setup' on first use to configure your models.
    """
    if ctx.invoked_subcommand is None:
        if question:
            # Backward compat: swarm "question" → swarm query "question"
            ctx.invoke(query, question=question)
        else:
            click.echo(ctx.get_help())


cli.add_command(setup)
cli.add_command(status)
cli.add_command(query)
cli.add_command(chat)
cli.add_command(presets)
cli.add_command(config)


if __name__ == "__main__":
    cli()
