import json
import click
from flux_worker.orchestrator import generate


@click.group()
def cli():
    pass


@cli.command()
@click.argument("prompts", nargs=-1)
@click.option("--prompts-file", type=click.Path(exists=True), help="JSON file with list of prompts")
@click.option("--output", default="./output", show_default=True, help="Output directory")
@click.option("--hf-token", envvar="HF_TOKEN", help="HuggingFace API token")
@click.option("--model", envvar="HF_MODEL", help="HuggingFace model ID (default: stabilityai/stable-diffusion-xl-base-1.0)")
def generate_cmd(prompts, prompts_file, output, hf_token, model):
    """Generate images from one or more prompts."""
    if prompts_file:
        with open(prompts_file) as f:
            all_prompts = json.load(f)
    else:
        all_prompts = list(prompts)

    if not all_prompts:
        raise click.UsageError("Provide at least one prompt or --prompts-file.")

    result = generate(
        prompts=all_prompts,
        output_dir=output,
        hf_token=hf_token,
        model=model,
    )

    if result.ok:
        for p in result.images:
            click.echo(str(p))
        return

    if result.error_type == "user_error":
        click.echo(f"\n✗ {result.error_message}", err=True)
        raise SystemExit(1)

    # Unexpected error — show message and file bug report
    click.echo(f"\n✗ Unexpected error: {result.error_message}", err=True)
    click.echo("\n  Filing bug report...", err=True)

    from flux_worker.bug_report import file_report
    report = file_report(result.error_message, result.traceback)

    if "issue_url" in report:
        click.echo(f"\n  Bug report filed: {report['issue_url']}", err=True)
    click.echo(f"\n  Or report manually: {report['fallback_url']}", err=True)
    raise SystemExit(1)


cli.add_command(generate_cmd, name="generate")
