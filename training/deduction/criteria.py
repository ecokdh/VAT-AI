"""공제 판정 기준표. 합성 거래의 정답(verdict·category·근거 조문)과 템플릿 사유는 여기서만 정한다.

쟁점(Issue)마다 영수증 틀과 '사용자가 확인한 사실(Fact)'별 결론을 둔다.
같은 영수증에 사실만 바꾼 변형을 함께 만들어, 사실이 없으면 애매·있으면 확정이라는 기준을 학습시킨다.
애매의 경우별 결과(cases)는 같은 쟁점의 확정 사실들로 만든다.

사유 문장의 {items}·{industry}·{evidence}는 label_template.py가 거래 값으로 채운다.

범위: 일반과세자의 과세(부가세 있음) 매입만. 면세·유흥업소처럼 rule_check가 먼저 확정하는 거래와
판단이 갈리는 거래(사업주 본인 식대, 거래처와의 업무 협의 식사 등)는 넣지 않는다.
"""

from dataclasses import dataclass

# 근거 조문은 data/laws.json의 (법령명, 조문) 표기를 그대로 쓴다. 모두 rules.CORE_LAWS에 있어 프롬프트에 항상 들어간다.
VAT_38 = "부가가치세법 제38조 제1항"  # 공제하는 매입세액
VAT_39 = "부가가치세법 제39조 제1항"  # 공제하지 아니하는 매입세액
CARD_46 = "부가가치세법 제46조 제3항"  # 신용카드매출전표등 수취분 공제
DEC_77 = "부가가치세법 시행령 제77조"  # 사업과 직접 관련 없는 지출
DEC_79 = "부가가치세법 시행령 제79조"  # 기업업무추진비
DEC_88 = "부가가치세법 시행령 제88조 제5항"  # 카드 공제 제외 업종

# 업종(BusinessFacts 값)과 사유 문장에 쓸 이름. 앱의 industry_category / industry_subtype 코드와 같다.
INDUSTRIES = {
    "restaurant": ("food_service", "restaurant", "음식점업"),
    "cafe": ("food_service", "other", "카페"),
    "manufacturing": ("manufacturing", None, "제조업"),
    "retail": ("other", None, "소매업"),
}
ALL = tuple(INDUSTRIES)
FOOD = ("restaurant", "cafe")

CARD = ("card_receipt",)
CARD_CASH = ("card_receipt", "cash_receipt")
INVOICE = ("tax_invoice",)


@dataclass(frozen=True)
class Receipt:
    vendors: tuple[str, ...]  # 가상 상호
    items: tuple[tuple[str, int, int], ...]  # (품목, 최소 단가, 최대 단가) — 부가세 포함 금액
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class Fact:
    """사용자가 확인한 사실과 그때의 결론. purpose 문구는 앱 확인 질문의 답변 형식을 따른다."""

    purpose: str | None
    business_related: bool | None
    verdict: str  # deductible | non_deductible | ambiguous
    category: str
    laws: tuple[str, ...]
    reasons: tuple[str, ...]  # 사유 문장 틀(하나를 무작위로 고른다). 애매의 경우별 결과에는 "확인"이 없는 문장만 쓴다.
    condition: str | None = None  # 애매의 경우별 결과로 쓸 때의 조건 문구
    decision_point: str | None = None  # 애매일 때 쟁점 기본값 대신 쓸 확인 사실


@dataclass(frozen=True)
class Issue:
    id: str
    title: str
    industries: tuple[str, ...]
    receipt: Receipt
    facts: tuple[Fact, ...]
    decision_point: str | None = None  # 애매일 때 사용자가 답할 사실


def deductible(category, *reasons, laws=(VAT_38,), purpose=None, related=None, condition=None):
    return Fact(purpose, related, "deductible", category, laws, reasons, condition)


def non_deductible(category, laws, *reasons, purpose=None, related=None, condition=None):
    return Fact(purpose, related, "non_deductible", category, laws, reasons, condition)


def ambiguous(category, laws, *reasons, purpose=None, related=None, decision_point=None):
    return Fact(purpose, related, "ambiguous", category, laws, reasons, decision_point=decision_point)


# 앱 확인 질문(app/receipts/questions.py)의 답변 문구
BUSINESS_USE = "실제 업무·매장 운영에 사용"
PERSONAL_USE = "개인·가족 생활에 사용"
OPERATIONS = "업무·매장 운영에 사용할 물품"
PERSONAL_GOODS = "개인·가족이 사용할 물품"
STAFF_MEAL = "사업주·직원 식사·간식 / 직원"
CLIENT_MEAL = "거래처·고객에게 제공한 식사·음식 / 관계 유지·접대를 위한 식사"
FAMILY_MEAL = "개인·가족 식사"
VEHICLE_BUSINESS = "업무를 위한 이동·운행"
VEHICLE_PERSONAL = "개인·가족의 이동·운행"


def detail(text: str) -> str:
    return f"기타 — 직접 입력 / 직접 입력: {text}"


# 자주 쓰는 사유 문장
BUSINESS_SUPPLY = "사업을 위하여 공급받은 재화·용역의 매입세액이므로 공제 대상입니다."
PERSONAL = ("개인·가족 용도로 사용한 지출은 사업과 직접 관련이 없어 매입세액을 공제하지 않습니다.",
            "사업과 직접 관련 없는 개인적 지출로 확인되어 {items}의 매입세액은 공제되지 않습니다.")
CARD_EXCLUDED = ("{items}의 공급자는 신용카드매출전표등으로 매입세액을 공제받을 수 없는 업종(시행령 제88조 제5항)에 해당합니다. "
                 "사용 목적과 관계없이 카드 영수증의 부가가치세는 공제되지 않습니다.",)
PASSENGER_CAR = ("{industry} 사업에 쓰더라도 비영업용 소형승용차의 구입·임차·유지에 관한 매입세액은 공제하지 않습니다.",
                 "운수업 등 영업용이 아닌 승용자동차 관련 비용이라 업무에 사용했어도 {items}의 매입세액은 불공제입니다.")


ISSUES = (
    # ── 영수증만으로 공제가 분명한 매입 ──
    Issue("office_supplies", "사무용품 구입", ALL,
          Receipt(("바른문구", "오피스플러스", "한빛문구센터", "문구나라", "새봄오피스", "알파사무용품"),
                  (("A4 복사용지 500매", 5500, 29000), ("프린터 토너", 35000, 98000), ("볼펜 12입", 3000, 9000),
                   ("서류 파일", 2000, 8000), ("영수증 용지 롤", 9000, 30000), ("스테이플러", 4000, 12000),
                   ("라벨지", 6000, 18000), ("포스트잇", 2000, 7000)), CARD_CASH),
          (deductible("소모품비", "{items}은(는) {industry} 사업장의 사무용 소모품으로 사업 외 용도를 생각하기 어렵습니다. " + BUSINESS_SUPPLY,
                      "{industry} 업무에 쓰는 사무용품({items}) 구입으로, 부가가치세가 구분된 {evidence}를 받아 매입세액을 공제할 수 있습니다."),
           deductible("소모품비", "업무·매장 운영에 사용할 사무용품({items})으로 확인되었습니다. " + BUSINESS_SUPPLY,
                      purpose=OPERATIONS, related=True))),
    Issue("packaging", "포장용기·일회용품", FOOD,
          Receipt(("포장나라", "한국용기유통", "그린패키지", "다온포장", "에코팩상사"),
                  (("테이크아웃컵 1000개", 38000, 75000), ("빨대 500개", 6000, 15000), ("포장용기 300개", 30000, 90000),
                   ("비닐봉투 1000매", 15000, 32000), ("컵홀더 1000개", 18000, 40000), ("일회용 수저 1000세트", 15000, 35000)),
                  CARD + INVOICE),
          (deductible("소모품비", "{items}은(는) {industry} 판매에 쓰는 포장재·일회용품으로 사업용임이 분명합니다. " + BUSINESS_SUPPLY,
                      "{industry} 영업에 필요한 포장 소모품({items})을 {evidence}로 매입한 거래라 매입세액 공제 대상입니다."),)),
    Issue("cafe_ingredients", "카페 원재료", ("cafe",),
          Receipt(("로스터리하우스", "커피빈상사", "카페재료몰", "모닝로스터스", "빈스토리"),
                  (("원두 1kg(로스팅)", 22000, 45000), ("바닐라 시럽", 9000, 18000), ("휘핑크림", 6000, 12000),
                   ("초코 파우더", 12000, 25000), ("카라멜 소스", 8000, 16000), ("콜드브루 원액", 15000, 30000)), CARD + INVOICE),
          (deductible("원재료", "{items}은(는) 카페에서 음료를 만들어 파는 데 쓰는 원재료입니다. " + BUSINESS_SUPPLY,
                      "카페 판매 음료의 재료({items}) 매입으로, 부가가치세가 구분된 {evidence}를 받았으므로 공제할 수 있습니다."),)),
    Issue("restaurant_ingredients", "음식점 가공 식재료", ("restaurant",),
          Receipt(("식자재왕도매", "푸드마켓", "한마음식자재", "으뜸식자재", "새벽식자재"),
                  (("식용유 18L", 45000, 70000), ("업소용 간장 13L", 25000, 40000), ("냉동만두 5kg", 30000, 55000),
                   ("고추장 14kg", 50000, 80000), ("물엿 10kg", 18000, 30000), ("업소용 케첩 3.3kg", 9000, 15000)),
                  CARD + INVOICE),
          (deductible("원재료", "{items}은(는) 음식점에서 판매할 음식의 조리 재료(가공식품)로 사업용입니다. " + BUSINESS_SUPPLY,
                      "음식점 조리에 쓰는 과세 식재료({items})를 {evidence}로 매입했으므로 매입세액을 공제할 수 있습니다."),)),
    Issue("telecom", "사업장 통신 요금", ALL,
          Receipt(("한빛텔레콤", "누리통신", "스카이링크통신", "하나넷"),
                  (("사업장 인터넷 요금", 33000, 55000), ("매장 전화 요금", 15000, 35000), ("카드단말기 회선 요금", 11000, 22000)),
                  INVOICE),
          (deductible("통신비", "{industry} 사업장의 통신 요금({items})으로 세금계산서를 받은 사업용 지출입니다. " + BUSINESS_SUPPLY,
                      "사업장 회선 사용료({items})는 {industry} 운영에 필요한 용역이므로 매입세액 공제 대상입니다."),)),
    Issue("rent", "사업장 임차료", ALL,
          Receipt(("(주)대성빌딩", "새솔부동산임대", "중앙상가관리", "동명빌딩관리", "한빛타워관리"),
                  (("상가 월 임차료", 800000, 3300000), ("관리비", 110000, 440000)), INVOICE),
          (deductible("임차료", "{industry} 사업장의 임차료·관리비를 세금계산서로 받은 거래로, 사업용 건물의 임차 용역에 대한 매입세액이라 공제됩니다.",
                      "사업장으로 쓰는 상가의 {items}은(는) 사업을 위하여 공급받은 용역입니다. 세금계산서를 받았으므로 매입세액을 공제할 수 있습니다."),)),
    Issue("service_fee", "사업 관련 수수료", ALL,
          Receipt(("바른세무회계", "포스케어", "한결노무법인", "정직회계사무소", "스마트포스"),
                  (("기장 수수료", 110000, 330000), ("POS 유지보수", 22000, 66000), ("노무 자문료", 110000, 220000),
                   ("급여 대행 수수료", 55000, 110000)), INVOICE),
          (deductible("지급수수료", "{items}은(는) {industry} 사업 운영을 위한 전문 용역 대가입니다. " + BUSINESS_SUPPLY,
                      "사업 관련 수수료({items})를 세금계산서로 받았으므로 매입세액 공제 대상입니다."),)),
    Issue("advertising", "광고·홍보물 제작", ALL,
          Receipt(("인쇄골목", "애드온광고", "프린트하우스", "모아광고기획", "바른애드"),
                  (("전단지 3000매", 90000, 180000), ("현수막 제작", 50000, 120000), ("메뉴판 인쇄", 40000, 150000),
                   ("SNS 광고 대행", 110000, 330000)), CARD + INVOICE),
          (deductible("광고선전비", "{items}은(는) {industry} 영업 홍보를 위한 광고 지출로 사업용입니다. " + BUSINESS_SUPPLY,
                      "매장 홍보용 광고·인쇄물({items}) 비용으로, 부가가치세가 구분된 {evidence}를 받아 공제할 수 있습니다."),)),
    Issue("repair", "사업장 설비 수리", ALL,
          Receipt(("냉동공조서비스", "한빛설비", "바른인테리어", "한국공조", "우리설비"),
                  (("업소용 냉장고 수리", 80000, 350000), ("에어컨 점검", 55000, 150000), ("매장 조명 교체", 60000, 250000),
                   ("출입문 수리", 70000, 200000)), CARD + INVOICE),
          (deductible("기타", "{items}은(는) {industry} 사업장 설비의 수리·유지 비용으로 사업 외 용도를 생각하기 어렵습니다. " + BUSINESS_SUPPLY,
                      "사업장 시설 수선({items})은 사업을 위하여 공급받은 용역이며 {evidence}를 받았으므로 매입세액을 공제합니다."),)),

    # ── 사용 목적에 따라 결론이 갈리는 매입(목적이 없으면 애매) ──
    Issue("restaurant_meal", "식당 식사", ("manufacturing", "retail", "cafe"),
          Receipt(("한솥가마", "명가숯불", "소문난국밥", "청기와식당", "바다횟집", "옛날칼국수", "고향식당"),
                  (("김치찌개", 8000, 10000), ("삼겹살 1인분", 15000, 19000), ("국밥", 9000, 12000),
                   ("모둠회 중", 45000, 70000), ("공기밥", 1000, 2000), ("제육볶음", 9000, 12000)), CARD),
          (ambiguous("복리후생비", (VAT_38, VAT_39, DEC_77, DEC_79),
                     "식당 식사비는 직원 식사·회식인지, 거래처 접대인지, 개인 식사인지에 따라 공제 여부가 달라집니다.",
                     "{items} 결제는 영수증만으로 누구와 어떤 목적으로 식사했는지 알 수 없어 공제 여부를 확정할 수 없습니다."),
           deductible("복리후생비", "직원 식사로 확인되어 사업을 위한 복리후생 지출입니다. 부가가치세가 구분된 {evidence}를 받았으므로 공제할 수 있습니다.",
                      "직원 식대·회식은 사업과 관련된 지출이므로 {items}의 매입세액은 공제 대상입니다.",
                      purpose=STAFF_MEAL, related=True, condition="직원 식사·회식 등 복리후생 지출인 경우"),
           non_deductible("기업업무추진비", (VAT_39, DEC_79),
                          "거래처·고객 접대를 위한 식사비는 기업업무추진비에 해당하여 매입세액을 공제하지 않습니다.",
                          "관계 유지·접대 목적의 식사로 확인되어 기업업무추진비 관련 매입세액으로 불공제입니다.",
                          purpose=CLIENT_MEAL, related=True, condition="거래처·고객 접대를 위한 식사인 경우"),
           non_deductible("개인지출", (VAT_39, DEC_77), *PERSONAL,
                          purpose=FAMILY_MEAL, related=False, condition="개인·가족 식사인 경우")),
          decision_point="이 식사가 직원 식사·회식인지, 거래처 접대인지, 개인·가족 식사인지"),
    Issue("household_goods", "마트 생활용품", ("manufacturing", "retail"),
          Receipt(("행복마트", "우리동네마트", "알뜰할인마트", "다모아마트", "365마트"),
                  (("주방세제", 4000, 9000), ("두루마리 휴지 30롤", 15000, 25000), ("물티슈 10팩", 9000, 16000),
                   ("고무장갑", 2000, 4000), ("락스", 3000, 6000), ("청소용 솔", 3000, 7000), ("쓰레기봉투 50매", 5000, 12000)),
                  CARD_CASH),
          (ambiguous("소모품비", (VAT_38, VAT_39, DEC_77),
                     "{items}은(는) 사업장에서도 가정에서도 흔히 쓰는 생활용품이라 사용처에 따라 공제 여부가 달라집니다.",
                     "생활용품({items})은 영수증만으로 사업장용인지 개인용인지 알 수 없습니다."),
           deductible("소모품비", "사업장 운영에 사용할 물품으로 확인된 {items} 구입입니다. " + BUSINESS_SUPPLY,
                      "사업장 청소·위생 등 업무에 쓰는 소모품은 사업을 위하여 공급받은 재화라 매입세액을 공제합니다.",
                      purpose=OPERATIONS, related=True, condition="사업장 청소·위생 등 업무에 사용한 경우"),
           non_deductible("개인지출", (VAT_39, DEC_77), *PERSONAL,
                          purpose=PERSONAL_GOODS, related=False, condition="가정 등 개인 용도로 사용한 경우")),
          decision_point="이 생활용품을 사업장 운영에 사용했는지, 개인·가족 용도로 사용했는지"),
    Issue("electronics", "전자기기 구입", ALL,
          Receipt(("디지털플라자", "전자랜드마트", "하이테크몰", "테크월드", "미래전자"),
                  (("노트북", 900000, 1800000), ("태블릿", 500000, 1200000), ("모니터", 200000, 450000),
                   ("프린터", 150000, 400000)), CARD),
          (ambiguous("기타", (VAT_38, VAT_39, DEC_77),
                     "{items}은(는) 업무용으로도 개인용으로도 쓰일 수 있어 실제 사용 목적에 따라 공제 여부가 달라집니다.",
                     "전자기기 구입은 사업에 사용하는지 확인되어야 공제 여부를 정할 수 있습니다."),
           deductible("기타", "업무에 사용하는 전자기기({items})로 확인되었습니다. " + BUSINESS_SUPPLY,
                      "업무에 쓰는 전자기기는 사업을 위하여 공급받은 재화라 매입세액을 공제할 수 있습니다.",
                      purpose=BUSINESS_USE, related=True, condition="매장·업무용으로 사용하는 경우"),
           non_deductible("개인지출", (VAT_39, DEC_77), *PERSONAL,
                          purpose=PERSONAL_USE, related=False, condition="개인·가족이 사용하는 경우")),
          decision_point="이 기기를 업무에 사용하는지, 개인·가족이 사용하는지"),
    Issue("gift_set", "선물세트 구입", ALL,
          Receipt(("명품선물관", "한가위선물센터", "정성선물몰", "마음선물샵"),
                  (("한우 선물세트", 150000, 300000), ("과일청 선물세트", 30000, 60000), ("커피 선물세트", 25000, 55000),
                   ("견과류 선물세트", 30000, 70000)), CARD),
          (ambiguous("기업업무추진비", (VAT_38, VAT_39, DEC_77, DEC_79),
                     "선물 구입은 받는 사람이 직원인지, 거래처인지, 가족인지에 따라 공제 여부가 달라집니다.",
                     "{items}은(는) 영수증만으로 누구에게 준 선물인지 알 수 없어 공제 여부를 확정할 수 없습니다."),
           deductible("복리후생비", "직원에게 준 선물로 확인되어 사업 관련 복리후생 지출입니다. " + BUSINESS_SUPPLY,
                      "직원에게 주는 선물은 사업 관련 복리후생 지출이라 매입세액을 공제할 수 있습니다.",
                      purpose=detail("직원 명절 선물"), related=True, condition="직원에게 준 선물인 경우"),
           non_deductible("기업업무추진비", (VAT_39, DEC_79),
                          "거래처에 준 선물은 기업업무추진비에 해당하여 관련 매입세액을 공제하지 않습니다.",
                          "거래처 명절 선물로 확인되어 기업업무추진비 관련 매입세액으로 불공제입니다.",
                          purpose=detail("거래처 명절 선물"), related=True, condition="거래처에 준 선물인 경우"),
           non_deductible("개인지출", (VAT_39, DEC_77), *PERSONAL,
                          purpose=PERSONAL_GOODS, related=False, condition="개인·가족 선물인 경우")),
          decision_point="이 선물을 직원에게 주었는지, 거래처에 주었는지, 개인적으로 사용했는지"),
    Issue("fuel", "주유", ALL,
          Receipt(("푸른주유소", "한길셀프주유소", "고속도로주유소", "새솔주유소", "중앙셀프주유소"),
                  (("휘발유", 40000, 120000), ("경유", 50000, 150000)), CARD),
          # 업무 운행이어도 비영업용 승용차면 불공제라, 차종을 모르면 목적만으로는 확정할 수 없다.
          (ambiguous("차량유지비", (VAT_38, VAT_39, DEC_77),
                     "주유비는 화물차 등 업무용 차량에 썼는지, 비영업용 승용차나 개인 운행에 썼는지에 따라 공제 여부가 달라집니다.",
                     "{items} 주유는 영수증만으로 어떤 차량에 어떤 목적으로 썼는지 알 수 없습니다."),
           ambiguous("차량유지비", (VAT_38, VAT_39),
                     "업무 운행이라도 비영업용 소형승용차라면 유지비 매입세액이 불공제라, 차종에 따라 결론이 달라집니다.",
                     "업무용 운행은 확인되었지만 차량이 화물차인지 승용차인지에 따라 공제 여부가 갈립니다.",
                     purpose=VEHICLE_BUSINESS, related=True,
                     decision_point="업무 운행에 사용한 차량이 화물차 등 승용차가 아닌 차량인지, 비영업용 승용차인지"),
           deductible("차량유지비", "배송용 화물차 주유로 확인되었습니다. 화물차는 불공제 대상인 비영업용 승용자동차가 아니어서 매입세액을 공제할 수 있습니다.",
                      "화물차 등 승용차가 아닌 업무용 차량의 유지비는 사업을 위한 지출이라 매입세액을 공제할 수 있습니다.",
                      purpose=detail("배송용 1톤 화물차 주유"), related=True, condition="화물차 등 승용차가 아닌 업무용 차량에 주유한 경우"),
           non_deductible("차량유지비", (VAT_39,), *PASSENGER_CAR,
                          purpose=detail("사업주 2000cc 승용차 업무 운행"), related=True, condition="비영업용 승용차에 주유한 경우"),
           non_deductible("개인지출", (VAT_39, DEC_77), *PERSONAL,
                          purpose=VEHICLE_PERSONAL, related=False, condition="개인·가족 운행에 주유한 경우")),
          decision_point="이 주유를 어떤 차량(화물차·승용차 등)에, 업무와 개인 중 어떤 운행에 사용했는지"),

    # ── 사업 관련이어도 불공제인 매입(목적과 무관하게 확정) ──
    Issue("passenger_transport", "택시·고속버스·항공 등 여객운송(카드)", ALL,
          Receipt(("한빛택시", "고속버스터미널", "에어코리아항공", "고속철도역", "모범택시", "중부고속", "푸른하늘항공"),
                  (("택시 요금", 8000, 35000), ("고속버스 승차권", 15000, 40000), ("항공권", 60000, 250000),
                   ("고속철도 승차권", 25000, 60000)), CARD),
          (non_deductible("기타", (CARD_46, DEC_88), *CARD_EXCLUDED),
           non_deductible("기타", (CARD_46, DEC_88),
                          "출장 등 사업 목적이어도 여객운송업자가 발급한 카드 영수증의 부가가치세는 공제 대상이 아닙니다(시행령 제88조 제5항).",
                          purpose=detail("거래처 방문 출장"), related=True))),
    Issue("admission_ticket", "영화관·공연장 입장권(카드)", ALL,
          Receipt(("시네마월드", "별빛극장", "아트홀공연장", "드림시네마"),
                  (("영화 관람권", 12000, 15000), ("공연 입장권", 50000, 120000)), CARD),
          (non_deductible("복리후생비", (CARD_46, DEC_88), *CARD_EXCLUDED),
           non_deductible("복리후생비", (CARD_46, DEC_88),
                          "직원 복리후생 목적이어도 입장권을 발행하는 사업자의 카드 영수증은 매입세액 공제 대상이 아닙니다(시행령 제88조 제5항).",
                          purpose=detail("직원 단체 관람"), related=True))),
    Issue("hair_salon", "미용실(카드)", ALL,
          Receipt(("헤어살롱 봄", "블루헤어", "마이뷰티헤어", "헤어온"),
                  (("커트", 15000, 30000), ("펌", 60000, 150000)), CARD),
          (non_deductible("개인지출", (CARD_46, DEC_88), *CARD_EXCLUDED),)),
    Issue("passenger_car_repair", "승용차 정비", ALL,
          Receipt(("스피드카정비", "한국오토서비스", "바른자동차공업사", "카닥터정비"),
                  (("엔진오일 교환", 60000, 120000), ("타이어 교체", 300000, 700000), ("와이퍼 교체", 20000, 50000)),
                  CARD + INVOICE),
          (ambiguous("차량유지비", (VAT_38, VAT_39),
                     "차량 정비비는 정비한 차량이 화물차 등 업무용인지 비영업용 승용차인지에 따라 공제 여부가 달라집니다.",
                     "{items}은(는) 영수증만으로 어떤 차량을 정비했는지 알 수 없어 공제 여부를 확정할 수 없습니다."),
           non_deductible("차량유지비", (VAT_39,), *PASSENGER_CAR,
                          purpose=detail("사업주 2000cc 승용차 업무용"), related=True, condition="비영업용 승용차를 정비한 경우"),
           deductible("차량유지비", "배송용 화물차 정비로 확인되었습니다. 화물차는 불공제 대상인 비영업용 승용자동차가 아니어서 매입세액을 공제할 수 있습니다.",
                      "화물차 등 승용차가 아닌 업무용 차량의 정비비는 사업을 위한 지출이라 매입세액을 공제할 수 있습니다.",
                      purpose=detail("배송용 1톤 화물차 정비"), related=True, condition="화물차 등 승용차가 아닌 업무용 차량을 정비한 경우")),
          decision_point="정비한 차량이 화물차 등 업무용 차량인지, 비영업용 승용차인지"),
)
