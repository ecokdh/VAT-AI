"""영수증 사진 품질. 학습 모델 없이 밝기·흐림·잘림만 본다."""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageFilter, ImageOps, ImageStat


@dataclass(frozen=True)
class QualityResult:
    ok: bool
    reasons: tuple[str, ...]


def inspect_receipt_image(file_bytes: bytes) -> QualityResult:
    with Image.open(BytesIO(file_bytes)) as image:
        image.load()
        rgb = image.convert("RGB")
        width, height = rgb.size
        gray = ImageOps.grayscale(rgb)

    reasons: list[str] = []
    if width < 80 or height < 80:
        reasons.append("사진이 너무 작습니다. 다시 찍어 주세요.")

    mean = ImageStat.Stat(gray).mean[0]
    if mean < 45:
        reasons.append("사진이 너무 어둡습니다. 다시 찍어 주세요.")
    if mean > 245:
        reasons.append("사진이 너무 하얗게 나왔습니다. 다시 찍어 주세요.")

    edge_mean = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0]
    if edge_mean < 4:
        reasons.append("사진이 흔들렸거나 흐립니다. 다시 찍어 주세요.")

    if width > height * 4 or height > width * 4:
        reasons.append("영수증이 잘린 것 같습니다. 다시 찍어 주세요.")
    elif _content_touches_all_edges(gray):
        reasons.append("영수증이 잘린 것 같습니다. 다시 찍어 주세요.")

    return QualityResult(ok=not reasons, reasons=tuple(reasons))


def _content_touches_all_edges(gray: Image.Image) -> bool:
    width, height = gray.size
    if width < 16 or height < 16:
        return False
    strip = 4

    def dark_ratio(box: tuple[int, int, int, int]) -> float:
        region = gray.crop(box)
        if hasattr(region, "get_flattened_data"):
            pixels = list(region.get_flattened_data())
        else:
            pixels = list(region.getdata())
        if not pixels:
            return 0.0
        return sum(1 for value in pixels if value < 180) / len(pixels)

    edges = (
        dark_ratio((0, 0, width, strip)),
        dark_ratio((0, height - strip, width, height)),
        dark_ratio((0, 0, strip, height)),
        dark_ratio((width - strip, 0, width, height)),
    )
    return all(ratio > 0.4 for ratio in edges)
