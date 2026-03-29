import time
from pathlib import Path
from flux_worker.config import load_config
from flux_worker import vastai


def generate(
    prompts,
    output_dir="./output",
    vastai_api_key=None,
    ssh_key_path=None,
    max_gpu_price=None,
    min_vram_gb=None,
    min_cuda_version=None,
    disk_gb=None,
) -> list:
    if isinstance(prompts, str):
        prompts = [prompts]

    config = load_config(
        vastai_api_key=vastai_api_key,
        ssh_key_path=ssh_key_path,
        max_gpu_price=max_gpu_price,
        min_vram_gb=min_vram_gb,
        min_cuda_version=min_cuda_version,
        disk_gb=disk_gb,
        output_dir=output_dir,
    )
    config.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Finding GPU (max ${config.max_gpu_price}/hr, {config.min_vram_gb}GB VRAM)...")
    offer = vastai.find_offer(
        config.vastai_api_key,
        config.max_gpu_price,
        config.min_vram_gb,
        config.min_cuda_version,
    )
    print(f"Found: {offer['gpu_name']} @ ${offer['dph_total']:.3f}/hr (id={offer['id']})")

    instance_id = None
    try:
        print("Renting instance...")
        result = vastai.create_instance(
            config.vastai_api_key,
            offer["id"],
            prompts,
            config.disk_gb,
        )
        instance_id = result["new_contract"]
        print(f"Instance {instance_id} created. Waiting for SSH...")

        host, port = _wait_for_running(config.vastai_api_key, instance_id)
        vastai.wait_for_ssh(host, port, config.ssh_key_path)
        print("SSH ready. Generating images...")

        paths = _poll_and_download(config, host, port, prompts)
        return paths

    finally:
        if instance_id:
            print(f"Destroying instance {instance_id}...")
            try:
                vastai.destroy_instance(config.vastai_api_key, instance_id)
                print("Instance destroyed.")
            except Exception as e:
                print(f"Warning: failed to destroy instance {instance_id}: {e}")


def _wait_for_running(api_key: str, instance_id: int, timeout: int = 300):
    """Poll until instance is running, return (host, port)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        inst = vastai.get_instance(api_key, instance_id)
        if inst and inst.get("actual_status") == "running":
            return inst["ssh_host"], inst["ssh_port"]
        time.sleep(5)
    raise TimeoutError(f"Instance {instance_id} did not reach running state after {timeout}s")


def _poll_and_download(config, host: str, port: int, prompts: list) -> list:
    """Poll for done_N sentinels, download image_N.png as each appears."""
    paths = [None] * len(prompts)
    remaining = set(range(len(prompts)))

    while remaining:
        for i in list(remaining):
            sentinel = f"/output/done_{i}"
            if vastai.file_exists_ssh(host, port, config.ssh_key_path, sentinel):
                status = vastai.read_file_ssh(host, port, config.ssh_key_path, sentinel)
                if status != "ok":
                    raise RuntimeError(f"Worker failed on prompt {i}: {status}")
                local_path = config.output_dir / f"image_{i}.png"
                print(f"Downloading image {i+1}/{len(prompts)}...")
                vastai.download_file_ssh(host, port, config.ssh_key_path, f"/output/image_{i}.png", local_path)
                print(f"Saved: {local_path}")
                paths[i] = local_path
                remaining.remove(i)
        if remaining:
            time.sleep(5)

    return paths
