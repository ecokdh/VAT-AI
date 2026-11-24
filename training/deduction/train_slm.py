"""Qwen3-4B-Instruct를 공제 판정(JudgeOutput JSON) 과제로 LoRA 파인튜닝한다. GPU 서버(DGX Spark)에서 실행한다.
앱 코드에 의존하지 않으므로 이 파일과 data/train.jsonl·val.jsonl만 서버에 올리면 된다.

먼저 몇 단계만 돌려 설정과 손실 마스킹을 확인한다:
    python train_slm.py --data data --output outputs/smoke --smoke
본 학습(중단됐으면 같은 명령에 --resume):
    python train_slm.py --data data --output outputs/qwen3-4b-deduction
"""
import argparse
import json
import random
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from torch.utils.data import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments

LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def messages(row: dict, with_answer: bool) -> list[dict]:
    out = [{"role": "system", "content": row["system"]}, {"role": "user", "content": row["prompt"]}]
    return out + [{"role": "assistant", "content": row["answer"]}] if with_answer else out


class JudgeDataset(Dataset):
    def __init__(self, path: Path, limit: int | None = None, seed: int = 7):
        rows = [json.loads(line) for line in open(path, encoding="utf-8")]
        if limit and limit < len(rows):
            rows = random.Random(seed).sample(rows, limit)
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


class Collator:
    """답변 토큰만 손실에 넣고, 지시문·프롬프트·패딩 토큰은 -100으로 가린다."""

    def __init__(self, tokenizer, max_len: int):
        self.tokenizer = tokenizer
        self.max_len = max_len

    def encode(self, row: dict) -> tuple[list[int], list[int]]:
        t = self.tokenizer
        prompt = t.apply_chat_template(messages(row, False), tokenize=False, add_generation_prompt=True)
        full = t.apply_chat_template(messages(row, True), tokenize=False)
        prompt_ids = t(prompt, add_special_tokens=False)["input_ids"]
        full_ids = t(full, add_special_tokens=False)["input_ids"]
        # 채팅 템플릿이 답변 앞부분을 바꾸면 마스킹 위치가 틀어지므로 학습 전에 멈춘다.
        if full_ids[: len(prompt_ids)] != prompt_ids:
            raise ValueError(f"{row['id']}: 프롬프트 토큰이 전체 토큰의 앞부분과 다릅니다(채팅 템플릿 확인 필요).")
        if len(full_ids) > self.max_len:
            raise ValueError(f"{row['id']}: {len(full_ids)} 토큰으로 --max-len {self.max_len}을 넘습니다.")
        return full_ids, [-100] * len(prompt_ids) + full_ids[len(prompt_ids):]

    def __call__(self, batch):
        encoded = [self.encode(row) for row in batch]
        width = max(len(ids) for ids, _ in encoded)
        pad = self.tokenizer.pad_token_id
        return {
            "input_ids": torch.tensor([ids + [pad] * (width - len(ids)) for ids, _ in encoded]),
            "attention_mask": torch.tensor([[1] * len(ids) + [0] * (width - len(ids)) for ids, _ in encoded]),
            "labels": torch.tensor([labels + [-100] * (width - len(labels)) for _, labels in encoded]),
        }


def show_mask(collator: Collator, row: dict) -> None:
    """smoke 실행 때 학습 대상 토큰(답변)과 길이를 보여 준다."""
    ids, labels = collator.encode(row)
    target = [i for i, label in zip(ids, labels) if label != -100]
    print(f"[mask] 전체 {len(ids)} 토큰 중 학습 대상 {len(target)} 토큰")
    print("[mask] 학습 대상:", collator.tokenizer.decode(target))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("outputs/qwen3-4b-deduction"))
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--epochs", type=float, default=1)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=16)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--max-len", type=int, default=12288)
    parser.add_argument("--resume", action="store_true", help="--output의 마지막 체크포인트에서 이어서 학습한다")
    parser.add_argument("--val-limit", type=int, default=200, help="에폭마다 손실을 잴 검증 샘플 수")
    parser.add_argument("--smoke", action="store_true", help="데이터 8개로 2단계만 돌려 설정을 확인한다")
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    tokenizer.padding_side = "right"
    collator = Collator(tokenizer, args.max_len)
    limit = 8 if args.smoke else None
    train = JudgeDataset(args.data / "train.jsonl", limit)
    val = JudgeDataset(args.data / "val.jsonl", limit or args.val_limit)
    # 모델을 올리기 전에 전체 데이터의 마스킹·길이를 미리 검사한다(CPU, 수십 초).
    lengths = [len(collator.encode(row)[0]) for row in train.rows + val.rows]
    print(f"[data] train {len(train)} / val {len(val)}, 토큰 길이 평균 {sum(lengths) // len(lengths)} · 최대 {max(lengths)}")
    if args.smoke:
        show_mask(collator, train[0])

    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16, attn_implementation="sdpa")
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=args.lora_r, lora_alpha=args.lora_r * 2, lora_dropout=0.05,
                                             target_modules=LORA_TARGETS, task_type="CAUSAL_LM"))
    model.print_trainable_parameters()

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
            warmup_steps=0 if args.smoke else 10,  # transformers 5는 warmup_ratio를 받지 않는다.
            bf16=True,
            logging_steps=1 if args.smoke else 10,
            eval_strategy="no" if args.smoke else "steps",
            eval_steps=50,
            save_strategy="no" if args.smoke else "steps",
            save_steps=50,
            save_total_limit=2,
            remove_unused_columns=False,
            dataloader_num_workers=0,
            report_to="none",
        ),
        train_dataset=train,
        eval_dataset=val,
        data_collator=collator,
    )
    trainer.train(resume_from_checkpoint=args.resume or None)
    model.save_pretrained(args.output / "adapter")
    tokenizer.save_pretrained(args.output / "adapter")
    print("saved:", args.output / "adapter")


if __name__ == "__main__":
    main()
