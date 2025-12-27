#!/usr/bin/env python3
"""
Qwen3 4B (Unsloth) fine-tuning pipeline + GGUF export.

This script is designed to be refactored into Colab cells later:
- You typically do *installs* (pip/apt) and Google Drive mount in separate Colab cells.
- This file focuses on the training / merge / GGUF export logic.

Key points:
- Base model: unsloth/Qwen3-4B-Instruct-2507-unsloth-bnb-4bit
- Training: QLoRA (4-bit load + LoRA adapters)
- Export: GGUF via Unsloth's save_pretrained_gguf (preferred), with optional manual fallback

References:
- Unsloth: save_pretrained_gguf & save_pretrained_merged
- Qwen3 requires transformers >= 4.51.0

Usage examples (after dependencies are installed):
  python qwen3_4b_unsloth_pipeline.py train \
    --data_path "/content/drive/MyDrive/Spaced Repetition Project/training_data_formatted.jsonl" \
    --output_dir "/content/drive/MyDrive/Spaced Repetition Project/qwen3_4b_flashcard_finetuned_lora"

  python qwen3_4b_unsloth_pipeline.py export-gguf \
    --adapter_dir "/content/drive/MyDrive/Spaced Repetition Project/qwen3_4b_flashcard_finetuned_lora" \
    --gguf_dir   "/content/drive/MyDrive/Spaced Repetition Project/qwen3_4b_flashcard_gguf" \
    --quant      "q4_k_m"
"""
from __future__ import annotations

import argparse
import gc
import os
import platform
import sys
from pathlib import Path
from typing import Optional

# NOTE: imports below require your environment already has these installed:
# pip install -U unsloth "transformers>=4.51.0" trl datasets accelerate peft bitsandbytes
import unsloth
from unsloth import FastLanguageModel

import torch
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig



BASE_MODEL_DEFAULT = "unsloth/Qwen3-4B-Instruct-2507-unsloth-bnb-4bit"


def _print_env():
    import transformers, unsloth  # noqa

    print("Python:", platform.python_version())
    print("Torch:", torch.__version__)
    print("CUDA available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))
    print("Transformers:", transformers.__version__)
    print("Unsloth:", getattr(unsloth, "__version__", "unknown"))


def clear_gpu():
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
    gc.collect()


def get_hf_token() -> Optional[str]:
    # Prefer env vars (works locally + Colab)
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")

    # Optional: Colab Secrets
    try:
        from google.colab import userdata  # type: ignore
        token = token or userdata.get("HF_TOKEN")
    except Exception:
        pass

    return token


def load_jsonl_dataset(data_path: str):
    ds = load_dataset("json", data_files=data_path, split="train")
    if "text" not in ds.column_names:
        raise ValueError(f"Dataset must have a 'text' column. Columns: {ds.column_names}")
    return ds


def tokenize_and_chunk_dataset(ds, tokenizer, max_seq_length: int, min_tokens: int = 64, num_proc: int = 2):
    """
    Turns a JSONL with {"text": "..."} into a dataset with input_ids/attention_mask chunks.
    This is helpful when each example can be extremely long.
    """
    def tokenize_and_chunk(batch):
        out_input_ids, out_attention = [], []
        for text in batch["text"]:
            ids = tokenizer(text, add_special_tokens=False)["input_ids"]
            if tokenizer.eos_token_id is not None:
                ids = ids + [tokenizer.eos_token_id]

            for i in range(0, len(ids), max_seq_length):
                chunk = ids[i:i + max_seq_length]
                if len(chunk) < min_tokens:
                    continue
                out_input_ids.append(chunk)
                out_attention.append([1] * len(chunk))

        return {"input_ids": out_input_ids, "attention_mask": out_attention}

    chunked = ds.map(
        tokenize_and_chunk,
        batched=True,
        remove_columns=ds.column_names,
        num_proc=num_proc,
        desc="tokenize+chunk",
    )
    return chunked


def build_model_and_tokenizer(
    model_name: str,
    max_seq_length: int,
    load_in_4bit: bool = True,
    device_map: str = "auto",
):
    clear_gpu()
    token = get_hf_token()
    load_kwargs = dict(
        model_name=model_name,
        max_seq_length=max_seq_length,
        dtype=None,
        load_in_4bit=load_in_4bit,
        device_map=device_map,
        trust_remote_code=True,
    )
    if token:
        load_kwargs["token"] = token

    model, tokenizer = FastLanguageModel.from_pretrained(**load_kwargs)

    # training does not need KV cache
    try:
        model.config.use_cache = False
    except Exception:
        pass

    # pad token safe
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token or tokenizer.unk_token
    if getattr(model.config, "pad_token_id", None) is None and tokenizer.pad_token_id is not None:
        model.config.pad_token_id = tokenizer.pad_token_id

    return model, tokenizer


def apply_lora(model, r: int = 16, lora_alpha: int = 16, lora_dropout: float = 0.0, seed: int = 42):
    model = FastLanguageModel.get_peft_model(
        model,
        r=r,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=seed,
    )
    return model


def train_lora(
    data_path: str,
    output_dir: str,
    base_model: str = BASE_MODEL_DEFAULT,
    max_seq_length: int = 2048,
    batch_size: int = 1,
    grad_acc: int = 8,
    max_steps: int = 120,
    lr: float = 2e-4,
    min_tokens: int = 64,
    num_proc: int = 2,
):
    if not torch.cuda.is_available():
        raise RuntimeError("GPU not available. In Colab: Runtime -> Change runtime type -> GPU.")

    print("== Environment ==")
    _print_env()

    print("== Dataset ==")
    ds = load_jsonl_dataset(data_path)
    print("Examples:", len(ds))
    print(ds[0]["text"][:200], "...")

    print("== Load model ==")
    model, tokenizer = build_model_and_tokenizer(base_model, max_seq_length=max_seq_length, load_in_4bit=True)

    print("== LoRA ==")
    model = apply_lora(model, r=16, lora_alpha=16, lora_dropout=0.0, seed=42)
    print("Model + LoRA ready.")

    print("== Chunk dataset ==")
    chunked = tokenize_and_chunk_dataset(ds, tokenizer, max_seq_length=max_seq_length, min_tokens=min_tokens, num_proc=num_proc)
    print("Chunks:", len(chunked))

    # fp16 vs bf16: auto
    use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()

    print("== Train ==")
    args = SFTConfig(
        output_dir=output_dir,
        max_length=max_seq_length,   # <- TRL usa max_length
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_acc,
        max_steps=max_steps,
        warmup_steps=10,
        learning_rate=lr,
        logging_steps=10,
        optim="adamw_8bit",
        fp16=not use_bf16,
        bf16=use_bf16,
        report_to="none",
        save_steps=50,
        save_total_limit=2,

        remove_unused_columns=False,
        dataset_kwargs={"skip_prepare_dataset": True},
    )


    # TRL changed tokenizer arg name in some versions, handle both.
    import inspect
    trainer_kwargs = dict(model=model, train_dataset=chunked, args=args)
    sig = inspect.signature(SFTTrainer.__init__)
    if "processing_class" in sig.parameters:
        trainer_kwargs["processing_class"] = tokenizer
    else:
        trainer_kwargs["tokenizer"] = tokenizer

    trainer = SFTTrainer(**trainer_kwargs)
    trainer.train()

    # Save LoRA adapters
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    print("✅ Saved adapter + tokenizer to:", output_dir)


def export_gguf(
    adapter_dir: str,
    gguf_dir: str,
    quant: str = "q4_k_m",
    max_seq_length: int = 2048,
):
    """
    Export a (LoRA) fine-tuned model to GGUF for llama.cpp / Ollama.
    Uses Unsloth's built-in converter:
      model.save_pretrained_gguf("directory", tokenizer, quantization_method="q4_k_m")
    """
    if not torch.cuda.is_available():
        raise RuntimeError("GPU not available. GGUF export can run on CPU, but Unsloth's helper often assumes Colab/GPU env.")

    print("== Environment ==")
    _print_env()

    print("== Load fine-tuned (adapter) model ==")
    model, tokenizer = build_model_and_tokenizer(adapter_dir, max_seq_length=max_seq_length, load_in_4bit=True)

    out = Path(gguf_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"== Export GGUF ({quant}) ==")
    # Unsloth handles merging+conversion internally.
    model.save_pretrained_gguf(str(out), tokenizer, quantization_method=quant)

    print("✅ GGUF saved in:", out)
    print("Tip: run `ls -lh` or `tree` to see the produced .gguf file(s).")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_train = sub.add_parser("train", help="Train LoRA adapters with Unsloth")
    p_train.add_argument("--data_path", required=True)
    p_train.add_argument("--output_dir", required=True)
    p_train.add_argument("--base_model", default=BASE_MODEL_DEFAULT)
    p_train.add_argument("--max_seq_length", type=int, default=2048)
    p_train.add_argument("--batch_size", type=int, default=1)
    p_train.add_argument("--grad_acc", type=int, default=8)
    p_train.add_argument("--max_steps", type=int, default=120)
    p_train.add_argument("--lr", type=float, default=2e-4)
    p_train.add_argument("--min_tokens", type=int, default=64)
    p_train.add_argument("--num_proc", type=int, default=2)

    p_gguf = sub.add_parser("export-gguf", help="Export fine-tuned adapters to GGUF")
    p_gguf.add_argument("--adapter_dir", required=True)
    p_gguf.add_argument("--gguf_dir", required=True)
    p_gguf.add_argument("--quant", default="q4_k_m")
    p_gguf.add_argument("--max_seq_length", type=int, default=2048)

    args = parser.parse_args()

    if args.cmd == "train":
        train_lora(
            data_path=args.data_path,
            output_dir=args.output_dir,
            base_model=args.base_model,
            max_seq_length=args.max_seq_length,
            batch_size=args.batch_size,
            grad_acc=args.grad_acc,
            max_steps=args.max_steps,
            lr=args.lr,
            min_tokens=args.min_tokens,
            num_proc=args.num_proc,
        )
    elif args.cmd == "export-gguf":
        export_gguf(
            adapter_dir=args.adapter_dir,
            gguf_dir=args.gguf_dir,
            quant=args.quant,
            max_seq_length=args.max_seq_length,
        )
    else:
        raise RuntimeError("Unknown command")


if __name__ == "__main__":
    main()
