# PII 목록: en_US (미국)

이 문서는 `tinicore/src/guardrails/config/pii_filter_config.yaml` 에 미국(en_US) 고유 PII recognizer 가 포함되어야 하는 근거를 기록한다. 이미 YAML 에 있는 항목도 근거를 남기기 위해 포함하며, 국가에 종속되지 않는 항목(카드번호, API 키, 비밀번호, 이메일, IP 주소 등)은 다루지 않는다.

## 0. 문서 작성 기준

각 항목은 다음 네 가지 기준으로 평가한다.

1. 적용 법령 또는 감독기관 규제상 노출되면 안 되는 PII 인가?
2. 그 PII 가 무엇이며, 노출을 막아야 하는 근거는 무엇인가?
3. 결정론적 방법(regex 또는 손으로 작성한 패턴 매칭)으로 검출할 수 있는가?
4. 검증기(체크섬 등)가 있어서 매칭 정확도를 높일 수 있는가? 검증기가 없어도 보안상 중요하면 채택한다.

### 검출 방식 세 가지 (결정론적 검출 가능성 항목에서 사용하는 용어)

엔진(`recognizer.rs` 의 `PiiEngine`)은 세 가지 매칭 방식을 지원하며, 어느 방식으로 찾은 매치든 같은 후처리 파이프라인(boundary check → validator → dedup → context_words 점수)을 거친다. 따라서 검증기와 context_words 는 방식과 무관하게 동일하게 적용된다.

| 방식 | 구현 위치 | 동작 | 적합한 경우 | 비용 |
|---|---|---|---|---|
| **regex** | `PatternRecognizer`, `PatternTemplateRecognizer` | 모든 패턴을 `regex_automata::hybrid::dfa`(lazy DFA)로 컴파일해 한 번에 스캔 | 패턴 수가 적고 구조가 단순할 때. 기본 선택지 | 패턴 수와 복잡도에 비례해 DFA 캐시 메모리가 커진다. 카드번호는 105개 패턴이 문제가 되어 handwritten 으로 옮겼다 |
| **byte-scan handwritten** | `handwritten/card_detector.rs` 방식 (`MatchEngine` 직접 구현) | 텍스트를 바이트 단위로 걸으며 숫자열·영숫자열을 뽑고, 접두 표·길이·자리 규칙을 코드로 검사 | 접두가 고정 문자열이 아니라 **표**(BIN 처럼 여러 접두 구간)이거나, 주별 형식처럼 패턴 수가 많거나, 체크섬을 매칭 단계에서 바로 적용하고 싶을 때 | 메모리 거의 없음. 타입마다 detector 코드를 작성해야 한다 |
| **Aho-Corasick handwritten** | `handwritten/aho_corasick_detector.rs` (`pattern_desc_for` 에 anchor + verifier 등록) | 고정 문자열 anchor 를 하나의 automaton 으로 찾고, anchor 뒤(또는 앞)의 바이트를 verifier 함수가 검사 | **고정 리터럴 접두**가 있고 그 뒤에 단순한 문자 집합 run 이 이어질 때 (`AKIA`, `ghp_`, `010` 등). 여러 타입을 한 automaton 에 묶어 텍스트를 한 번만 스캔한다 | 메모리 거의 없음. anchor 가 짧으면(1-2바이트) 텍스트 곳곳에서 verifier 가 호출되어 이득이 줄고, anchor 는 대소문자를 구분한다(`ascii_case_insensitive` 미사용) |

각 항목의 "결정론적 검출 가능성"에서는 regex 를 기본으로 기술하고, 그 아래에 handwritten(byte-scan, Aho-Corasick) 대안의 실현 가능성과 **오탐률이 regex 대비 어떻게 달라지는지**를 함께 적는다. 오탐률은 매칭 형식이 같으면 방식과 무관하게 같고, handwritten 이 매칭 단계에서 표 대조나 체크섬을 추가로 수행할 때만 낮아진다.

### 엔진 제약 (regex 작성 시 유의)

- lazy DFA 이므로 **lookahead·lookbehind·역참조를 쓸 수 없다.** 배제 규칙(예: SSN 의 `000`, `666`, `9xx` 지역번호 제외)은 regex 가 아니라 `validator.rs` 의 검증 함수로 구현하거나, handwritten detector 안에서 코드로 처리한다.
- 현재 `validator.rs` 에 존재하는 검증기는 `luhn`, `rrn`, `phonenumber` 세 가지뿐이다. `rrn` 은 자릿수만 확인하고 `phonenumber` 는 항상 `true` 를 돌려준다. 아래 "검증기" 필드에서 "현재"는 이 세 가지 기준이고, "구현 가능"은 새로 작성해야 하는 검증 논리를 뜻한다.
- 단어 경계 처리는 `boundary_check` 와 `boundary_check_reject_before/after` 설정으로 한다. handwritten detector 도 같은 설정을 따른다.

## 1. 적용 법령 및 감독기관

미국은 단일한 포괄적 연방 개인정보보호법이 없고, 분야별 연방법과 주법이 겹쳐서 적용된다. 아래 표는 이 문서에서 근거로 인용하는 법령을 정리한 것이다.

| 법령 | 감독기관 | 적용 범위 요약 |
|---|---|---|
| Privacy Act of 1974 (5 U.S.C. §552a) | OMB, 각 연방기관 | 연방기관이 보유한 개인 기록. SSN 수집·공개 제한의 출발점 |
| Identity Theft and Assumption Deterrence Act (1998), Social Security Number Protection Act (2010) | FTC, SSA | SSN 등 식별 수단 도용 처벌, 정부 수표·문서에 SSN 표기 금지 |
| Gramm-Leach-Bliley Act (GLBA, 1999) 및 Safeguards Rule | FTC, CFPB, OCC, FDIC, Fed | 금융기관이 취급하는 비공개 개인 금융정보(NPI): 계좌번호, 라우팅번호, SSN 등 |
| HIPAA Privacy Rule, 45 CFR §164.514(b) Safe Harbor | HHS Office for Civil Rights | 보호 대상 건강정보(PHI). Safe Harbor 는 제거해야 할 18개 식별자를 열거(SSN, 전화번호, 의료기록번호, 건강보험 수혜자번호, 계좌번호, 면허번호, 차량 식별번호 등) |
| MACRA (2015) §501, Social Security Number Removal Initiative | CMS | Medicare 카드에서 SSN 기반 번호를 제거하고 MBI 로 교체 |
| Driver's Privacy Protection Act (DPPA, 18 U.S.C. §2721) | DOJ, 각 주 DMV | 운전면허·차량등록 기록의 공개 제한 |
| Fair Credit Reporting Act (FCRA) | FTC, CFPB | 신용정보의 수집·이용 제한 |
| Telephone Consumer Protection Act (TCPA), CPNI 규정 (47 U.S.C. §222) | FCC | 전화번호 및 통신 이용 기록 보호 |
| IRC §6103, IRS Publication 1075 | IRS | 납세자 정보(SSN, ITIN, EIN 포함) 비밀 유지 |
| 21 CFR Part 1301 (Controlled Substances Act 시행규칙) | DEA | 규제약물 등록번호(DEA number) 관리, 처방 사기 방지 |
| 8 CFR §208.6 및 Privacy Act | DHS, USCIS | 이민 기록, 특히 망명 신청자 정보 비밀 유지 |
| 주 데이터 유출 통지법 (50개 주 전부, 예: Cal. Civ. Code §1798.82) | 각 주 법무장관 | "이름 + SSN / 운전면허번호 / 계좌번호 / 의료정보" 조합을 개인정보로 정의. 유출 시 통지 의무 |
| California CCPA/CPRA (Cal. Civ. Code §1798.100 이하) | California Privacy Protection Agency | 광범위한 개인정보 정의. SSN, 운전면허, 여권, 계좌, 정확한 위치 등을 "민감 개인정보"로 별도 분류 |
| Illinois BIPA, NY SHIELD Act 등 주별 특별법 | 각 주 | 생체정보, 유출 통지 강화 |
| NIST SP 800-122 (참고 문서, 법령 아님) | NIST | 연방기관용 PII 정의 및 보호 지침. SSN, 여권, 운전면허, 계좌, 차량번호 등을 PII 예시로 열거 |

## 2. 요약 표

| pii_type | 설명 | 결정론적 검출 | 권장 검출 방식 | 검증기 (현재 / 구현 가능) | 기존 구현 | 채택 |
|---|---|---|---|---|---|---|
| us_social_security_number | 사회보장번호 (SSN) | 가능 | regex (+ `ssn` 검증기) | 없음 / 범위 배제 규칙 | 기존 | 채택 |
| us_itin | 개인 납세자 번호 (ITIN) | 가능 | regex | 없음 / 없음 (구간 규칙은 regex 로 표현) | 신규 | 채택 |
| us_ein | 고용주 식별번호 (EIN) | 가능 | regex | 없음 / 접두 번호 목록 | 신규 | 미채택 (보류) |
| us_passport | 여권번호 | 가능 (약함) | regex | 없음 / 없음 | 기존 | 채택 |
| us_driver_license | 운전면허·주 신분증 번호 | 가능 (주별 패턴, 약함) | **byte-scan handwritten** (주별 형식 표) | 없음 / 없음 | 신규 | 채택 |
| us_bank_account | ABA 라우팅번호 + 계좌번호 | 가능 | regex 템플릿 (+ `aba_routing` 검증기), 또는 byte-scan | 없음 / ABA 체크 디지트 | 기존 | 채택 |
| us_phonenumber | 북미 번호 체계(NANP) 전화번호 | 가능 | regex (+ NANP 검증기) | `phonenumber`(자리표시자) / NANP 규칙 | 기존 | 채택 |
| us_medicare_beneficiary_identifier | Medicare 수혜자 식별번호 (MBI) | 가능 (형식 엄격) | regex | 없음 / 없음 | 신규 | 채택 |
| us_dea_number | DEA 규제약물 등록번호 | 가능 | regex (+ `dea` 검증기) | 없음 / 체크 디지트 | 신규 | 채택 |
| us_npi | 국가 의료제공자 식별번호 (NPI) | 가능 | regex (+ Luhn 래퍼) | 없음 / Luhn (접두 80840) | 신규 | 미채택 (공개 등록부) |
| us_alien_registration_number | 외국인 등록번호 (A-Number) | 가능 | regex (Aho-Corasick 도 가능하나 이득 적음) | 없음 / 없음 | 신규 | 채택 |
| us_vehicle_identification_number | 차량 식별번호 (VIN) | 가능 | regex (+ `vin` 검증기) | 없음 / 체크 디지트 (mod 11) | 신규 | 조건부 채택 (공통 항목으로 이관 검토) |

이외에 검토했으나 결정론적 검출이 불가능해서 미채택한 항목은 4절에 정리했다.

## 3. 항목별 상세

### us_social_security_number

- **설명**: 사회보장국(SSA)이 발급하는 9자리 개인 식별번호. `AAA-GG-SSSS`(지역-그룹-일련) 형식이다. 2011년 6월 이후 무작위 발급으로 바뀌어 지역번호가 출생지를 뜻하지 않는다. 사실상 미국의 범용 개인 식별자로 쓰인다.
  - 예시: `219-09-9999` (SSA 가 홍보물에 쓰는, 발급된 적 없는 번호), `123-45-6789` (형식 예시). 두 번호 모두 형식은 유효하지만 실제 발급 번호가 아니다.
- **법적 근거**:
  - 법령: Privacy Act of 1974, Identity Theft and Assumption Deterrence Act, Social Security Number Protection Act of 2010, GLBA, HIPAA Safe Harbor 식별자 목록, IRC §6103, 모든 주의 데이터 유출 통지법, CCPA/CPRA "민감 개인정보"
  - 감독기관: SSA, FTC, HHS OCR, IRS, 각 주 법무장관
  - 노출 금지 이유: 신원 도용의 핵심 열쇠이다. 대출·신용카드 개설·세금 환급 사기에 직접 이용되며, 미국 내 어느 법령을 적용하든 예외 없이 개인정보로 분류된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본): 기존 패턴 `([0-9]{3}[- ][0-9]{2}[- ][0-9]{4})` 를 유지한다. 구분자가 없는 9자리 숫자는 여권번호·라우팅번호·전화번호와 충돌하므로 구분자가 있는 형태만 잡는 결정이 타당하다. lookahead 가 없으므로 `000`·`666`·`9xx` 배제는 regex 로 표현할 수 없고 `ssn` 검증기가 맡는다. 오탐: 형식이 `3-2-4` 숫자 조합이면 무엇이든 잡히므로 검증기 없이는 중간 수준이다. 날짜(`123-45-6789` 형태는 드묾)나 부품번호와 충돌할 수 있다.
  - **byte-scan handwritten**: 가능. 숫자열을 뽑아 `3-2-4` 그룹 경계와 구분자(`-`, 공백)를 확인하고, 지역·그룹·일련번호 배제를 코드 안에서 바로 처리한다. 오탐률은 regex + `ssn` 검증기 조합과 **동일**하다. 매칭 단계에서 배제 규칙까지 끝내므로 검증기가 필요 없어지는 것이 유일한 차이다. 단일 패턴이라 DFA 메모리 부담이 없으므로 handwritten 으로 옮길 이유는 약하다. 다만 ITIN·EIN·라우팅번호처럼 "숫자열 + 그룹 규칙" 계열을 하나의 숫자열 스캐너로 묶는다면 SSN 도 그 안에 포함하는 것이 자연스럽다.
  - **Aho-Corasick**: 부적합. 고정 리터럴 접두가 없다.
  - **권장**: regex + `ssn` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬은 없다. 다만 SSA 가 발급하지 않는 범위를 배제하는 규칙을 검증기 `ssn` 으로 구현할 수 있다. 지역번호 `000`, `666`, `900`-`999` 배제, 그룹번호 `00` 배제, 일련번호 `0000` 배제. 광고용으로 예약된 `987-65-4320`-`987-65-4329` 도 배제 대상이다.
- **채택 여부 및 근거**: 채택. 체크섬이 없어도 미국에서 가장 위험도가 높은 식별자이므로 반드시 유지한다.
- **기존 구현 여부**: 기존 (`pii_filter_config.yaml` `us_social_security_number`). 범위 배제 검증기 추가를 권장한다.
- **context_words 후보**: 기존 `social`, `security`, `ssn`, `ss#`, `ssid`, `tax id` 에 더해 `social security number`, `soc sec`, `ssn#`
- **비고**: 아래 ITIN 은 SSN 과 같은 형식이면서 지역번호가 `9` 로 시작한다. `ssn` 검증기가 `9xx` 를 배제하면 겹치는 매치는 `us_itin` 으로 귀속된다. `recognizer.rs` 의 `validate_and_collapse` 가 검증에 실패한 매치를 dedup·겹침 해소 이전에 버리므로 이 동작은 코드상 보장된다.

### us_itin

- **설명**: Individual Taxpayer Identification Number. SSN 을 받을 수 없는 납세자(비거주 외국인, 일부 이민자 등)에게 IRS 가 발급하는 9자리 세금 신고용 번호. SSN 과 같은 `9XX-XX-XXXX` 형식이며, 첫 자리가 항상 `9` 이고 4-5번째 자리(그룹번호)가 `50`-`65`, `70`-`88`, `90`-`92`, `94`-`99` 구간에 속한다.
  - 예시: `912-70-1234`, `900-94-5678` (형식 예시. 그룹번호 `70`, `94` 가 유효 구간에 속한다)
- **법적 근거**:
  - 법령: IRC §6103 (납세자 정보 비밀), IRS Publication 1075, 주 데이터 유출 통지법(다수 주가 "납세자 식별번호"를 명시), CCPA/CPRA
  - 감독기관: IRS, 각 주 법무장관
  - 노출 금지 이유: SSN 과 동일하게 세금 환급 사기와 신원 도용에 쓰인다. 또한 ITIN 보유 사실 자체가 이민 신분을 추정하게 하므로 민감도가 높다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본): `9[0-9]{2}[- ](5[0-9]|6[0-5]|7[0-9]|8[0-8]|9[0-2]|9[4-9])[- ][0-9]{4}`. 그룹번호 구간은 lookahead 없이 선택 그룹으로 표현된다. 구분자 없는 9자리는 SSN 과 같은 이유로 제외한다. 오탐: 첫 자리 `9` 와 그룹번호 구간 제한 덕분에 SSN 패턴보다 낮다.
  - 주의: 그룹번호 구간은 IRS 가 수시로 확장해 왔으므로, 구현 시점에 IRS 최신 공고로 재확인해야 한다.
  - **byte-scan handwritten**: 가능. SSN 과 같은 숫자열 스캐너에서 첫 자리 `9` 와 그룹번호 구간을 표로 대조하면 된다. 오탐률은 regex 와 **동일**하다. 구간 표가 IRS 공고에 따라 바뀔 때 regex 문자열보다 코드 표를 고치는 편이 읽기 쉽다는 유지보수상 이점만 있다.
  - **Aho-Corasick**: 부적합. 접두가 `9` 한 글자뿐이라 anchor 로 쓰면 텍스트의 모든 `9` 에서 verifier 가 호출된다. 이득이 없다.
  - **권장**: regex. SSN 을 숫자열 스캐너로 옮긴다면 그때 함께 옮긴다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 구간 규칙은 regex 에 이미 포함되므로 별도 검증기가 필요 없다.
- **채택 여부 및 근거**: 채택. SSN 과 동급의 위험도이며 regex 만으로 SSN 보다 오히려 더 정밀하게 구분된다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `itin`, `individual taxpayer`, `taxpayer identification`, `tax id`, `tin`, `w-7`, `납세자 번호`

### us_ein

- **설명**: Employer Identification Number. IRS 가 사업체·법인·신탁 등에 발급하는 9자리 번호. `XX-XXXXXXX` 형식이며, 앞 두 자리 접두는 발급 캠퍼스에 따라 정해진 유효 목록(`01`-`06`, `10`-`16`, `20`-`27`, `30`-`39`, `40`-`48`, `50`-`59`, `60`-`68`, `71`-`77`, `80`-`88`, `90`-`95`, `98`-`99`)에 속한다.
  - 예시: `12-3456789` (IRS 서식 안내에 쓰이는 형식 예시), `98-7654321`
- **법적 근거**:
  - 법령: IRC §6103 이 형식상 적용되지만, 실제로 EIN 은 W-2, 1099, 비영리단체 Form 990 등 공개 문서에 널리 인쇄된다.
  - 감독기관: IRS
  - 노출 금지 이유: 개인이 아니라 조직의 식별자이므로 개인정보 성격이 약하다. 다만 개인사업자(sole proprietor)의 EIN 은 개인과 직결되고, EIN 을 이용한 사업자 명의 신용 사기 사례가 존재한다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본): `(0[1-6]|1[0-6]|2[0-7]|3[0-9]|4[0-8]|5[0-9]|6[0-8]|7[1-7]|8[0-8]|9[0-5]|9[89])-[0-9]{7}`. 오탐: `2-7` 숫자 조합은 흔치 않아 낮은 편이다.
  - **byte-scan handwritten**: 가능. 숫자열 스캐너에서 `2-7` 그룹과 접두 표를 대조한다. 오탐률은 regex 와 **동일**하다.
  - **Aho-Corasick**: 부적합. 접두가 2자리 숫자 수십 개라 anchor 가 너무 짧고 많다.
  - **권장**: (채택 시) regex.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 접두 목록은 regex 에 포함된다.
- **채택 여부 및 근거**: 미채택 (보류). 조직 식별자이고 공개 문서에 흔히 등장하므로 개인정보 마스킹 대상으로 보기 어렵다. 개인사업자 보호가 요구사항으로 추가되면 재검토한다.
- **기존 구현 여부**: 신규 (미채택이므로 구현하지 않음)
- **context_words 후보** (재검토 시 참고): `ein`, `employer identification`, `federal tax id`, `fein`, `tax id number`

### us_passport

- **설명**: 국무부(State Department)가 발급하는 여권 번호. 구형은 9자리 숫자, 2021년 이후 Next Generation Passport 는 영문자 1자 + 숫자 8자리이다. 여권 카드(Passport Card)는 `C` + 숫자 8자리이다.
  - 예시: `123456789` (구형 9자리), `A12345678` (Next Generation Passport), `C12345678` (여권 카드)
- **법적 근거**:
  - 법령: Privacy Act of 1974, 주 데이터 유출 통지법(다수 주가 여권번호를 명시), CCPA/CPRA "민감 개인정보", NIST SP 800-122
  - 감독기관: State Department, 각 주 법무장관
  - 노출 금지 이유: 여권번호는 정부 발급 신분증 번호로서 신원 확인·항공권 예약·금융 KYC 에 쓰인다. 유출 시 신원 도용과 여행 서류 위조에 이용된다.
- **결정론적 검출 가능성**: 가능하나 정밀도가 낮다.
  - **regex** (기본): 기존 패턴 `([a-zA-Z]\d{8}|[0-9]{9})`. 오탐: 높다. 9자리 숫자는 라우팅번호·구분자 없는 SSN 과, 영문자 1자 + 숫자 8자리는 다른 국가 여권·운전면허·제품 일련번호와 겹친다. context_words 가 사실상 유일한 필터이다.
  - **byte-scan handwritten**: 가능하지만 이득이 없다. 형식에 표나 체크섬이 없어서 코드로 옮겨도 오탐률이 regex 와 **동일**하다. 패턴이 2개뿐이라 메모리 이점도 없다.
  - **Aho-Corasick**: 부적합. 고정 접두가 없다(여권 카드의 `C` 는 1글자라 anchor 로 부적합).
  - **권장**: regex 유지. 정밀도 개선은 context_words 확충으로만 가능하다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 여권 번호 자체에는 체크섬이 없다. MRZ(기계 판독 영역)에는 체크 디지트가 있지만 번호만 단독으로 등장할 때는 쓸 수 없다.
- **채택 여부 및 근거**: 채택. 검증기는 없지만 정부 발급 신분증 번호로서 주법과 CCPA 가 명시적으로 민감 정보로 분류하므로 유지한다.
- **기존 구현 여부**: 기존 (`pii_filter_config.yaml` `us_passport`)
- **context_words 후보**: 기존 `passport` 에 더해 `passport number`, `passport no`, `passport #`, `travel document`, `여권`

### us_driver_license

- **설명**: 각 주 DMV 가 발급하는 운전면허번호 및 주 신분증(State ID) 번호. 형식이 주마다 다르다. 예를 들어 California 는 영문자 1자 + 숫자 7자리, New York 은 숫자 9자리, Texas 는 숫자 8자리, Florida 는 영문자 1자 + 숫자 12자리, Illinois 는 영문자 1자 + 숫자 11자리, Wisconsin 은 영문자 1자 + 숫자 13자리이다. Florida, Illinois, Wisconsin, Maryland, Michigan, Minnesota, New Hampshire, Washington 등은 성(姓)의 Soundex 코드와 생년월일을 번호에 인코딩한다.
  - 예시: `A1234567` (CA), `123456789` (NY), `12345678` (TX), `A123-456-78-901-0` (FL, 구분자 표기), `A123-4567-8901` (IL), `A123-4567-8901-23` (WI). 모두 형식 예시이며 실제 발급 번호가 아니다.
- **법적 근거**:
  - 법령: DPPA (18 U.S.C. §2721), 모든 주의 데이터 유출 통지법(운전면허번호를 명시), CCPA/CPRA "민감 개인정보", HIPAA Safe Harbor 식별자("certificate/license numbers"), NIST SP 800-122
  - 감독기관: DOJ, 각 주 DMV, 각 주 법무장관
  - 노출 금지 이유: 미국에서 가장 널리 쓰이는 신분증이며, 계좌 개설과 신원 확인에 SSN 다음으로 자주 요구된다. 주법이 예외 없이 개인정보로 명시한다.
- **결정론적 검출 가능성**: 가능하나 정밀도가 낮다. 주별 형식을 모두 다루면 패턴 수가 수십 개에 이른다.
  - **regex** (기본): 주별 패턴을 여러 개 등록한다. 대표 예시(주별 전체 목록은 별도 부록으로 작성 필요):
    - `[A-Z][0-9]{7}` (CA, 그 외 다수 주)
    - `[A-Z][0-9]{12}` (FL), `[A-Z][0-9]{11}` (IL), `[A-Z][0-9]{13}` (WI)
    - `[A-Z][0-9]{3}-[0-9]{3}-[0-9]{2}-[0-9]{3}-[0-9]` (FL 구분자 표기), `[A-Z][0-9]{3}-[0-9]{4}-[0-9]{4}` (IL 구분자 표기), `[A-Z][0-9]{3}-[0-9]{4}-[0-9]{4}-[0-9]{2}` (WI 구분자 표기)
    - `[0-9]{9}` (NY, 그 외), `[0-9]{8}` (TX, 그 외), `[0-9]{7}` (일부 주)
    - `[A-Z]{2}[0-9]{6}[A-Z]` (VA 구형 등)
    - 오탐: 높다. 특히 숫자만 있는 7-9자리 패턴은 단독으로는 거의 모든 숫자열과 충돌하므로 context_words 가 반드시 함께 있어야 한다. 또한 50개 주 전체를 담으면 카드번호(105개 패턴)와 같은 이유로 DFA 메모리가 커진다.
  - **byte-scan handwritten**: **적합**. `CardDetector` 와 같은 구조로, 영숫자열을 뽑은 뒤 "(선행 영문자 수, 숫자 수, 총 길이, 구분자 위치)" 조합을 주별 형식 표(`brand_for` 의 `CARD_BRANDS` 표에 대응)와 대조한다. 오탐률은 같은 형식 집합을 regex 로 등록했을 때와 **동일**하다. 표 대조가 regex 의 union 과 같은 집합을 받아들이기 때문이다. 이 방식의 이점은 오탐이 아니라 메모리이다. 패턴 수가 늘어도 DFA 상태가 늘지 않는다.
  - **Aho-Corasick**: 부적합. 주별로 고정 접두가 없다.
  - **권장**: **byte-scan handwritten**. 주별 형식이 10개를 넘는 시점부터 regex 보다 유리하다. 초기 구현에서 몇 개 주만 다룬다면 regex 로 시작해도 된다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 범용 체크섬은 없다. Soundex 인코딩 주는 첫 문자가 성의 첫 글자와 일치하는지 등의 구조 검증이 이론상 가능하지만, 텍스트에서 이름을 알 수 없으므로 실용성이 없다.
- **채택 여부 및 근거**: 채택. 검증기가 없고 오탐 위험이 있지만, 주법과 DPPA 가 명시적으로 보호하는 핵심 신분증 번호이므로 context_words 필수 조건으로 유지한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `driver license`, `driver's license`, `drivers license`, `dl#`, `dl number`, `license number`, `lic#`, `dmv`, `state id`, `id card`, `운전면허`. 기존 `kr_driver_license` 의 영문 context_words(`driver`, `license`, `permit`, `lic`, `dls`, `cdls`, `driving`)와 공유 가능하다.

### us_bank_account

- **설명**: 미국 은행 계좌를 지정하는 두 숫자의 조합이다. ABA 라우팅번호(Routing Transit Number)는 9자리이며 은행을 식별하고, 계좌번호는 은행마다 4-17자리로 자유 형식이다. 수표 하단 MICR 줄에 "라우팅번호 계좌번호 수표번호" 순서로 인쇄된다.
  - 예시: `021000021 1234567890`, `011000015-123456789012`. 라우팅번호 `021000021`(JPMorgan Chase, NY)과 `011000015`(Federal Reserve Bank of Boston)는 공개된 실제 라우팅번호이며 ABA 체크 디지트를 통과한다. 뒤의 계좌번호는 가상의 값이다.
- **법적 근거**:
  - 법령: GLBA (비공개 개인 금융정보), 모든 주의 데이터 유출 통지법(계좌번호 + 접근 코드 조합을 명시), HIPAA Safe Harbor 식별자("account numbers"), CCPA/CPRA "민감 개인정보"(금융 계좌 + 접근 자격 증명), NIST SP 800-122
  - 감독기관: FTC, CFPB, OCC, FDIC, Fed, 각 주 법무장관
  - 노출 금지 이유: 라우팅번호 + 계좌번호만 있으면 ACH 인출과 수표 위조가 가능하다. GLBA 가 금융기관에 직접 보호 의무를 부과한다.
- **결정론적 검출 가능성**: 가능. 라우팅번호 단독 9자리는 SSN·여권과 충돌하므로 계좌번호가 뒤따르는 조합만 잡는 기존 설계가 타당하다.
  - **regex** (기본): 기존 `PatternTemplateRecognizer` 패턴 `{ROUTING_NUMBER}\s[A-Za-z\d]{6,17}(\s\d{3,4})?` 및 `-`, `:` 구분자 변형. `{ROUTING_NUMBER}` 는 `config/default/ROUTING_NUMBER.txt` 에서 확장되며 현재 내용은 `\d{9}` 와 `0\d{8}` 두 줄이다(둘째 줄은 첫째 줄에 포함되므로 사실상 중복이다). 개선 후보: 라우팅번호 앞 두 자리는 Federal Reserve 가 배정한 구간(`00`-`12`, `21`-`32`, `61`-`72`, `80`)에만 속하므로, `ROUTING_NUMBER.txt` 의 두 줄을 `(0[0-9]|1[0-2]|2[1-9]|3[0-2]|6[1-9]|7[0-2]|80)[0-9]{7}` 한 줄로 교체해 좁힐 수 있다. 오탐: "9자리 + 구분자 + 6-17자리 영숫자" 조합은 자연어에서 드물어 중간 이하이며, 접두 구간과 체크 디지트를 더하면 낮아진다.
  - **byte-scan handwritten**: 가능하며 검증기와의 결합이 더 자연스럽다. 숫자열 9자리를 뽑아 접두 구간 표와 ABA 체크 디지트를 매칭 단계에서 바로 확인하고, 이어지는 구분자와 6-17자리 영숫자를 검사한다. 오탐률은 "regex + 접두 구간 + `aba_routing` 검증기" 조합과 **동일**하다. 차이는 검증기가 매치 전체 문자열을 받아 앞 9자리를 스스로 잘라내야 하는 반면, handwritten 은 라우팅 부분에만 체크 디지트를 적용하기 쉽다는 구현상의 편의뿐이다.
  - **Aho-Corasick**: 부적합. 접두 구간이 2자리 숫자 37개라 anchor 가 짧고 많아서 verifier 가 텍스트 곳곳에서 호출된다.
  - **권장**: regex 템플릿 유지 + `aba_routing` 검증기. 다른 숫자열 계열(SSN, ITIN)을 byte-scan 으로 통합할 때 함께 옮기는 선택지도 있다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: ABA 라우팅번호 체크 디지트. `3*(d1+d4+d7) + 7*(d2+d5+d8) + (d3+d6+d9)` 가 10의 배수이면 유효하다. 검증기 `aba_routing` 으로 구현하면 매치의 앞 9자리에만 적용하면 된다. 계좌번호 부분은 표준이 없어 검증할 수 없다.
- **채택 여부 및 근거**: 채택. 검증기 구현이 가능하고 GLBA 직접 적용 대상이다.
- **기존 구현 여부**: 기존 (`pii_filter_config.yaml` `us_bank_account`). `aba_routing` 검증기와 접두 구간 제한 추가를 권장한다.
- **context_words 후보**: 기존 `bank`, `check`, `account`, `acct`, `save`, `debit`, `계좌`, `은행` 에 더해 `routing`, `routing number`, `aba`, `ach`, `wire`, `checking`, `savings`, `account number`

### us_phonenumber

- **설명**: 북미 번호 체계(NANP)를 따르는 10자리 전화번호. `NPA-NXX-XXXX` 형식이며 국가번호 `+1` 이 앞에 붙을 수 있다. NPA(지역번호)와 NXX(국번)의 첫 자리는 `2`-`9` 이고, NXX 의 둘째·셋째 자리가 `11` 인 형태(`N11`)는 특수 서비스 번호로 예약되어 있다.
  - 예시: `(212) 555-0123`, `212-555-0123`, `212.555.0123`, `+1 212 555 0123`, `2125550123`. `555-0100`-`555-0199` 구간은 NANP 가 영화·문서용으로 예약한 번호라 실제 가입자가 없다.
- **법적 근거**:
  - 법령: TCPA, CPNI 규정 (47 U.S.C. §222), HIPAA Safe Harbor 식별자("telephone numbers"), CCPA/CPRA (개인정보 정의에 포함), COPPA (아동 대상)
  - 감독기관: FCC, FTC, HHS OCR
  - 노출 금지 이유: 단독으로는 신원 도용 위험이 낮지만, SIM 스와핑·스미싱·2단계 인증 우회의 진입점이며 HIPAA 는 명시적으로 제거 대상 식별자로 열거한다. 대부분의 주 유출 통지법은 전화번호 단독을 개인정보로 보지 않으므로, 다른 항목보다 노출 시 위험도는 낮다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본): 기존 패턴 `((?-u:\b)|\(|\+1)[0-9]{3}([\)\-\.\_ ]|(\) ))?[0-9]{3}[ -]?[0-9]{4}(?-u:\b)`. 한계: 지역번호와 국번의 첫 자리에 `0`, `1` 을 허용하므로 NANP 상 존재할 수 없는 번호도 잡고, 구분자 없는 10자리 숫자를 허용하므로 다른 숫자열과 충돌한다. 개선 후보: `((?-u:\b)|\(|\+1[ .-]?)(\([2-9][0-9]{2}\)|[2-9][0-9]{2})[ .-]?[2-9][0-9]{2}[ .-]?[0-9]{4}(?-u:\b)`. 오탐: 구분자 없는 10자리를 허용하는 한 중간 수준이며, 첫 자리 제한으로 약 1/3 가량 줄어든다.
  - 주의: `us_phonenumber` 는 다른 `us_*` recognizer 와 달리 YAML 에 `boundary_check: true` 가 없다. 단어 경계는 오직 패턴 안의 `(?-u:\b)` 가 담당하므로, 패턴을 교체할 때 이 앵커를 빼면 긴 숫자열 안의 10자리 창을 잡게 된다. 앵커를 유지하거나 `boundary_check: true` 를 함께 추가해야 한다.
  - **byte-scan handwritten**: 가능. 숫자열(선택적 `+1`, 괄호, 구분자 포함)을 뽑아 10자리인지, NPA·NXX 첫 자리가 `2`-`9` 인지, `N11` 이 아닌지를 코드로 검사한다. 오탐률은 "개선 regex + NANP 검증기" 조합과 **동일**하다.
  - **Aho-Corasick**: 부분적으로만 가능. `kr_phonenumber` 는 모든 휴대전화가 `010` 으로 시작하기 때문에 anchor `010` 이 성립했지만, 미국 번호는 고정 접두가 없다. `+1` 과 `(` 를 anchor 로 삼으면 국가번호·괄호 표기만 잡고 `212-555-1234` 같은 맨 번호는 놓치므로, regex 와 병행하지 않는 한 재현율이 크게 떨어진다.
  - **권장**: regex (개선 후보) + NANP 검증기.
- **검증기**:
  - 현재: `phonenumber` (항상 `true` 를 돌려주는 자리표시자)
  - 구현 가능: NANP 규칙 검증. NPA 첫 자리 `2`-`9`, NXX 첫 자리 `2`-`9`, NXX 가 `N11` 이 아님. 체크섬은 아니지만 오탐을 줄인다. (`555-01XX` 허구 번호는 실제 가입자가 없더라도 마스킹해서 해로울 것이 없으므로 배제하지 않는다.)
- **채택 여부 및 근거**: 채택. 위험도는 낮으나 HIPAA 와 CCPA 가 명시하고, 기존 구현이 이미 존재한다.
- **기존 구현 여부**: 기존 (`pii_filter_config.yaml` `us_phonenumber`). 현재 `layers` 가 `default` 만 지정되어 있어 input 차단과 output 마스킹에는 적용되지 않는다. 이 문서는 사실만 기록하며, 계층 정책 변경 여부는 별도로 결정한다.
- **context_words 후보**: 기존 목록(`phone`, `telephone`, `cell`, `mobile`, `call`, `sms` 등)에 더해 `tel`, `fax`, `text me`, `전화`, `휴대폰`

### us_medicare_beneficiary_identifier

- **설명**: Medicare Beneficiary Identifier (MBI). 2018-2019년 CMS 가 SSN 기반 HICN 을 대체하기 위해 도입한 11자리 식별번호. 형식이 엄격하게 정해져 있다. 자리별 규칙은 `C A AN N A AN N A A N N` 이며, C 는 `1`-`9`, N 은 숫자, A 는 `S`, `L`, `O`, `I`, `B`, `Z` 를 제외한 대문자, AN 은 숫자 또는 그 대문자이다. 카드에는 `1EG4-TE5-MK73` 처럼 하이픈을 넣어 인쇄된다.
  - 예시: `1EG4-TE5-MK73` (CMS 가 안내 자료에 쓰는 공식 예시), `1EG4TE5MK73` (하이픈 없는 표기)
- **법적 근거**:
  - 법령: HIPAA Privacy Rule (건강보험 수혜자번호는 Safe Harbor 식별자), MACRA 2015 §501 (SSN Removal Initiative), Privacy Act of 1974
  - 감독기관: CMS, HHS OCR
  - 노출 금지 이유: Medicare 청구 사기의 직접 수단이다. CMS 는 MBI 를 "기밀로 취급하고 SSN 과 동등하게 보호"하도록 요구한다. 보유 사실 자체가 65세 이상 또는 장애 여부를 드러낸다.
- **결정론적 검출 가능성**: 가능하며, 자리별 문자 집합이 엄격해서 오탐이 적다.
  - **regex** (기본): `[1-9][AC-HJKMNP-RT-Y][0-9AC-HJKMNP-RT-Y][0-9]-?[AC-HJKMNP-RT-Y][0-9AC-HJKMNP-RT-Y][0-9]-?[AC-HJKMNP-RT-Y]{2}[0-9]{2}` (하이픈 선택). 오탐: 낮다. 11자리 안에서 숫자·영문자 위치가 고정되어 있어 무작위 영숫자열이 우연히 맞을 확률이 매우 작다. 소문자 표기는 규격 밖이지만 사용자 입력에서는 나타날 수 있으므로, 대소문자 무시 옵션 적용 여부를 구현 시 결정한다.
  - **byte-scan handwritten**: 가능. 영숫자열 11자리(하이픈 제거)를 뽑아 자리별 문자 집합 표와 대조한다. 오탐률은 regex 와 **동일**하다. 단일 패턴이라 메모리 이점도 없으므로 옮길 이유가 없다.
  - **Aho-Corasick**: 부적합. 첫 자리가 `1`-`9` 로만 정해져 있어 고정 접두가 없다.
  - **권장**: regex.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 자리별 규칙이 regex 에 이미 포함되어 있다.
- **채택 여부 및 근거**: 채택. 검증기는 없지만 형식 자체가 강한 필터 역할을 하고, HIPAA 와 CMS 가 SSN 급으로 보호를 요구한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `medicare`, `mbi`, `beneficiary`, `medicare number`, `medicare id`, `cms`, `health insurance claim`
- **비고**: 구형 HICN(SSN + 영문 접미 1-2자, 예: `123-45-6789A`)은 2020년 이후 폐지되었으나 오래된 문서에 남아 있을 수 있다. SSN 패턴이 앞부분을 잡으므로 별도 recognizer 는 두지 않는다.

### us_dea_number

- **설명**: DEA Registration Number. 마약단속국(DEA)이 규제약물을 처방·조제·제조할 수 있는 의사, 약사, 병원 등에 발급하는 등록번호. 영문자 2자 + 숫자 7자리이다. 첫 문자는 등록자 유형(`A`, `B`, `F`, `G` 는 의사·병원·약국, `M` 은 중급 처방자, `P`, `R` 은 제조·유통, `X` 는 부프레노르핀 처방 허가 등), 둘째 문자는 등록자 성의 첫 글자(또는 `9`)이다.
  - 예시: `AB1234563` (형식 예시. `(1+3+5) + 2*(2+4+6) = 33` 이므로 체크 디지트 `3` 이 맞다), `FA1234563`
- **법적 근거**:
  - 법령: Controlled Substances Act 및 21 CFR Part 1301, HIPAA (개별 의료제공자와 결합 시 PHI 의 일부), DEA 의 등록번호 비공개 지침
  - 감독기관: DEA
  - 노출 금지 이유: 처방전 위조의 핵심 요소이다. DEA 는 등록번호를 처방 목적 외에 사용하거나 공개하지 말 것을 명시적으로 요구하며, 유출된 번호는 오피오이드 등 규제약물의 불법 취득에 직접 쓰인다. 개인 의료제공자에게 발급되므로 개인 식별정보이기도 하다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본): `[ABCDEFGHJKLMPRSTUX][A-Z9][0-9]{7}`. 오탐: 검증기 없이는 중간 수준이다. 영문자 2자 + 숫자 7자리는 여권·운전면허·제품 코드와 겹친다. `dea` 체크 디지트를 붙이면 우연히 맞는 비율이 1/10 로 줄어 낮아진다.
  - **byte-scan handwritten**: 가능. 영문자 2자 + 숫자 7자리를 뽑고 첫 문자 집합과 체크 디지트를 코드 안에서 바로 계산한다. 오탐률은 "regex + `dea` 검증기" 조합과 **동일**하다.
  - **Aho-Corasick**: 부적합. 첫 문자 18종 × 둘째 문자 27종의 2바이트 anchor 조합은 너무 많고 짧다.
  - **권장**: regex + `dea` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크 디지트. 숫자 7자리를 `d1`-`d7` 이라 할 때 `(d1+d3+d5) + 2*(d2+d4+d6)` 의 일의 자리가 `d7` 과 같으면 유효하다. 검증기 `dea` 로 구현한다.
- **채택 여부 및 근거**: 채택. 체크 디지트로 정밀도를 높일 수 있고, 처방 사기라는 명확한 위해가 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `dea`, `dea number`, `dea#`, `dea registration`, `prescriber`, `controlled substance`, `npi` (함께 등장하는 경우가 많음)

### us_npi

- **설명**: National Provider Identifier. CMS 가 모든 의료제공자(개인·기관)에게 발급하는 10자리 번호. HIPAA 거래 표준에서 의료제공자 식별에 쓰인다.
  - 예시: `1234567893` (CMS 의 NPI 체크 디지트 안내 문서에 실린 공식 예시. `80840` 접두를 붙인 Luhn 검사를 통과한다)
- **법적 근거**:
  - 법령: HIPAA Administrative Simplification (45 CFR Part 162)
  - 감독기관: CMS
  - 노출 금지 이유: 약하다. NPI 는 CMS 의 NPPES 등록부에서 이름·주소와 함께 **공개 조회**가 가능하도록 설계되었다. 다만 DEA 번호와 조합되면 처방 사기에 쓰이고, 의료 청구 사기에 이용된 사례가 있다.
- **결정론적 검출 가능성**: 가능하나 10자리 숫자는 전화번호와 충돌한다.
  - **regex** (기본): `[1-9][0-9]{9}`. 오탐: 검증기 없이는 매우 높다(구분자 없는 전화번호와 구분 불가). Luhn 래퍼를 붙이면 1/10 로 줄지만 여전히 전화번호가 우연히 통과할 수 있다.
  - **byte-scan handwritten**: 가능. 10자리 숫자열에 `80840` 접두를 붙여 Luhn 을 바로 계산한다. 오탐률은 "regex + `npi` 검증기"와 **동일**하다.
  - **Aho-Corasick**: 부적합. 고정 접두가 없다.
  - **권장**: (채택 시) regex + `npi` 검증기.
- **검증기**:
  - 현재: `luhn` 이 존재하지만 그대로 쓸 수는 없다.
  - 구현 가능: NPI 는 접두 `80840` 을 붙인 15자리에 대해 Luhn 을 적용한다. 기존 `luhn` 함수에 `"80840"` + 번호를 넘기는 얇은 래퍼 `npi` 로 구현할 수 있다.
- **채택 여부 및 근거**: 미채택. 공개 등록부에 게시되는 번호이므로 마스킹 대상 개인정보로 보기 어렵다. 의료 사기 방지가 요구사항으로 추가되면 Luhn 검증기가 있으므로 도입 비용은 낮다.
- **기존 구현 여부**: 신규 (미채택이므로 구현하지 않음)
- **context_words 후보** (재검토 시 참고): `npi`, `national provider`, `provider id`, `provider number`

### us_alien_registration_number

- **설명**: Alien Registration Number (A-Number, USCIS Number). USCIS 가 이민자·영주권자·망명 신청자 등에게 부여하는 번호. `A` 뒤에 숫자 7-9자리가 오며, 현재 발급되는 번호는 9자리이다. 영주권(Green Card), 취업허가증(EAD), 이민 관련 서류 대부분에 인쇄된다.
  - 예시: `A123456789`, `A-123456789`, `A 123 456 789` (9자리), `A12345678` (구형 8자리). 모두 형식 예시이다.
- **법적 근거**:
  - 법령: Privacy Act of 1974 (DHS 시스템 기록), 8 CFR §208.6 (망명 신청자 정보 비밀), CCPA/CPRA (이민 신분은 "민감 개인정보"의 "시민권 또는 이민 상태" 범주에 해당), 일부 주 데이터 유출 통지법이 "정부 발급 신분번호"로 포괄
  - 감독기관: DHS, USCIS, ICE
  - 노출 금지 이유: 번호 자체가 정부 발급 식별번호이면서, 보유 사실이 이민 신분을 직접 드러낸다. 망명 신청자의 경우 노출이 신변 위험으로 이어질 수 있다.
- **결정론적 검출 가능성**: 가능하나 `A` + 숫자 형태는 짧아서 오탐이 있다.
  - **regex** (기본): `[aA][- ]?[0-9]{7,9}`. 오탐: 중간 수준이다. `A1234567` 같은 형태는 제품 코드·좌석번호·문서 번호에서도 나타난다. 단어 경계 검사와 context_words 가 필수이다.
  - **byte-scan handwritten**: 가능하지만 이득이 없다. 체크섬과 접두 표가 없으므로 오탐률이 regex 와 **동일**하다.
  - **Aho-Corasick**: 형식상 가능하다. 이 항목은 고정 리터럴 접두(`A`)가 있는 유일한 미국 항목이다. 다만 anchor `A`/`a` 는 1바이트라 텍스트의 모든 A 에서 verifier 가 호출되므로 `010`(3바이트) 같은 anchor 에 비해 이득이 거의 없다. `A-`, `A ` 를 anchor 로 쓰면 구분자 없는 `A123456789` 를 놓친다. 오탐률은 regex 와 **동일**하다(verifier 가 같은 형식을 검사하므로).
  - **권장**: regex. 단일 패턴이라 메모리 부담이 없고, Aho-Corasick 으로 옮겨도 오탐·성능 이득이 없다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음.
- **채택 여부 및 근거**: 채택. 검증기는 없지만 이민 신분이라는 특수 민감정보를 드러내며 CCPA 가 명시적으로 민감 범주로 분류한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `alien number`, `alien registration`, `a-number`, `a number`, `a#`, `uscis`, `uscis number`, `uscis#`, `green card`, `permanent resident`, `ead`, `i-94`, `외국인등록`

### us_vehicle_identification_number

- **설명**: Vehicle Identification Number (VIN). 1981년 이후 차량에 부여되는 17자리 영숫자 식별번호. `I`, `O`, `Q` 를 쓰지 않는다. 형식은 ISO 3779 국제 표준이지만, 9번째 자리의 체크 디지트는 미국·캐나다(49 CFR §565)에서만 의무이다.
  - 예시: `1HGCM82633A004352` (체크 디지트 `3`, 널리 인용되는 예시), `1HGBH41JXMN109186` (체크 디지트 `X`=10 인 경우). 두 값 모두 mod 11 검증을 통과한다.
- **법적 근거**:
  - 법령: HIPAA Safe Harbor 식별자("vehicle identifiers and serial numbers, including license plate numbers"), DPPA (차량 등록 기록), NIST SP 800-122 (PII 예시로 열거), 49 CFR §565
  - 감독기관: HHS OCR, NHTSA, 각 주 DMV
  - 노출 금지 이유: VIN 은 소유자 조회·차량 등록 기록·보험 기록과 연결되어 개인을 식별할 수 있다. HIPAA 가 명시적으로 제거 대상으로 열거한다. 다만 차량 앞유리에 공개적으로 표시되므로 단독 노출의 위험도는 낮다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본): `[A-HJ-NPR-Z0-9]{17}`. 오탐: 검증기 없이는 중간 수준이다. 17자리 영숫자는 해시·일련번호·토큰 조각과 겹친다. `vin` 체크 디지트를 붙이면 우연히 통과할 확률이 1/11 로 줄어 낮아진다.
  - **byte-scan handwritten**: 가능. 17자리 영숫자열(I·O·Q 제외)을 뽑아 치환표와 가중치로 체크 디지트를 매칭 단계에서 바로 계산한다. 오탐률은 "regex + `vin` 검증기" 조합과 **동일**하다. 단일 패턴이라 메모리 이점은 없다.
  - **Aho-Corasick**: 부적합. 첫 자리(WMI 지역 코드)가 `1`-`5`(북미), `J`(일본) 등으로 다양해 고정 접두가 없다.
  - **권장**: regex + `vin` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크 디지트. 각 문자를 49 CFR §565 의 치환표에 따라 숫자로 바꾸고(A-H = 1-8, J-N = 1-5, P = 7, R = 9, S-Z = 2-9, 숫자는 그대로, I·O·Q 는 사용하지 않음) 자리별 가중치 `8 7 6 5 4 3 2 10 0 9 8 7 6 5 4 3 2` 를 곱해 합한 뒤 11로 나눈 나머지가 9번째 자리(`0`-`9` 또는 `X`=10)와 같으면 유효하다. 검증기 `vin` 으로 구현한다.
- **채택 여부 및 근거**: 조건부 채택. 검증기가 있고 HIPAA 가 명시하지만, VIN 형식은 국제 표준이고 체크 디지트도 북미 차량 전체에 적용되므로 `us_` 접두보다 공통 항목으로 두는 편이 맞을 수 있다. 다른 국가 문서를 작성한 뒤 공통 항목으로 이관할지 최종 결정한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `vin`, `vehicle identification`, `vehicle id`, `chassis`, `car`, `vehicle`, `차대번호`

## 4. 검토 후 미채택한 항목

아래 항목은 법령상 PII 이지만 결정론적 검출이 불가능하거나 오탐이 지나치게 많아 recognizer 로 등록하지 않는다. 향후 NER 기반 검출을 도입하면 재검토한다.

| 항목 | 법적 근거 | 미채택 이유 |
|---|---|---|
| ZIP 코드 (5자리, ZIP+4) | HIPAA Safe Harbor (앞 3자리 조건부 허용), CCPA | 5자리 숫자는 다른 모든 숫자열과 충돌한다. 단독으로는 식별력이 낮고, HIPAA 도 앞 3자리는 허용한다. |
| 의료기록번호 (MRN) | HIPAA Safe Harbor | 병원마다 형식이 다르고 표준이 없다. |
| 건강보험 가입자번호 (Medicare 외 민간 보험) | HIPAA Safe Harbor | 보험사마다 형식이 다르다. MBI 만 별도 채택한다. |
| DoD ID (EDIPI, 10자리) | Privacy Act, DoD 5400.11 | 10자리 숫자는 전화번호와 충돌하고 체크섬이 없다. 군 관련 맥락이 필요하면 재검토한다. |
| 차량 번호판 | HIPAA Safe Harbor, DPPA | 주마다 형식이 다르고 대부분 일반 단어·숫자 조합과 구분되지 않는다. |
| 주소, 생년월일, 이름 | HIPAA Safe Harbor, CCPA, 주법 | 국가 종속 항목이 아니며 regex 로 결정론적 검출이 불가능하다. 공통 항목 또는 NER 로 다룬다. |
| 생체정보 | Illinois BIPA, CCPA | 텍스트 형태로 나타나지 않는다. |
| 신용카드번호, 이메일, IP 주소 | GLBA, PCI DSS, CCPA | 국가 종속 항목이 아니므로 이 문서 범위 밖이다. 기존 `card_number` 등이 담당한다. |

## 5. 구현 시 후속 작업 요약

이 문서에서 도출된, YAML·`validator.rs`·`handwritten/` 에 반영할 작업 목록이다.

| 작업 | 대상 | 종류 |
|---|---|---|
| `ssn` 범위 배제 검증기 추가 | us_social_security_number | validator 신규 |
| `us_itin` recognizer 추가 | us_itin | YAML 신규 |
| `us_driver_license` byte-scan detector 추가 (주별 형식 표 부록 필요). 초기에 소수 주만 다루면 regex 로 시작 가능 | us_driver_license | handwritten 신규 (또는 YAML 신규) |
| `aba_routing` 체크 디지트 검증기 추가, `ROUTING_NUMBER.txt` 접두 구간 제한 | us_bank_account | validator 신규, 키워드 파일 수정 |
| `phonenumber` 자리표시자를 NANP 규칙 검증으로 교체, 패턴 첫 자리 `2`-`9` 제한 (`(?-u:\b)` 앵커 유지) | us_phonenumber | validator 수정, YAML 수정 |
| `us_medicare_beneficiary_identifier` recognizer 추가 | us_medicare_beneficiary_identifier | YAML 신규 |
| `dea` 체크 디지트 검증기와 `us_dea_number` recognizer 추가 | us_dea_number | validator 신규, YAML 신규 |
| `us_alien_registration_number` recognizer 추가 | us_alien_registration_number | YAML 신규 |
| `vin` 체크 디지트 검증기와 recognizer 추가 (공통 이관 여부 결정 후) | us_vehicle_identification_number | validator 신규, YAML 신규 |
| (선택) SSN·ITIN·라우팅번호를 묶는 공용 숫자열 byte-scan detector | us_social_security_number, us_itin, us_bank_account | handwritten 신규. 메모리 절감 목적이며 오탐률 변화는 없다 |
