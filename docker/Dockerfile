FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y python3 python3-pip git && rm -rf /var/lib/apt/lists/*

RUN pip3 install torch --index-url https://download.pytorch.org/whl/cu121
RUN pip3 install diffusers transformers accelerate sentencepiece protobuf

ARG HF_TOKEN
RUN python3 -c "\
from huggingface_hub import snapshot_download; \
snapshot_download( \
    'black-forest-labs/FLUX.1-schnell', \
    local_dir='/model', \
    token='${HF_TOKEN}', \
)"

COPY worker.py /worker.py

CMD ["python3", "/worker.py"]
