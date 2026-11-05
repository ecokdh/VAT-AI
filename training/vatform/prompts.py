"""학습·평가가 같은 지시문과 메시지 형식을 쓰도록 한곳에 둔다."""

READ_PROMPT = (
    "이 이미지는 부가가치세 신고서(별지 제21호서식) 1쪽입니다. "
    "기재된 값을 {\"필드ID\": \"값\"} 형식의 JSON으로만 답하세요. 비어 있는 칸은 넣지 마세요."
)
LOCATE_PROMPT = (
    "부가가치세 신고서(별지 제21호서식) 1쪽에서 '{label}' 칸의 위치를 찾아 "
    "{{\"bbox_2d\": [x1, y1, x2, y2], \"label\": \"필드ID\"}} JSON으로만 답하세요. "
    "좌표는 이미지 기준 0~1000 상대 좌표입니다."
)


def user_message(prompt: str) -> dict:
    """이미지 1장 + 지시문. 이미지 자체는 processor에 따로 넘긴다."""
    return {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]}


def assistant_message(answer: str) -> dict:
    return {"role": "assistant", "content": [{"type": "text", "text": answer}]}
