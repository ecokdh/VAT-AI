"""Offline quality comparison. Never imported by the receipt processing path.

Run with a separate PyTorch runtime: python -m app.receipts.quality_experiment ROOT.
Real quality labels are assistant drafts; induced-condition scores are separate.
"""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import random
import time

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import torch
from torch import nn
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights

from app.receipts.fingerprints import image_fingerprints
from app.receipts.quality import inspect_receipt_image

LABELS = ["blur", "low_light", "crop", "skew"]
SEED = 20261005


def attach_visual_candidates(root, manifest):
    """Retain image-bound drafts without promoting them to quality ground truth."""
    path = root / "quality_real_label_candidates.json"
    if not path.exists():
        return {"candidate_count": 0, "independently_reviewed_count": 0}
    candidates = json.loads(path.read_text(encoding="utf-8"))
    originals = {row["id"]: row for row in manifest}
    seen = set()
    for candidate in candidates["records"]:
        id_ = candidate["id"]
        if id_ in seen or id_ not in originals:
            raise ValueError(f"Unknown or repeated quality candidate: {id_}")
        seen.add(id_)
        original = originals[id_]
        if any(candidate.get(key) != original[key] for key in ("image", "sha256", "split")):
            raise ValueError(f"Quality candidate image or split changed: {id_}")
        labels = candidate.get("labels", {})
        if set(labels) != set(LABELS) or any(type(value) is not bool for value in labels.values()):
            raise ValueError(f"Quality candidate labels must be four booleans: {id_}")
        if candidate.get("label_status") != "ASSISTANT_DRAFT" or candidate.get("independently_reviewed") is not False:
            raise ValueError(f"Draft loader requires explicit unreviewed assistant status: {id_}")
        original["visual_candidate"] = {key: candidate[key] for key in
            ("labels", "label_status", "independently_reviewed", "inspection", "visual_observations")}
        original["real_labels"] = None
        original["real_label_status"] = "UNREVIEWED"
    return {"candidate_count": len(seen), "independently_reviewed_count": 0,
        "candidate_source": path.name, "candidate_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "individual_original_inspected_count": sum(row.get("visual_candidate", {}).get("inspection") in
            ("individual_original", "contact_sheet_and_individual_image") for row in manifest),
        "scope": "Assistant drafts only; excluded from training, threshold selection and real-quality metrics"}


def metric(y, p):
    rows = {}
    for k, name in enumerate(LABELS):
        tp = int(((y[:, k] == 1) & (p[:, k] == 1)).sum())
        fp = int(((y[:, k] == 0) & (p[:, k] == 1)).sum())
        fn = int(((y[:, k] == 1) & (p[:, k] == 0)).sum())
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        rows[name] = {"tp": tp, "fp": fp, "fn": fn, "support": int(y[:, k].sum()),
                      "precision": precision, "recall": recall,
                      "f1": 2 * tp / (2 * tp + fp + fn) if y[:, k].sum() else None}
    normal = y.sum(axis=1) == 0
    return {"fields": rows, "normal_count": int(normal.sum()),
            "normal_false_rejection_rate": float(p[normal].any(axis=1).mean()) if normal.any() else None}


def tensor(image):
    image = ImageOps.pad(image, (224, 224), color="white", method=Image.Resampling.BILINEAR)
    values = torch.from_numpy(np.asarray(image).copy()).permute(2, 0, 1).float() / 255
    return (values - torch.tensor([.485, .456, .406])[:, None, None]) / torch.tensor([.229, .224, .225])[:, None, None]


def induce(image, flags, rng, training=False):
    image = image.copy()
    scale = max(image.size) / 224
    if flags[0]:
        image = image.filter(ImageFilter.GaussianBlur((rng.uniform(1.6, 3) if training else 2.3) * scale))
    if flags[1]:
        image = ImageEnhance.Brightness(image).enhance(rng.uniform(.12, .3) if training else .20)
    if flags[2]:
        w, h = image.size
        fraction = rng.uniform(.18, .32) if training else .25
        image = image.crop((0, int(h * fraction), w, h))
    if flags[3]:
        angle = rng.uniform(15, 28) if training else 22
        image = image.rotate(angle, resample=Image.Resampling.BILINEAR, expand=True, fillcolor="white")
    return image


def rule(image):
    stream = BytesIO()
    image.save(stream, format="PNG")
    return rule_bytes(stream.getvalue())[0]


def rule_bytes(data):
    result = inspect_receipt_image(data)
    return ([int(any(word in reason for reason in result.reasons)) for word in ("흐", "어둡", "잘린")] + [0], list(result.reasons))


def decode_tensor(data):
    with Image.open(BytesIO(data)) as image:
        return tensor(ImageOps.exif_transpose(image).convert("RGB"))


class SmallCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(nn.Conv2d(3, 12, 5, stride=2, padding=2), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(12, 24, 3, stride=2, padding=1), nn.ReLU(), nn.Conv2d(24, 32, 3, stride=2, padding=1),
            nn.ReLU(), nn.AdaptiveAvgPool2d(1), nn.Flatten())
        self.head = nn.Linear(32, 4)

    def forward(self, x):
        return self.head(self.features(x))


def probabilities(model, x):
    model.eval()
    with torch.no_grad():
        return torch.cat([model(batch).sigmoid() for batch in x.split(16)]).numpy()


def train(model, x, y, validation_x, validation_y, epochs):
    optimizer = torch.optim.Adam(model.parameters(), lr=.002)
    criterion = nn.BCEWithLogitsLoss()
    best, state, trace = float("inf"), None, []
    for epoch in range(epochs):
        model.train()
        order = torch.randperm(len(x))
        for indices in order.split(16):
            optimizer.zero_grad()
            loss = criterion(model(x[indices]), y[indices])
            loss.backward(); optimizer.step()
        model.eval()
        with torch.no_grad():
            value = float(criterion(model(validation_x), validation_y))
        trace.append(value)
        if value < best:
            best, state = value, {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(state)
    return {"epochs": epochs, "validation_loss": trace, "selected_epoch": int(np.argmin(trace)) + 1}


def thresholds(y, probability):
    chosen = []
    for k in range(4):
        scores = []
        for threshold in np.arange(.1, .91, .05):
            p = probability[:, k] >= threshold
            tp = int(((y[:, k] == 1) & p).sum()); fp = int(((y[:, k] == 0) & p).sum()); fn = int(((y[:, k] == 1) & ~p).sum())
            scores.append((2 * tp / max(1, 2 * tp + fp + fn), float(threshold)))
        chosen.append(max(scores)[1])
    return chosen


def run(root, cache):
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    torch.set_num_threads(4); torch.use_deterministic_algorithms(True)
    os.environ["TORCH_HOME"] = str(cache)
    records = [json.loads(line) for line in (root / "test_dataset.jsonl").read_text(encoding="utf-8").splitlines()]
    images, manifest = {}, []
    parent = {row["id"]: row["id"] for row in records}
    def find(id_):
        while parent[id_] != id_:
            id_ = parent[id_]
        return id_
    hashes = {}
    for row in records:
        data = (root / row["image"]).read_bytes()
        sha, phash = image_fingerprints(data)
        if sha != row["sha256"]:
            raise ValueError(f"Original image changed: {row['id']}")
        hashes[row["id"]] = (sha, phash)
        with Image.open(BytesIO(data)) as image:
            images[row["id"]] = ImageOps.exif_transpose(image).convert("RGB").copy()
    pairs = []
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            ah, bh = hashes[a["id"]], hashes[b["id"]]
            signature_a = tuple(a["printed"].get(k) for k in ("business_number", "date", "receipt_total_amount"))
            signature_b = tuple(b["printed"].get(k) for k in ("business_number", "date", "receipt_total_amount"))
            if ah[0] == bh[0] or (int(ah[1], 16) ^ int(bh[1], 16)).bit_count() <= 6 or (all(v is not None for v in signature_a) and signature_a == signature_b):
                parent[find(b["id"])] = find(a["id"])
                pairs.append([a["id"], b["id"]])
    groups = {}
    for row in records:
        groups.setdefault(find(row["id"]), []).append(row["id"])
    ordered = sorted(groups.values(), key=lambda g: hashlib.sha256((str(SEED) + min(g)).encode()).hexdigest())
    splits = {"train": [], "validation": [], "test": []}
    targets = {"train": 18, "validation": 6, "test": 6}
    for group in sorted(ordered, key=lambda g: -len(g)):
        destination = max(splits, key=lambda key: targets[key] - len(splits[key]))
        splits[destination].extend(group)
    for row in records:
        manifest.append({"id": row["id"], "image": row["image"], "sha256": hashes[row["id"]][0],
            "group_id": find(row["id"]), "split": next(k for k, ids in splits.items() if row["id"] in ids),
            "real_labels": None, "real_label_status": "UNREVIEWED", "assistant_visual_note": "Contact sheet inspected; no independently reviewed defect labels."})
    visual_review = attach_visual_candidates(root, manifest)
    (root / "quality_experiment_manifest.json").write_text(json.dumps({"seed": SEED, "targets": targets,
        "actual_counts": {k: len(v) for k, v in splits.items()}, "grouped_pairs": pairs, "records": manifest,
        "visual_review": visual_review}, ensure_ascii=False, indent=2), encoding="utf-8")
    def dataset(ids, training=False, retain_views=False):
        xs, ys, views = [], [], []
        rng = random.Random(SEED + (1 if training else 2))
        for id_ in ids:
            # All 16 combinations; labels describe induced conditions, not verified real quality.
            for mask in range(16):
                flags = [(mask >> k) & 1 for k in range(4)]
                view = induce(images[id_], flags, rng, training)
                xs.append(tensor(view)); ys.append(flags)
                if retain_views:
                    views.append((id_, flags, view))
        return torch.stack(xs), torch.tensor(ys, dtype=torch.float32), views
    train_x, train_y, _ = dataset(splits["train"], True)
    validation_x, validation_y, _ = dataset(splits["validation"])
    test_x, test_y, test_views = dataset(splits["test"], retain_views=True)
    print(json.dumps({"phase": "data_ready", "splits": {k: len(v) for k, v in splits.items()}, "train_augmented": len(train_x)}), flush=True)
    cnn = SmallCNN()
    cnn_training = train(cnn, train_x, train_y, validation_x, validation_y, 20)
    print("scratch CNN trained", flush=True)
    weights = MobileNet_V3_Small_Weights.IMAGENET1K_V1
    backbone = mobilenet_v3_small(weights=weights).eval()
    backbone.classifier = nn.Identity()
    for parameter in backbone.parameters():
        parameter.requires_grad_(False)
    def features(x):
        with torch.no_grad():
            return torch.cat([backbone(batch) for batch in x.split(16)])
    train_features, validation_features = features(train_x), features(validation_x)
    head = nn.Linear(train_features.shape[1], 4)
    mobile_training = train(head, train_features, train_y, validation_features, validation_y, 100)
    class Mobile(nn.Module):
        def forward(self, x):
            return head(backbone(x))
    mobile = Mobile().eval()
    cache.mkdir(parents=True, exist_ok=True)
    checkpoint = cache / "quality-trained-models.pt"
    torch.save({"seed": SEED, "cnn": cnn.state_dict(), "mobile_head": head.state_dict()}, checkpoint)
    print("frozen MobileNet features and head trained", flush=True)
    result = {"seed": SEED, "runtime": {"torch": torch.__version__, "device": "cpu", "threads": 4},
        "splits": splits, "training": {"cnn": cnn_training, "mobilenet": mobile_training},
        "mobile_weights": str(weights), "preprocessing": "Full image letterbox 224; ImageNet normalization; no center crop.",
        "real_quality": {"reviewed_count": 0, "unreviewed_count": 30, "metrics": None,
            "visual_review": visual_review,
            "reason": "OCR correctness acceptance does not establish independent photo quality labels."},
        "trained_checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        "scope": "Induced-condition scores and unlabelled original-image predictions. Original negatives are assumed reference conditions, not verified normal photos.",
        "limitations": ["No verified real defect classes or real normal false rejection rate.", "Six original test receipts are too few for deployment conclusions.",
            "Synthetic conditions are not evidence of real capture performance.", "No OCR calls or preprocessing/OCR comparison."]}
    result["synthetic_reference"] = {}
    result["real_quality"]["original_predictions"] = []
    real_x = torch.stack([tensor(images[row["id"]]) for row in records])
    encoded_views = []
    for _, _, view in test_views:
        stream = BytesIO(); view.save(stream, format="PNG")
        encoded_views.append(stream.getvalue())
    for name, model in (("cnn", cnn), ("mobilenet", mobile)):
        threshold = thresholds(validation_y.numpy(), probabilities(model, validation_x))
        probability = probabilities(model, test_x)
        prediction = (probability >= threshold).astype(int)
        latency = []
        for sample in test_x[:12]:
            with torch.no_grad():
                model(sample[None])
        for sample in test_x:
            start = time.perf_counter()
            with torch.no_grad():
                model(sample[None])
            latency.append((time.perf_counter() - start) * 1000)
        result["synthetic_reference"][name] = {**metric(test_y.numpy(), prediction), "thresholds_from_validation": threshold,
            "inference_ms_median": float(np.median(latency)), "inference_ms_p95": float(np.percentile(latency, 95)),
            "latency_scope": "CPU model only, batch 1; excludes decode and letterbox", "predictions": prediction.tolist()}
        end_to_end = []
        for data in encoded_views:
            start = time.perf_counter()
            sample = decode_tensor(data)
            with torch.no_grad():
                model(sample[None]).sigmoid().numpy() >= threshold
            end_to_end.append((time.perf_counter() - start) * 1000)
        result["synthetic_reference"][name]["comparable_latency"] = {
            "median_ms": float(np.median(end_to_end)), "p95_ms": float(np.percentile(end_to_end, 95)),
            "scope": "Same PNG bytes in memory; decode + model-specific preprocessing + inference + threshold; excludes encode, disk and network", "n": len(end_to_end)}
        real_probability = probabilities(model, real_x)
        real_prediction = (real_probability >= threshold).astype(int)
        for index, row in enumerate(records):
            if len(result["real_quality"]["original_predictions"]) <= index:
                result["real_quality"]["original_predictions"].append({"id": row["id"], "split": next(k for k, ids in splits.items() if row["id"] in ids),
                    "labels": None, "label_status": "UNREVIEWED", "models": {},
                    "visual_candidate": manifest[index].get("visual_candidate")})
            result["real_quality"]["original_predictions"][index]["models"][name] = {
                "probabilities": real_probability[index].tolist(), "predictions": real_prediction[index].tolist()}
    rule_predictions, latency = [], []
    rule_rejected = []
    for data in encoded_views:
        start = time.perf_counter(); flags, reasons = rule_bytes(data); rule_predictions.append(flags)
        rule_rejected.append(bool(reasons)); latency.append((time.perf_counter() - start) * 1000)
    result["synthetic_reference"]["existing_rules"] = {**metric(test_y.numpy(), np.array(rule_predictions)),
        "inference_ms_median": float(np.median(latency)), "inference_ms_p95": float(np.percentile(latency, 95)),
        "latency_scope": "PNG decode + native-resolution quality inspection; excludes encode, disk and network", "predictions": rule_predictions,
        "comparable_latency": {"median_ms": float(np.median(latency)), "p95_ms": float(np.percentile(latency, 95)),
            "scope": "Same PNG bytes in memory; decode + native-resolution app rules; excludes encode, disk and network", "n": len(latency)}}
    normal = test_y.numpy().sum(axis=1) == 0
    result["synthetic_reference"]["existing_rules"]["normal_false_rejection_rate"] = float(np.array(rule_rejected)[normal].mean())
    for index, row in enumerate(records):
        flags, reasons = rule_bytes((root / row["image"]).read_bytes())
        result["real_quality"]["original_predictions"][index]["models"]["existing_rules"] = {"predictions": flags, "rejection_reasons": reasons}
    result["test_conditions"] = [{"id": id_, "induced_labels": flags} for id_, flags, _ in test_views]
    (root / "quality_model_comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report = ["# 로컬 품질분류 비교 실험", "", "실제 품질 정답 검토 0/30건. 실제 결함별 F1과 정상 오거절률은 산출하지 않았다.",
        "아래 수치는 고정 인위적 조건의 참고 성능이며 실제 촬영환경 성능이 아니다.", "",
        f"seed={SEED}; 원본별 분할: { {k: len(v) for k, v in splits.items()} }; 유사 원본과 모든 증강본을 같은 분할에 유지.",
        "CNN은 무작위 초기화로 학습. MobileNetV3-Small은 ImageNet 사전학습 특징을 고정하고 분류 헤드만 학습.",
        "학습 조건의 강도는 무작위, Validation/Test의 조건은 고정. Test로 임계값을 선택하지 않았다.", "",
        "| 모델 | 흐림 F1 | 저조도 F1 | 잘림 F1 | 기울기 F1 | 참고 무변형 오거절률 |", "|---|---:|---:|---:|---:|---:|"]
    for name, row in result["synthetic_reference"].items():
        report.append("| " + name + " | " + " | ".join(f"{row['fields'][label]['f1']:.3f}" for label in LABELS) + f" | {row['normal_false_rejection_rate']:.3f} |")
    report.extend(["", "같은 PNG 메모리 입력에 대해 디코딩부터 판단까지 측정했다. 인코딩·디스크·네트워크는 제외한다. 모델만의 시간은 별도 JSON 항목으로 유지한다.",
        "", "| 모델 | 동일 입력 전체 처리 중앙값 ms | p95 ms |", "|---|---:|---:|"])
    for name, row in result["synthetic_reference"].items():
        timing = row["comparable_latency"]
        report.append(f"| {name} | {timing['median_ms']:.2f} | {timing['p95_ms']:.2f} |")
    report.extend(["", "원본 30건의 모델별 예측·신뢰도·기존 규칙 거절 사유도 JSON에 기록했다. 정답 라벨이 없으므로 거절 비율을 실제 정상 오거절률로 부르지 않는다.",
        f"시각 검토 초안 {visual_review['candidate_count']}건을 사진 해시·분할과 대조해 보존했다. 초안은 학습·임계값·실제 성능 계산에 사용하지 않았다.",
        "", "실제 라벨이 부족하므로 앱 적용·모델 선택 근거로 사용할 수 없다. 학습 모델은 앱 처리 경로에 넣지 않았다.",
        "추가 OCR 호출 없이 전처리의 OCR 개선을 측정했다고 주장하지 않는다.",
        "", "사전학습 모델 출처: https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.mobilenet_v3_small.html"])
    (root / "quality_model_comparison.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"phase": "complete", "results": {k: {label: r["fields"][label]["f1"] for label in LABELS} for k, r in result["synthetic_reference"].items()}}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    run(args.root, args.cache)
