"""평가 전용 골드셋. 학습 데이터에 섞지 않는다.

기준표(criteria.py)와 상호·품목·문구를 다르게 쓰고, 기준표에 없는 경계 사례(경차·승합차·전세버스·출장 숙박 등)를 더했다.
정답은 data/laws.json 조문을 근거로 적었으며, 사용자 검수(reviewed) 전까지는 초안이다.
"""

from criteria import (
    CARD_46, CLIENT_MEAL, DEC_77, DEC_79, DEC_88, FAMILY_MEAL, OPERATIONS, PERSONAL_GOODS, PERSONAL_USE,
    STAFF_MEAL, VAT_38, VAT_39, VEHICLE_BUSINESS, VEHICLE_PERSONAL, detail,
)

D, N, A = "deductible", "non_deductible", "ambiguous"

# (id, 업종, 상호, [(품목, 부가세 포함 금액)], 증빙, 사용 목적, 사업 관련 여부, 정답, 분류, 근거 조문, 메모)
GOLD = (
    # 영수증만으로 공제가 분명함
    ("g01", "retail", "새길사무기기", [("라벨 프린터 테이프", 23000)], "card_receipt", None, None, D, "소모품비", (VAT_38,), ""),
    ("g02", "cafe", "한결커피유통", [("에스프레소 블렌드 원두 2kg", 68000)], "tax_invoice", None, None, D, "원재료", (VAT_38,), ""),
    ("g03", "restaurant", "대한식품도매", [("업소용 마요네즈 3.2kg", 14500), ("돈가스 소스 2kg", 9800)], "card_receipt", None, None, D, "원재료", (VAT_38,), ""),
    ("g04", "manufacturing", "동양철강상사", [("스테인리스 판재", 1320000)], "tax_invoice", None, None, D, "원재료", (VAT_38,), "제조업 원자재"),
    ("g05", "retail", "온누리통신", [("매장 와이파이 요금", 27500)], "tax_invoice", None, None, D, "통신비", (VAT_38,), ""),
    ("g06", "cafe", "푸른상가관리단", [("점포 임대료", 1650000)], "tax_invoice", None, None, D, "임차료", (VAT_38,), ""),
    ("g07", "restaurant", "배달플랫폼광고(주)", [("앱 상단 노출 광고", 220000)], "tax_invoice", None, None, D, "광고선전비", (VAT_38,), ""),
    ("g08", "manufacturing", "정밀기계서비스", [("CNC 기계 수리", 770000)], "tax_invoice", None, None, D, "기타", (VAT_38,), ""),
    ("g09", "cafe", "그린팩토리", [("종이 캐리어 500개", 41000)], "card_receipt", None, None, D, "소모품비", (VAT_38,), ""),
    ("g10", "retail", "세움세무사무소", [("부가세 신고 대행 수수료", 165000)], "tax_invoice", None, None, D, "지급수수료", (VAT_38,), ""),

    # 사용 목적이 없어 결론이 갈림(애매)
    ("g11", "manufacturing", "장터순대국", [("순대국", 9000), ("순대국", 9000), ("수육 소", 22000)], "card_receipt", None, None, A, "복리후생비", (VAT_38, VAT_39, DEC_79), "직원 식사·접대·개인 식사로 갈림"),
    ("g12", "retail", "본가갈비", [("돼지갈비 4인분", 64000), ("냉면", 9000)], "card_receipt", None, None, A, "복리후생비", (VAT_38, VAT_39, DEC_79), ""),
    ("g13", "cafe", "하나로생활마트", [("키친타월", 7900), ("섬유유연제", 12900)], "card_receipt", None, None, A, "소모품비", (VAT_38, VAT_39, DEC_77), ""),
    ("g14", "restaurant", "컴퓨존", [("데스크톱 PC", 1150000)], "card_receipt", None, None, A, "기타", (VAT_38, VAT_39, DEC_77), ""),
    ("g15", "retail", "에너지주유소", [("휘발유 45.2L", 78000)], "card_receipt", None, None, A, "차량유지비", (VAT_38, VAT_39), "차종·용도 모름"),
    ("g16", "manufacturing", "참좋은선물", [("홍삼 선물세트", 98000)], "card_receipt", None, None, A, "기업업무추진비", (VAT_38, VAT_39, DEC_79), ""),
    ("g17", "retail", "대로주유소", [("경유 60L", 96000)], "card_receipt", VEHICLE_BUSINESS, True, A, "차량유지비", (VAT_38, VAT_39), "업무 운행이지만 차종 모름"),
    ("g18", "manufacturing", "명품카센터", [("브레이크 패드 교체", 180000)], "card_receipt", None, None, A, "차량유지비", (VAT_38, VAT_39), ""),

    # 사용 목적이 확인돼 결론이 확정됨
    ("g19", "manufacturing", "장터순대국", [("순대국", 9000), ("순대국", 9000), ("수육 소", 22000)], "card_receipt", STAFF_MEAL, True, D, "복리후생비", (VAT_38,), "g11의 목적 확인 변형"),
    ("g20", "retail", "본가갈비", [("돼지갈비 4인분", 64000), ("냉면", 9000)], "card_receipt", CLIENT_MEAL, True, N, "기업업무추진비", (VAT_39, DEC_79), "g12의 목적 확인 변형"),
    ("g21", "retail", "본가갈비", [("돼지갈비 4인분", 64000), ("냉면", 9000)], "card_receipt", FAMILY_MEAL, False, N, "개인지출", (VAT_39, DEC_77), ""),
    ("g22", "cafe", "하나로생활마트", [("키친타월", 7900), ("섬유유연제", 12900)], "card_receipt", OPERATIONS, True, D, "소모품비", (VAT_38,), ""),
    ("g23", "cafe", "하나로생활마트", [("키친타월", 7900), ("섬유유연제", 12900)], "card_receipt", PERSONAL_GOODS, False, N, "개인지출", (VAT_39, DEC_77), ""),
    ("g24", "restaurant", "컴퓨존", [("데스크톱 PC", 1150000)], "card_receipt", detail("매장 주문·재고 관리용"), True, D, "기타", (VAT_38,), ""),
    ("g25", "restaurant", "컴퓨존", [("데스크톱 PC", 1150000)], "card_receipt", PERSONAL_USE, False, N, "개인지출", (VAT_39, DEC_77), ""),
    ("g26", "manufacturing", "참좋은선물", [("홍삼 선물세트", 98000)], "card_receipt", detail("거래처 대표 감사 선물"), True, N, "기업업무추진비", (VAT_39, DEC_79), ""),
    ("g27", "retail", "대로주유소", [("경유 60L", 96000)], "card_receipt", detail("상품 배송용 1톤 트럭"), True, D, "차량유지비", (VAT_38,), ""),
    ("g28", "retail", "에너지주유소", [("휘발유 45.2L", 78000)], "card_receipt", detail("대표 개인 승용차(2500cc) 거래처 방문"), True, N, "차량유지비", (VAT_39,), "업무용이어도 비영업용 승용차"),
    ("g29", "retail", "에너지주유소", [("휘발유 45.2L", 78000)], "card_receipt", VEHICLE_PERSONAL, False, N, "개인지출", (VAT_39, DEC_77), ""),
    ("g30", "cafe", "달빛베이커리", [("생일 케이크", 32000)], "card_receipt", detail("직원 생일 축하"), True, D, "복리후생비", (VAT_38,), ""),
    ("g31", "manufacturing", "든든한도시락", [("도시락", 7500), ("도시락", 7500), ("도시락", 7500)], "card_receipt", detail("직원 야근 식사"), True, D, "복리후생비", (VAT_38,), ""),
    ("g32", "retail", "스마일전자", [("휴대폰 액세서리", 25000)], "card_receipt", PERSONAL_USE, False, N, "개인지출", (VAT_39, DEC_77), ""),

    # 사업 관련이어도 카드 공제가 안 되는 업종
    ("g33", "manufacturing", "서울개인택시", [("택시 운임", 18600)], "card_receipt", detail("거래처 미팅 이동"), True, N, "기타", (CARD_46, DEC_88), "여객운송업"),
    ("g34", "retail", "하늘항공", [("김포-제주 항공권", 89000)], "card_receipt", detail("박람회 참가 출장"), True, N, "기타", (CARD_46, DEC_88), ""),
    ("g35", "cafe", "동부고속", [("우등고속 승차권", 34000)], "card_receipt", None, None, N, "기타", (CARD_46, DEC_88), "목적과 무관"),
    ("g36", "restaurant", "메가시네마", [("영화 관람권 6매", 84000)], "card_receipt", detail("직원 회식 후 단체 관람"), True, N, "복리후생비", (CARD_46, DEC_88), "입장권 발행 사업"),
    ("g37", "retail", "라온헤어", [("남성 커트", 18000)], "card_receipt", None, None, N, "개인지출", (CARD_46, DEC_88), ""),
    ("g38", "manufacturing", "고속열차예매", [("고속철도 서울-부산", 59800)], "card_receipt", detail("공장 출장"), True, N, "기타", (CARD_46, DEC_88), ""),

    # 경계 사례(기준표에 없음)
    ("g39", "retail", "행운주유소", [("휘발유 30L", 51000)], "card_receipt", detail("업무용 경차(1000cc 이하) 주유"), True, D, "차량유지비", (VAT_38, VAT_39), "경차는 개별소비세 과세 자동차가 아님"),
    ("g40", "manufacturing", "행운주유소", [("경유 55L", 88000)], "card_receipt", detail("직원 출퇴근용 12인승 승합차"), True, D, "차량유지비", (VAT_38, VAT_39), "9인승 이상 승합차"),
    ("g41", "manufacturing", "푸른관광전세버스", [("워크숍 전세버스 대절", 660000)], "card_receipt", detail("직원 워크숍 이동"), True, D, "복리후생비", (VAT_38, DEC_88), "전세버스는 카드 공제 제외 업종에서 빠짐"),
    ("g42", "retail", "시티비즈호텔", [("숙박 1박", 99000)], "card_receipt", detail("지방 거래처 출장 숙박"), True, D, "기타", (VAT_38, CARD_46), "숙박업은 카드 공제 제외 업종 아님"),
    ("g43", "cafe", "제일리스", [("업무용 승용차 렌트(2000cc) 월 대여료", 550000)], "tax_invoice", detail("매장 업무용"), True, N, "차량유지비", (VAT_39,), "임차도 불공제"),
    ("g44", "restaurant", "한우명가", [("한우 등심 4인분", 240000)], "card_receipt", detail("거래처 사장님 접대"), True, N, "기업업무추진비", (VAT_39, DEC_79), ""),
    ("g45", "retail", "가나안경", [("안경 맞춤", 150000)], "card_receipt", PERSONAL_USE, False, N, "개인지출", (VAT_39, DEC_77), ""),
    ("g46", "manufacturing", "안전용품마트", [("안전화", 45000), ("작업장갑 10켤레", 15000)], "card_receipt", detail("생산직 직원 작업용"), True, D, "소모품비", (VAT_38,), ""),
    ("g47", "cafe", "우리세탁", [("앞치마 세탁", 12000)], "card_receipt", OPERATIONS, True, D, "소모품비", (VAT_38,), ""),
    ("g48", "restaurant", "바른주방설비", [("업소용 식기세척기", 2750000)], "tax_invoice", None, None, D, "기타", (VAT_38,), "음식점 설비라 사업 관련이 분명"),
    ("g49", "retail", "한마음꽃집상가", [("포장 리본", 5500)], "card_receipt", None, None, D, "소모품비", (VAT_38,), "소매업 포장재"),
    ("g50", "manufacturing", "다온카페", [("아메리카노", 4500), ("카페라떼", 5000)], "card_receipt", None, None, A, "복리후생비", (VAT_38, VAT_39, DEC_79), "직원 간식·접대·개인으로 갈림"),
)
