"""Qwen3-VL-4B-Instruct를 신고서 read/locate 과제로 LoRA 파인튜닝한다. GPU 서버(DGX Spark)에서 실행한다.

먼저 몇 단계만 돌려 설정을 확인한다:
    python train_lora.py --data data --output outputs/smoke --smoke
본 학습:
    python train_lora.py --data data --output outputs/qwen3vl4b-lora
"""
import argparse
import json
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from PIL import Image
from torch.utils.data import Dataset
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration, Trainer, TrainingArguments

from vatform.prompts import assistant_message, user_message

# 언어 모델 쪽 선형층에만 LoRA를 붙인다. 비전 인코더는 고정한다.
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


class FormDataset(Dataset):
    def __init__(self, root: Path, split: str, limit: int | None = None):
        self.root = root
        rows = [json.loads(line) for line in open(root / f"{split}.jsonl", encoding="utf-8")]
        self.rows = rows[:limit] if limit else rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        row = self.rows[i]
        return {"image": Image.open(self.root / row["image"]).convert("RGB"), "prompt": row["prompt"], "answer": row["answer"]}


class Collator:
    """답변 토큰만 손실에 넣고, 지시문·이미지·패딩 토큰은 -100으로 가린다."""

    def __init__(self, processor):
        self.processor = processor

    def __call__(self, batch):
        p = self.processor
        prompts = [p.apply_chat_template([user_message(b["prompt"])], tokenize=False, add_generation_prompt=True) for b in batch]
        fulls = [p.apply_chat_template([user_message(b["prompt"]), assistant_message(b["answer"])], tokenize=False) for b in batch]
        images = [b["image"] for b in batch]
        inputs = p(text=fulls, images=images, padding=True, return_tensors="pt")
        labels = inputs["input_ids"].clone()
        for i, (prompt, image) in enumerate(zip(prompts, images)):
            prompt_len = p(text=[prompt], images=[image], return_tensors="pt")["input_ids"].shape[1]
            labels[i, :prompt_len] = -100
        labels[inputs["attention_mask"] == 0] = -100
        inputs["labels"] = labels
        return inputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("outputs/qwen3vl4b-lora"))
    parser.add_argument("--model", default="Qwen/Qwen3-VL-4B-Instruct")
    parser.add_argument("--epochs", type=float, default=2)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--smoke", action="store_true", help="데이터 8개로 2단계만 돌려 설정을 확인한다")
    args = parser.parse_args()

    processor = AutoProcessor.from_pretrained(args.model)
    processor.tokenizer.padding_side = "right"
    model = Qwen3VLForConditionalGeneration.from_pretrained(args.model, dtype=torch.bfloat16, attn_implementation="sdpa")
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=args.lora_r, lora_alpha=args.lora_r * 2, lora_dropout=0.05,
                                             target_modules=LORA_TARGETS, task_type="CAUSAL_LM"))
    model.print_trainable_parameters()

    limit = 8 if args.smoke else None
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(args.output),
            num_train_epochs=args.epochs,
            max_steps=2 if args.smoke else -1,
            per_device_train_batch_size=args.batch,
            per_device_eval_batch_size=args.batch,
            gradient_accumulation_steps=1 if args.smoke else args.grad_accum,
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            warmup_steps=0 if args.smoke else 20,  # transformers 5는 warmup_ratio를 받지 않는다.
            bf16=True,
            logging_steps=1 if args.smoke else 10,
            eval_strategy="no" if args.smoke else "epoch",
            save_strategy="no" if args.smoke else "epoch",
            save_total_limit=2,
            remove_unused_columns=False,
            dataloader_num_workers=0 if args.smoke else 4,
            report_to="none",
        ),
        train_dataset=FormDataset(args.data, "train", limit),
        eval_dataset=FormDataset(args.data, "val", limit),
        data_collator=Collator(processor),
    )
    trainer.train()
    model.save_pretrained(args.output / "adapter")
    processor.save_pretrained(args.output / "adapter")
    print("saved:", args.output / "adapter")


if __name__ == "__main__":
    main()
