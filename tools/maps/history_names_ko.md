# 과거 국가 이름 한국어 표기 기준

목적: 시험지 지도 편집 화면에서 교사가 고르는 나라 이름. 현대 한국 고등학교 교과서(2022 개정 세계사·동아시아사·한국사, 2015 개정 세계사·동아시아사) 표현을 따른다.

## 우선순위
1. **교과서에 나오는 이름**이면 교과서 표기 그대로. (예: Achaemenid Empire → 아케메네스 왕조 페르시아, Seljuk Empire → 셀주크 튀르크, Umayyad Caliphate → 우마이야 왕조, Fatimid Caliphate → 파티마 왕조, Ghaznavid → 가즈니 왕조, Maurya Empire → 마우리아 왕조, Gupta Empire → 굽타 왕조, Delhi Sultanate → 델리 술탄 왕조, Holy Roman Empire → 신성 로마 제국, Kingdom of Prussia → 프로이센 왕국, Aztec Empire / Triple Alliance → 아스테카 제국, Inca Empire → 잉카 제국, Mali Empire → 말리 왕국, Songhai Empire → 송가이 왕국, Kingdom of Kush → 쿠시 왕국, Ilkhanate → 일 칸국, Golden Horde → 킵차크 칸국, Chagatai Khanate → 차가타이 칸국, Safavid → 사파비 왕조, Timurid → 티무르 왕조, Khmer Empire → 앙코르 왕조(크메르), Srivijaya → 스리위자야, Champa → 참파, Đại Việt → 대월(다이비엣), Tibetan Empire → 토번, Uyghur Khaganate → 위구르, Göktürk → 돌궐, Khitan Liao → 요, Jurchen Jin → 금, Western Xia → 서하, Nanzhao → 남조, Dali → 대리, Goguryeo → 고구려, Baekje → 백제, Silla → 신라, Balhae → 발해, Goryeo → 고려, Yamato → 야마토 정권, Kamakura shogunate → 가마쿠라 막부, Tokugawa shogunate → 에도 막부)
2. 중국 왕조는 교과서처럼 한 글자로 쓰고, 같은 소리가 겹치면 한자를 괄호로 단다: 진(秦), 진(晉), 한, 수, 당, 송, 원, 명, 청, 북위, 동진, 서진, 전진, 후한 등.
3. 교과서에 없는 나라는 **국립국어원 외래어 표기법**으로 옮기고 정치체 종류를 한국어로 붙인다: Kingdom → 왕국, Empire → 제국, Sultanate → 술탄국, Khanate → 칸국, Caliphate → 칼리프국(교과서 왕조명이 있으면 "~ 왕조"), Emirate → 토후국, Republic → 공화국, Duchy → 공국, Grand Duchy → 대공국, Principality → 공국, County → 백국, Confederation → 연합/동맹, Chiefdom → 족장 사회, Culture → 문화, Colony → 식민지, Protectorate → 보호령, Dynasty → 왕조.
4. 현대 나라는 외교부 공식 한국어 국명: Republic of Korea → 대한민국, Viet Nam → 베트남 등.
5. 사람 이름·지명은 교과서 표기 우선(예: Charlemagne 아닌 국명이면 해당 없음, Ottoman → 오스만, Mughal → 무굴, Rus' → 루스, Kievan Rus' → 키예프 공국, Muscovy → 모스크바 대공국, Byzantine/Eastern Roman → 비잔티움 제국).
6. 같은 한국어 이름이 서로 다른 두 나라에 붙으면 안 된다. 겹치면 시기·지역을 괄호로 붙여 구별한다. 예: 진(秦)/진(晉), 송(남조)/송.
7. 괄호 없이 간결하게. 이름 뒤에 설명을 달지 않는다(구별용 괄호만 예외).
8. 이미 있는 한국어 이름(ko)이 교과서 표기와 다르거나 위키백과식 긴 제목·잘못된 이름이면 고친다. 맞으면 그대로 둔다.

## 이름표 파일
`history_names_ko.json`: `{"영어 이름": ["한국어 이름", "t" 또는 "x"]}`. Cliopatria의 나라 1,587개를 모두 담는다.
- `t`: 교과서에 나오는 이름. `x`: 교과서에 없어 외래어 표기법으로 옮긴 이름.
- 영어 이름이 `(`로 시작하는 묶음 영역은 속한 이름만 적는다. `build_past_map_data.py`가 "… 전체"를 붙인다.
- 고친 뒤 `python -I tools/maps/build_past_map_data.py`로 `app/map_data/history.json.gz`를 다시 만든다(내려받기 없음).
