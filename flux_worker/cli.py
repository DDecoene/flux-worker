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
@click.option("--vastai-key", envvar="VASTAI_API_KEY", help="Vast.ai API key")
@click.option("--max-gpu-price", type=float, envvar="MAX_GPU_PRICE", help="Max $/hr (default: 0.50)")
@click.option("--min-vram-gb", type=int, envvar="MIN_VRAM_GB", help="Min VRAM in GB (default: 16)")
@click.option("--min-cuda-version", type=float, envvar="MIN_CUDA_VERSION", help="Min CUDA version (default: 12.0)")
@click.option("--disk-gb", type=int, envvar="DISK_GB", help="Disk GB for instance (default: 50)")
@click.option("--ssh-key-path", envvar="SSH_KEY_PATH", help="SSH private key path")
def generate_cmd(prompts, prompts_file, output, vastai_key, max_gpu_price, min_vram_gb, min_cuda_version, disk_gb, ssh_key_path):
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
        vastai_api_key=vastai_key,
        max_gpu_price=max_gpu_price,
        min_vram_gb=min_vram_gb,
        min_cuda_version=min_cuda_version,
        disk_gb=disk_gb,
        ssh_key_path=ssh_key_path,
    )

    if result.ok:
        for p in result.images:
            click.echo(str(p))
        return

    # Handle errors
    if result.error_type == "user_error":
        click.echo(f"\n✗ {result.error_message}", err=True)
        raise SystemExit(1)

    if result.error_type == "vastai_error":
        click.echo(f"\n✗ {result.error_message}", err=True)
        click.echo("  → https://console.vast.ai", err=True)
        raise SystemExit(1)

    # Unexpected error — show message and file bug report
    click.echo(f"\n✗ Unexpected error: {result.error_message}", err=True)
    click.echo("\n  Filing bug report...", err=True)

    from flux_worker.bug_report import file_report
    report = file_report(result.error_message, result.traceback, result.config)

    if "issue_url" in report:
        click.echo(f"\n  Bug report filed: {report['issue_url']}", err=True)
    click.echo(f"\n  Or report manually: {report['fallback_url']}", err=True)
    raise SystemExit(1)


cli.add_command(generate_cmd, name="generate")
