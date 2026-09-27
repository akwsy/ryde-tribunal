# Kaggle platform setup

This is the first step in the fine-tuning work. The attached notebook is a hardware check only: it does not access dispute data, download a model, or train anything.

## Run the platform check

1. Sign in to Kaggle and create a new notebook.
2. Upload `kaggle-platform-check.ipynb` from this folder.
3. In the notebook settings, select **GPU T4 x2** as the accelerator.
4. Run the notebook and save the output showing the GPU names and memory.
5. Check Kaggle's account quota display. Kaggle's published quota is typically 30 GPU hours per week, but availability can vary and GPU sessions may queue.

The current Kaggle announcement says P100 was retired on 15 September 2026 and T4 x2 remains available. Kaggle's general notebook documentation still contains stale P100 references, so the notebook checks the actual accelerator attached to your account rather than relying on that old listing.

## What this establishes

The M5 Mac is only used to access Kaggle; training runs on Kaggle's GPU. T4 x2 means two T4 devices with 16 GiB each, but usable memory for one training process depends on how the training job uses multiple GPUs. The first training candidate should therefore be small and selected after the hardware check. A possible candidate for later evaluation is Qwen2.5-1.5B-Instruct with LoRA through Hugging Face TRL/PEFT; this is not yet a final model choice.

Kaggle GPU access is free within its current quota and availability limits. Kaggle's docs say GPU sessions can queue during busy periods; its published execution limit is 12 hours per notebook session. Do not start a paid upgrade if the free accelerator is unavailable.

## Data boundary for this step

Do not add company exports, dispute examples, reviewer decisions, API keys, or other private data to this notebook or Git. No Singapore transport datasets will be used. After the platform check succeeds, the next work is to define the eligible training data and create an independent held-out evaluation benchmark. Fine-tuning comes after those are ready.

Kaggle notebooks and datasets are stored on Kaggle even when their visibility is private. Before uploading company-derived training examples, review Kaggle's current terms and confirm the data owner permits storage and processing there. The existing approval to send imported data to external models authorizes model processing; it does not by itself answer how long Kaggle should retain uploaded files. The training data will not be uploaded at this platform-check stage.

## References

- [Kaggle announcement: P100 retirement and T4 x2](https://www.kaggle.com/product-announcements/735239)
- [Kaggle GPU quota guidance](https://www.kaggle.com/docs/efficient-gpu-usage)
- [Kaggle notebook runtime limits and specifications](https://www.kaggle.com/docs/notebooks)
- [Qwen2.5-1.5B-Instruct model card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct)
- [Hugging Face TRL SFT Trainer](https://huggingface.co/docs/trl/sft_trainer)
