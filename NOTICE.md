# Model attribution

AI-Shop uses pretrained **Qwen3-4B-Instruct-2507** weights from the Qwen team,
quantized as **Q4_K_M GGUF** by Unsloth. The model is Apache 2.0 licensed.
No model weights, store-specific data or chat records are included in this repository.

- Original model and license: https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507
- Quantized distribution: https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF
- Pinned revision, size and SHA-256: [model.json](ai_shop/resources/model.json)
- Python CPU runtime (MIT): https://github.com/abetlen/llama-cpp-python

Application instructions, catalogue retrieval and reviewed public knowledge do not
constitute training a new base model. Downloading public weights and packages uses
the Internet once; ordinary generation after installation takes place on the host.
