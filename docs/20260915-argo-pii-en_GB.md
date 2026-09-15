# PII 목록: en_GB (영국)

이 문서는 `tinicore/src/guardrails/config/pii_filter_config.yaml` 에 영국(en_GB) 고유 PII recognizer 가 포함되어야 하는 근거를 기록한다. 이미 YAML 에 있는 항목도 근거를 남기기 위해 포함하며, 국가에 종속되지 않는 항목(카드번호, API 키, 비밀번호, 이메일, IP 주소 등)은 다루지 않는다. 2026-09-15 현재 YAML 에 `gb_*` recognizer 는 하나도 없으므로 이 문서의 모든 항목은 신규이다. `pii_type` 접두는 ISO 3166 국가 코드에 맞춰 `gb_` 를 쓴다(locale 은 en_GB).

## 0. 문서 작성 기준

각 항목은 다음 네 가지 기준으로 평가한다.

1. 적용 법령 또는 감독기관 규제상 노출되면 안 되는 PII 인가?
2. 그 PII 가 무엇이며, 노출을 막아야 하는 근거는 무엇인가?
3. 결정론적 방법(regex 또는 손으로 작성한 패턴 매칭)으로 검출할 수 있는가?
4. 검증기(체크섬 등)가 있어서 매칭 정확도를 높일 수 있는가? 검증기가 없어도 보안상 중요하면 채택한다.

### 검출 방식 세 가지 (결정론적 검출 가능성 항목에서 사용하는 용어)

엔진(`recognizer.rs` 의 `PiiEngine`)은 세 가지 매칭 방식을 지원하며, 어느 방식으로 찾은 매치든 같은 후처리 파이프라인(boundary check → validator → dedup → 점수 계산·임계값)을 거친다. 따라서 검증기와 context_words 는 방식과 무관하게 동일하게 적용된다.

| 방식 | 구현 위치 | 동작 | 적합한 경우 | 비용 |
|---|---|---|---|---|
| **regex** | `PatternRecognizer`, `PatternTemplateRecognizer` | 패턴을 30개 단위 청크(`DEFAULT_CHUNK_SIZE`)로 나눠 `regex_automata::hybrid::dfa`(lazy DFA)로 컴파일하고, 청크마다 텍스트를 한 번씩 스캔 | 패턴 수가 적고 구조가 단순할 때. 기본 선택지 | 패턴 수와 복잡도에 비례해 DFA 캐시 메모리와 스캔 횟수가 늘어난다. 카드번호는 105개 패턴이 문제가 되어 handwritten 으로 옮겼다 |
| **byte-scan handwritten** | `handwritten/card_detector.rs` 방식 (`MatchEngine` 직접 구현) | 텍스트를 바이트 단위로 걸으며 숫자열·영숫자열을 뽑고, 접두 표·길이·자리 규칙을 코드로 검사 | 접두가 고정 문자열이 아니라 **표**(BIN 처럼 여러 접두 구간)이거나, 주별 형식처럼 패턴 수가 많거나, 체크섬을 매칭 단계에서 바로 적용하고 싶을 때 | 메모리 거의 없음. 타입마다 detector 코드를 작성해야 한다 |
| **Aho-Corasick handwritten** | `handwritten/aho_corasick_detector.rs` (`pattern_desc_for` 에 anchor + verifier 등록) | 고정 문자열 anchor 를 하나의 automaton 으로 찾고, anchor 뒤의 바이트를 verifier 함수가 검사 | **고정 리터럴 접두**가 있고 그 뒤에 단순한 문자 집합 run 이 이어질 때 (`AKIA`, `ghp_`, `010` 등). 여러 타입을 한 automaton 에 묶어 텍스트를 한 번만 스캔한다 | 메모리 거의 없음. anchor 가 짧으면(1-2바이트) 텍스트 곳곳에서 verifier 가 호출되어 이득이 줄고, anchor 는 대소문자를 구분한다(`ascii_case_insensitive` 미사용) |

각 항목의 "결정론적 검출 가능성"에서는 regex 를 기본으로 표로 기술하고, 그 아래에 handwritten(byte-scan, Aho-Corasick) 대안의 실현 가능성과 **오탐률이 regex 대비 어떻게 달라지는지**를 함께 적는다. 오탐률은 매칭 형식이 같으면 방식과 무관하게 같고, handwritten 이 매칭 단계에서 표 대조나 체크섬을 추가로 수행하거나 (카드번호처럼) 구분자 제약을 의도적으로 풀 때만 달라진다.

### 점수 체계와 context_words (정확도가 낮은 패턴에 반드시 적용)

**현재 코드에서 context_words 는 매치를 걸러내지 않는다.** `compute_score` (`recognizer.rs`)는 context 단어가 매치 주변 ±50자 안에 있으면 1.0, 없으면 0.5 를 돌려주고, 임계값 `SCORE_THRESHOLD` 도 0.5 이므로 context 단어가 없어도 모든 매치가 살아남는다. 점수는 겹침 해소(`detector.rs`)에서 어느 매치를 우선할지 정하는 데에만 쓰인다. 따라서 "context_words 가 있으니 오탐을 걸러준다"는 가정은 현재 성립하지 않는다.

이 문서의 regex 표에서 **"score 사용 필요"** 로 표시한 패턴은, 형식만으로는 정확도가 낮아서 context 단어 없이 매칭되면 오탐이 될 가능성이 높은 것들이다. 이런 패턴을 채택하려면 Presidio 와 같은 방식의 점수 체계가 먼저 있어야 한다.

- `RecognizerConfig` 와 `PatternMeta` 에 recognizer 단위 `score` 필드(기본값 0.5)를 추가한다.
- `compute_score` 를 "기본 점수 + context 가산" 방식으로 바꾸고 임계값 0.5 는 유지한다. 가산값은 **0.5** 를 권장한다. 그러면 기존 recognizer 의 context 매치 점수가 지금과 같은 1.0 으로 유지되어 `tinicore/tests/guardrails/filter_test.rs` 의 `score == 1.0` 단정 3건(5331, 5441, 5471행)이 그대로 통과한다. Presidio 기본값 0.35 를 쓰면 통과·탈락 결과는 같지만 점수가 0.85 로 바뀌어 이 테스트들을 갱신해야 한다.
- 기존 recognizer 는 모두 기본값 0.5 이므로 통과·탈락 결과가 바뀌지 않는다. `card_number` 와 Aho-Corasick 계열은 Luhn 과 고정 접두가 이미 강한 필터라서 `score` 를 지정할 필요가 없다. `PatternMeta` 를 통해 같은 파이프라인을 타지만 값이 기본이라 영향이 없다.
- 낮은 `score` 를 준 recognizer 에는 `context_words` 를 반드시 채워야 한다. `compute_score` 는 `context_words` 가 비어 있으면 가산 없이 기본 점수를 돌려주므로, 비워 두면 모든 매치가 탈락한다.
- 정확도가 낮은 패턴은 같은 `pii_type` 을 가진 별도 recognizer(예: `us_driver_license_numeric`)로 분리해 `score: 0.3` 처럼 낮게 준다. context 없이는 0.3 으로 탈락하고, context 가 있으면 0.8 로 통과한다. pid 가 패턴 단위이고 `PatternMeta` 가 recognizer 설정을 패턴마다 복제하므로, 패턴별 점수보다 recognizer 분리가 스키마 변경이 적다.

context_words 는 소문자 부분 문자열 검색이므로 `car`, `tin`, `ead`, `ach`, `aba` 같은 짧은 단어는 `card`, `routing`, `read` 안에서도 걸린다. 점수 체계를 도입하면 이런 단어가 가산의 근거가 되므로, 짧은 단어는 목록에서 빼거나 앞뒤에 공백을 포함한 형태로 등록해야 한다.

### 엔진 제약 (regex 작성 시 유의)

- lazy DFA 이므로 **lookahead·lookbehind·역참조를 쓸 수 없다.** 배제 규칙(예: SSN 의 `000`, `666`, `9xx` 지역번호 제외)은 regex 가 아니라 `validator.rs` 의 검증 함수로 구현하거나, handwritten detector 안에서 코드로 처리한다.
- 현재 `validator.rs` 에 존재하는 검증기는 `luhn`, `rrn`, `phonenumber` 세 가지뿐이다. `rrn` 은 자릿수만 확인하고 `phonenumber` 는 항상 `true` 를 돌려준다. 아래 "검증기" 필드에서 "현재"는 이 세 가지 기준이고, "구현 가능"은 새로 작성해야 하는 검증 논리를 뜻한다.
- **`validator::validate` 는 fail-open 이다.** 모르는 검증기 이름이 오면 `true` 를 돌려준다. 따라서 YAML 에 `ssn`, `aba_routing` 같은 이름을 먼저 적고 함수를 나중에 구현하면 경고 없이 모든 매치가 통과한다. 반드시 **검증기 구현 → YAML 등록** 순서로 작업한다.
- 단어 경계 처리는 `boundary_check` 와 `boundary_check_reject_before/after` 설정으로 한다. `config.rs` 의 `boundary_check_reject_before` 필드 주석은 패턴 안의 `(?-u:\b)` 대신 이 설정을 쓰도록 안내한다(DFA 상태 수 감소). handwritten detector 도 같은 설정을 따른다.
- `RecognizerConfig` 에 대소문자 무시 옵션이 없다. 소문자 입력까지 잡으려면 패턴 안에 `(?i)` 인라인 플래그를 넣거나 문자 클래스에 소문자를 포함해야 한다. 기존 `us_passport` 는 `[a-zA-Z]` 로 소문자를 허용하고, 이 문서의 운전면허 제안은 `[A-Z]` 만 쓴다. 구현 시 통일한다.

### regex 표의 형식

각 항목의 regex 는 다음 3열 표로 기술한다. 표에 실린 모든 regex 는 Python `re` 로 예시와의 매칭을 확인했다(`(?-u:\b)` 는 `\b` 로 치환, `boundary_check` 는 인접 문자 검사로 모사).

| regex | 매칭 예시 | 비고 (score 사용 필요 등) |
|---|---|---|

"비고" 열의 표기는 다음 뜻이다.
- **score 사용 필요**: 형식만으로는 정확도가 낮다. 점수 체계 도입 후 낮은 `score` 로 등록해서 context 단어가 있을 때만 통과시킨다. 신규 패턴은 점수 체계가 없는 동안 등록하지 않는다. 이미 YAML 에 있는 기존 recognizer(en_US 의 `us_passport` 등)는 예외로, 현재 상태(오탐 감수)로 유지하다가 점수 체계 도입 후 낮은 `score` 로 전환한다.
- **score 사용 고려**: 형식만으로는 정확도가 중간이다. 검증기가 있으면 기본 점수로 충분하고, 검증기가 없거나 검증기 없이 등록한다면 낮은 `score` 를 권장한다.
- **기본**: 형식 자체가 충분히 특이해서 기본 점수 0.5 로 등록해도 된다.


### 이 문서의 regex 검증 방법에 대한 보충

엔진은 DFA 를 `MatchKind::All` 로 빌드해 겹치는 모든 매치 끝을 보고한 뒤 boundary check 와 dedup 으로 가장 긴 것을 남긴다. 이 문서의 regex 는 모두 ASCII 만 쓴다. NHS 번호·UTR·IBAN·VAT 의 체크섬은 python-stdnum 2.2 의 `stdnum.gb.nhs`, `stdnum.gb.utr`, `stdnum.gb.vat`, `stdnum.iban` 구현과 대조했다. 운전면허번호는 stdnum 에 구현이 없어 DVLA 가 공개한 구조 규칙으로 자체 검증했다.

## 1. 적용 법령 및 감독기관

영국은 EU 탈퇴 후에도 GDPR 을 국내법으로 계승한 UK GDPR 과 Data Protection Act 2018(DPA 2018)이 개인정보 보호의 기본 법제이고, 2025년 Data (Use and Access) Act 가 일부를 개정했다. 감독기관은 ICO(Information Commissioner's Office) 단일 기관이다. 영국 법제의 특징은 **단일 국가 신분증이 없고 목적별 번호가 분리**되어 있다는 점이다. 국민보험번호(NINO)는 세금·복지, NHS 번호는 의료, UTR 은 세무 신고, 운전면허번호는 DVLA 로 각각 관리되며, 어느 하나도 법정 범용 식별자가 아니다. 따라서 이 문서는 GDPR 제87조식 "국가 식별번호" 대신, 각 번호를 관리하는 개별법의 비밀 유지 조항과 ICO 의 해석을 근거로 삼는다.

| 법령 | 감독기관 | 적용 범위 요약 |
|---|---|---|
| UK GDPR (retained Regulation (EU) 2016/679) 제4조, 제9조, 제32조 | ICO (Information Commissioner's Office) | 개인정보 정의, 특수 범주(건강 등), 처리 보안 |
| Data Protection Act 2018 제10조, Schedule 1; Data (Use and Access) Act 2025 | ICO | 특수 범주 처리 조건, UK GDPR 보완·개정 |
| Social Security Administration Act 1992 제1조; Social Security (Crediting and Treatment of Contributions, and National Insurance Numbers) Regulations 2001 (SI 2001/769) | HMRC, DWP | 국민보험번호(NINO)의 부여와 이용 |
| Commissioners for Revenue and Customs Act 2005 제18조; Taxes Management Act 1970 | HMRC | HMRC 보유 정보의 비밀 유지 (NINO, UTR 포함) |
| NHS Act 2006 제251조; Health and Social Care Act 2012; Caldicott 원칙 | NHS England, ICO | 환자 식별 정보(NHS 번호 포함)의 처리 조건(제251조는 동의 없는 처리를 예외적으로 허용하는 관문 조항이며, 비밀 유지의 일반 원칙은 보통법상 confidentiality 와 Caldicott 원칙) |
| Identity Documents Act 2010 | Home Office (HM Passport Office) | 여권 등 신분 서류의 위조·부정 사용 처벌 |
| Road Traffic Act 1988 제97조; Road Vehicles (Registration and Licensing) Regulations 2002 제27조; Vehicle Excise and Registration Act 1994 제22조–제23조 | DVLA | 운전면허 발급, 차량 등록 정보 공개 조건, 차량 등록부(제22조)와 등록 번호판 부여(제23조) |
| Privacy and Electronic Communications Regulations 2003 (PECR) 제19조–제22조; Communications Act 2003 | ICO, Ofcom | 동의 없는 마케팅 전화·문자 금지, 통신 가입자 정보 |
| Payment Services Regulations 2017; Money Laundering Regulations 2017 | FCA | 계좌 식별자(sort code·계좌번호·IBAN) 취급 |
| Fraud Act 2006 | 검찰 (CPS) | 신원 사기 처벌 (감독기관 없음) |
| Companies Act 2006; Value Added Tax Act 1994 | Companies House, HMRC | 회사 번호·VAT 번호는 공개 사업자 번호 |

## 2. 요약 표

| pii_type | 설명 | 결정론적 검출 | 권장 검출 방식 | 검증기 (현재 / 구현 가능) | score | 기존 구현 | 채택 |
|---|---|---|---|---|---|---|---|
| gb_national_insurance_number | 국민보험번호 (NINO, `AB 12 34 56 C`) | 가능 (형식 엄격) | regex | 없음 / 미배정 접두 7종 배제 (선택, `gb_nino`) | 기본 | 신규 | 채택 |
| gb_nhs_number | NHS 번호 (10자리, `943 476 5919`) | 가능 | regex (+ `gb_nhs` 검증기) | 없음 / 가중합 mod 11 | 사용 고려 | 신규 | 채택 |
| gb_utr | 납세자 고유 번호 (UTR, 10자리) | 가능 | regex (+ `gb_utr` 검증기) | 없음 / 가중합 mod 11 (첫 자리가 체크) | 사용 고려 | 신규 | 채택 |
| gb_driver_license | 운전면허번호 (DVLA, 16자리) | 가능 (형식 엄격) | regex (+ `gb_dvla` 구조 검증기) | 없음 / 생년월일 구조 검증 | 기본 | 신규 | 채택 |
| gb_passport | 여권번호 (9자리 숫자) | 가능 (약함) | regex (+ `mrz_731`, 체크 디지트 동반 시) | 없음 / MRZ 7-3-1 (10자리 표기에만) | **사용 필요** | 신규 | 채택 (점수 체계 도입이 선행 조건) |
| gb_iban | 영국 IBAN / sort code + 계좌번호 | 가능 | regex 또는 Aho-Corasick (+ `iban` 검증기) | 없음 / ISO 7064 mod 97-10. sort code·계좌 modulus 검사는 VocaLink 가중치 표 필요 | 기본 (IBAN) / 사용 고려 (sort code + 계좌) | 신규 | 조건부 채택 (공통 항목 `iban` 으로 이관 검토, sort code 표기는 영국 고유) |
| gb_phonenumber (recognizer `gb_phonenumber`) | 휴대전화번호 (`07XXX XXXXXX`) | 가능 | regex 또는 Aho-Corasick (anchor `+44`) | 없음 / 없음 | 사용 고려 | 신규 | 채택 |
| gb_phonenumber (recognizer `gb_phonenumber_landline`) | 유선전화번호 (`01`/`02`) | 가능 (약함) | regex | 없음 / 지역번호 표 | **사용 필요** | 신규 | 채택 (점수 체계 도입이 선행 조건) |
| gb_vehicle_plate | 차량 등록 번호판 (`AB12 CDE`) | 가능 | regex | 없음 / 연령 숫자 구간 검증 (이득 작음) | 기본 | 신규 | 채택 |
| gb_postcode | 우편번호 (`SW1A 1AA`) | 가능 | regex | 없음 / 없음 | 사용 고려 | 신규 | 조건부 채택 (주소 마스킹 정책 결정 후) |
| gb_vat | VAT 등록번호 (9자리) | 가능 | regex (+ `gb_vat` 검증기) | 없음 / mod 97 및 9755 변형 | 사용 고려 / 기본 (`GB` 접두) | 신규 | 미채택 |

이외에 검토했으나 결정론적 검출이 불가능하거나 공개 번호라서 미채택한 항목은 4절에 정리했다.

## 3. 항목별 상세

### gb_national_insurance_number

- **설명**: National Insurance number (NINO). HMRC·DWP 가 16세 전후에 부여하는 번호로 `대문자 2 + 숫자 6 + 대문자 1(접미 `A`-`D`)` 의 9자리이며 `AB 12 34 56 C` 처럼 띄어 쓴다. 접두 문자에는 규칙이 있다. 첫 문자에 `D`, `F`, `I`, `Q`, `U`, `V` 를 쓰지 않고, 둘째 문자에 `D`, `F`, `I`, `O`, `Q`, `U`, `V` 를 쓰지 않으며, `BG`, `GB`, `NK`, `KN`, `TN`, `NT`, `ZZ` 조합은 배정하지 않는다. 체크섬은 없다. 급여명세서·세금 서류·복지 신청서에 기재된다.
  - 예시: `AB 12 34 56 C`, `AB123456C`, `AB 12 34 56 A` (형식 예시). HMRC 가 안내 자료에 쓰는 `QQ 12 34 56 C` 는 `Q` 접두가 발급 대상이 아니라서 아래 regex 가 의도적으로 거부한다.
- **법적 근거**:
  - 법령: Social Security Administration Act 1992 제1조, Commissioners for Revenue and Customs Act 2005 제18조 (HMRC 비밀 유지), UK GDPR 제4조. ICO 는 NINO 를 "개인을 직접 식별하는 데이터"로 다룬다.
  - 감독기관: HMRC, DWP, ICO
  - 노출 금지 이유: 영국에서 범용 신분증이 없는 탓에 NINO 가 사실상의 신원 확인 키로 쓰인다. NINO + 이름 + 생년월일 조합으로 세금 환급·복지 급여 사기와 고용 사기가 가능하다.
- **결정론적 검출 가능성**: 가능하며 형식이 엄격하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z] ?[0-9]{2} ?[0-9]{2} ?[0-9]{2} ?[A-D]` | `AB 12 34 56 C`, `AB123456C`, `AB 12 34 56 A` (`QQ 12 34 56 C`, `DA123456C`, `AO123456C`, 접미 `E`, 5자리는 거부) | 기본. 접두 문자 집합과 접미 `A`-`D` 제한, 9자리 고정 구조로 오탐이 낮다. 배정되지 않은 조합(`BG`, `GB`, `NK`, `KN`, `TN`, `NT`, `ZZ`)은 lookahead 없이 표현하기 번거로워 검증기로 넘긴다. `boundary_check: true` 적용 |

    오탐: 낮다. 소문자 입력은 `(?i)` 로 잡는다.
  - **byte-scan handwritten**: 가능하나 단일 패턴이라 이점이 없다.
  - **Aho-Corasick**: 부적합. 접두가 열려 있다.
  - **권장**: regex. 미배정 접두 조합 배제는 선택적으로 검증기 `gb_nino` 에 둔다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 미배정 접두 조합 7종 배제만 가능하다.
- **채택 여부 및 근거**: 채택. 영국의 사실상 범용 식별자이며 형식이 엄격하다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `national insurance`, `national insurance number`, `nino`, `ni number`, `ni no`, `hmrc`, `dwp`, `payslip`, `p60`, `p45`

### gb_nhs_number

- **설명**: NHS number. 잉글랜드·웨일스·맨섬의 모든 환자에게 부여되는 10자리 번호로 `943 476 5919` 처럼 3-3-4 로 띄어 쓴다. 마지막 자리는 앞 9자리에 가중치 `10 9 8 7 6 5 4 3 2` 를 곱해 합한 값을 11 로 나눈 나머지 r 에 대해 `11 - r`(11 이면 0, 10 이면 무효)로 계산한 체크 디지트이다. 스코틀랜드는 CHI 번호(10자리, `DDMMYY` + 4자리. 체크 디지트는 NHS 번호와 같은 mod 11 이지만 앞 6자리가 생년월일), 북아일랜드는 H&C 번호(10자리)를 쓰며 형식이 다르다.
  - 예시: `943 476 5919`, `9434765919` (NHS 가 테스트 자료에 쓰는 형식 예시. 체크 디지트 통과), `450 557 7104` (형식 예시. 체크 디지트 통과)
- **법적 근거**:
  - 법령: NHS Act 2006 제251조 (환자 식별 정보), Health and Social Care Act 2012, UK GDPR 제9조 (건강 데이터는 특수 범주), DPA 2018 제10조, Caldicott 원칙
  - 감독기관: NHS England, ICO
  - 노출 금지 이유: 의료 기록의 연결 키이며 건강 데이터는 특수 범주이다. NHS 번호로 GP 기록·처방·예약 시스템에 접근할 수 있다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{3} ?[0-9]{3} ?[0-9]{4}` | `943 476 5919`, `9434765919`, `450 557 7104` (9자리는 거부) | score 사용 고려. 구분자 없는 10자리는 영국 전화번호(11자리)·미국 전화번호(10자리)와 겹치므로 `gb_nhs` 검증기(1/11) 병행이 사실상 필수. 검증기 없이 등록한다면 score 사용 필요. `boundary_check: true` 적용 |

    오탐: 검증기 없이는 높고, 검증기를 붙이면 중간이다(10자리 숫자열의 약 1/11 이 통과).
  - **byte-scan handwritten**: 가능. 오탐률은 regex + `gb_nhs` 조합과 **동일**하다.
  - **Aho-Corasick**: 부적합. 고정 접두가 없다.
  - **권장**: regex + `gb_nhs` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 위 가중합 mod 11. 검증기 `gb_nhs` 로 구현한다(python-stdnum `gb.nhs` 와 동일). CHI 번호는 앞 6자리 생년월일 검사를 더한 별도 분기로 둘 수 있다.
- **채택 여부 및 근거**: 채택. 특수 범주(건강) 데이터의 연결 키이고 검증기가 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `nhs`, `nhs number`, `nhs no`, `patient`, `gp`(2글자, 제외), `hospital`, `chi number`, `health and care number`

### gb_utr

- **설명**: Unique Taxpayer Reference (UTR). HMRC 가 자진 신고(Self Assessment) 대상 개인·법인에 부여하는 10자리 번호로 `12345 67890` 처럼 5-5 로 띄어 쓴다. **첫 자리**가 체크 디지트이며, 뒤 9자리에 가중치 `6 7 8 9 10 5 4 3 2` 를 곱해 합한 값을 11 로 나눈 나머지를 `21987654321` 표에서 찾은 값이다.
  - 예시: `1123456789`, `11234 56789` (형식 예시. python-stdnum 으로 체크 디지트 확인)
- **법적 근거**:
  - 법령: Commissioners for Revenue and Customs Act 2005 제18조, Taxes Management Act 1970, UK GDPR 제4조
  - 감독기관: HMRC, ICO
  - 노출 금지 이유: HMRC 온라인 계정과 세금 환급 사기의 열쇠이다. 회계사·고용주에게 자주 전달되어 유출 경로가 넓다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{5} ?[0-9]{5}` | `11234 56789`, `1123456789` | score 사용 고려. 구분자 없는 10자리는 NHS 번호·전화번호와 겹치므로 `gb_utr` 검증기(1/11) 병행이 사실상 필수. 검증기 없이 등록한다면 score 사용 필요. NHS 번호와 같은 값이 두 검증기를 모두 통과할 확률은 약 1/121 이다. `boundary_check: true` 적용 |

    오탐: 검증기 없이는 높고, 검증기를 붙이면 중간이다.
  - **byte-scan handwritten**: 가능. 오탐률은 regex + `gb_utr` 조합과 **동일**하다.
  - **Aho-Corasick**: 부적합.
  - **권장**: regex + `gb_utr` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 위 가중합 규칙. 검증기 `gb_utr` 로 구현한다(python-stdnum `gb.utr` 과 동일).
- **채택 여부 및 근거**: 채택. HMRC 비밀 유지 대상이고 검증기가 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `utr`, `unique taxpayer reference`, `taxpayer reference`, `self assessment`, `hmrc`, `tax return`

### gb_driver_license

- **설명**: DVLA 운전면허번호(잉글랜드·스코틀랜드·웨일스). 16자리 영숫자로 개인정보가 인코딩되어 있다. 자리 1-5 는 성(姓)의 앞 5자(짧으면 `9` 로 채움), 자리 6 은 출생 연도의 십의 자리, 자리 7-8 은 출생 월(여성은 +50), 자리 9-10 은 출생 일, 자리 11 은 출생 연도의 일의 자리, 자리 12-13 은 이름·중간 이름 이니셜(없으면 `9`), 자리 14 는 임의 숫자(보통 `9`), 자리 15-16 은 체크 문자 2자(알고리즘 비공개. 문자 집합이 `[A-Z]` 인지 `[A-Z0-9]` 인지 DVLA 명세 확인 필요)이다. 카드에는 뒤에 발급 회차 2자리가 더 붙는다(`MORGA753116SM9IJ 35`). 북아일랜드 면허는 8자리 숫자로 별개이다.
  - 예시: `MORGA753116SM9IJ` (DVLA 견본 면허증의 가상 인물 번호. 1976년 3월 11일생 여성 Sarah Meredyth Morgan. 자리 6 `7` 과 자리 11 `6` 이 연도 `76` 을 이룬다), `SMITH912045JD9AB`, `LEE99801011J99CD` (형식 예시)
- **법적 근거**:
  - 법령: Road Traffic Act 1988 제97조, Road Vehicles (Registration and Licensing) Regulations 2002 제27조 (DVLA 정보 공개 조건), UK GDPR 제4조
  - 감독기관: DVLA, ICO
  - 노출 금지 이유: 성·생년월일·성별·이니셜이 번호 안에 그대로 들어 있어 번호 자체가 개인정보를 드러낸다. 영국에서 운전면허증은 가장 흔한 사진 신분증이라 계약·대여·연령 확인에 널리 쓰인다.
- **결정론적 검출 가능성**: 가능하며 형식이 엄격하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z9]{5}[0-9](0[1-9]\|1[0-2]\|5[1-9]\|6[0-2])(0[1-9]\|[12][0-9]\|3[01])[0-9][A-Z9]{2}[0-9][A-Z]{2}` | `MORGA753116SM9IJ`, `SMITH912045JD9AB`, `LEE99801011J99CD` (`MORGA713116SM9IJ`(월 13), 15자리는 거부) | 기본. 16자리 안에서 문자·숫자 위치와 월(`01`-`12`, `51`-`62`)·일 범위가 고정되어 우연히 맞기 어렵다. `boundary_check: true` 적용 |

    오탐: 낮다.
  - **byte-scan handwritten**: 가능. 오탐률은 regex 와 **동일**하다. 단일 패턴이라 이점이 없다.
  - **Aho-Corasick**: 부적합. 접두가 성이라 열려 있다.
  - **권장**: regex. 월별 일수 검사는 `gb_dvla` 검증기로 둘 수 있다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크 문자 2자의 알고리즘은 공개되어 있지 않다. 생년월일 구조 검증(월·일 범위, 월별 일수)만 가능하며 대부분 regex 에 포함된다.
- **채택 여부 및 근거**: 채택. 번호 자체가 생년월일·성별을 드러내고 형식이 엄격해 오탐이 낮다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `driving licence`, `driving license`, `driver's licence`, `dvla`, `licence number`, `driver number`, `photocard`

### gb_passport

- **설명**: 영국 여권번호. 9자리 숫자이다(예: `123456789`). 번호 자체에 체크섬은 없고 MRZ 에 7-3-1 체크 디지트가 붙는다.
  - 예시: `123456789` (형식 예시)
- **법적 근거**:
  - 법령: Identity Documents Act 2010, UK GDPR 제4조
  - 감독기관: HM Passport Office, ICO
  - 노출 금지 이유: 정부 발급 신분증 번호로서 항공·호텔·은행 KYC·고용 자격 확인(right to work)에 쓰인다.
- **결정론적 검출 가능성**: 가능하나 정밀도가 낮다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{9}[0-9]?` | `123456789` | **score 사용 필요**. 9자리 숫자열은 미국 여권·SSN·라우팅번호·NY 운전면허와 동일 형식이다. 선택 꼬리는 MRZ 체크 디지트 표기용이며 10자리 매치에만 `mrz_731` 적용. 점수 체계 도입 전에는 등록하지 않는다. `boundary_check: true` 적용 |

    오탐: 높다.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합.
  - **권장**: 점수 체계 도입 후 낮은 `score` 로 등록.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 번호 자체에는 없다. MRZ 체크 디지트 동반 시 `mrz_731`(de_DE 문서).
- **채택 여부 및 근거**: 채택하되 점수 체계 도입이 선행 조건이다. 정부 발급 신분증 번호이지만 9자리 숫자열이라 context 단어 없이는 오탐을 제어할 수 없다.
- **비고**: 기존 `us_passport` 패턴 `([a-zA-Z]\d{8}|[0-9]{9})` 가 이미 모든 9자리 숫자를 input·output·default 계층에서 잡고 있으므로, `gb_passport` 를 보류해도 검출 공백은 없고 `pii_type` 표기만 `us_passport` 로 나온다. 또한 10자리 형태 `[0-9]{9}[0-9]?` 는 `gb_nhs_number`·`gb_utr` 와 span 이 같아 세 recognizer 가 동시에 매치될 수 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `passport`, `passport number`, `passport no`, `hm passport office`, `travel document`

### gb_iban

- **설명**: 영국 IBAN 과 국내 계좌 표기. IBAN 은 `GB` + 키 2자리 + 은행 코드 4자(BIC 앞 4자, 대문자) + sort code 6자리 + 계좌번호 8자리 = 22자리이다. 국내에서는 IBAN 보다 `sort code 12-34-56 + 계좌번호 12345678` 표기가 훨씬 흔하다. sort code·계좌번호에는 은행별 modulus 10/11 검사가 있으나 VocaLink 가 배포하는 가중치 표(수백 행)가 필요하다.
  - 예시: `GB29NWBK60161331926819`, `GB29 NWBK 6016 1331 9268 19` (IBAN 표준 견본. mod 97 통과), sort code + 계좌 `60-16-13 31926819`, `12-34-56 12345678`
- **법적 근거**:
  - 법령: Payment Services Regulations 2017, Money Laundering Regulations 2017, UK GDPR 제4조
  - 감독기관: FCA, ICO
  - 노출 금지 이유: sort code + 계좌번호만으로 Direct Debit 설정과 계좌 이체 사기(APP fraud)가 가능하다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `GB[0-9]{2} ?[A-Z]{4} ?[0-9]{4} ?[0-9]{4} ?[0-9]{4} ?[0-9]{2}` | `GB29NWBK60161331926819`, `GB29 NWBK 6016 1331 9268 19` (21자리, `DE89…` 은 거부) | 기본. `GB` 접두 + 은행 코드 4자 + 22자리 + `iban` 검증기. 마지막 그룹을 고정해 뒤따르는 공백이 매치에 들어가지 않게 했다. `boundary_check: true` 적용 |
    | `[0-9]{2}[- ]?[0-9]{2}[- ]?[0-9]{2} ?[0-9]{8}` (sort code + 계좌번호) | `60-16-13 31926819`, `60 16 13 31926819`, `601613 31926819`, `12-34-56 12345678` | score 사용 고려. `2-2-2` + 8자리 구조는 하이픈 표기에서는 비교적 특이하지만, 공백·무구분 표기를 허용하면 14자리 숫자열과 겹치고 검증기 없이는 날짜(`12-34-56`)와 숫자열 조합에도 걸린다 |

    오탐: IBAN 은 낮고, sort code 표기는 중간이다.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 공통 IBAN detector 로 확장하면 적합(de_DE 문서 참조). `GB` 를 국가 코드 anchor 목록에 등록한다.
  - **권장**: 공통 `iban` recognizer + `iban` 검증기. sort code + 계좌번호 표기는 영국 고유로 유지한다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: `iban`(ISO 7064 mod 97-10, de_DE 문서와 동일). sort code·계좌번호 modulus 검사는 VocaLink 가중치 표를 내장해야 하므로 비용 대비 효과를 검토한 뒤 결정한다.
- **채택 여부 및 근거**: 조건부 채택. IBAN 부분은 공통 항목으로 이관하고, sort code + 계좌번호 표기는 영국 고유로 유지한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `sort code`, `account number`, `iban`, `bank account`, `direct debit`, `bacs`, `faster payments`, `account no`

### gb_phonenumber

- **설명**: 영국 전화번호. 국가번호 `+44`, 국내 접두 `0`. 휴대전화는 `07` 로 시작하는 11자리(`07XXX XXXXXX`)이고, 유선은 `01`(지역, 지역번호 3-6자리)·`02`(대도시, `020` 런던, `023`·`024`·`028`·`029`) 로 시작하는 10-11자리이다. `03` 은 비지리 번호, `08`·`09` 는 특수 요금 번호이다. Ofcom 은 `07700 900000`-`900999` 를 영화·문서용으로 예약해 두었다.
  - 예시: 휴대전화 `07700 900123`, `+44 7700 900123`, `07700900123`, `+447700900123`, `07700-900123`. 유선 `020 7946 0958`, `+44 20 7946 0958`, `023 8022 2222`, `028 9012 3456`, `01632 960123`, `0161 496 0123`, `02079460958`. 대부분 Ofcom 예약 대역의 형식 예시이다.
- **법적 근거**:
  - 법령: PECR 2003 제19조–제22조 (동의 없는 마케팅 전화·문자 금지), Communications Act 2003, UK GDPR 제4조
  - 감독기관: ICO (PECR), Ofcom
  - 노출 금지 이유: 휴대전화번호는 2단계 인증·은행 앱 인증의 열쇠이고, ICO 는 PECR 위반 텔레마케팅에 고액 과징금을 부과해 왔다.
- **결정론적 검출 가능성**: 휴대전화는 가능, 유선은 가능하나 약하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `(\+44 ?7\|07)[0-9]{3}[ -]?[0-9]{3}[ -]?[0-9]{3}` | `07700 900123`, `07700 900 123`, `+44 7700 900123`, `07700900123`, `+447700900123`, `07700-900123` (`0800 900123`, 10자리는 거부. `+44 (0)7700 900123` 괄호 표기는 잡지 못함) | score 사용 고려. `07` 접두와 11자리 고정 길이가 필터이지만, 구분자 없는 11자리 숫자열은 다른 번호와 겹칠 수 있다. `boundary_check: true` 적용 |
    | `(\+44 ?\|0)(2[03489][ -]?[0-9]{4}[ -]?[0-9]{4}\|1[0-9]{2,3}[ -]?[0-9]{3,4}[ -]?[0-9]{3,4})` | `020 7946 0958`, `+44 20 7946 0958`, `023 8022 2222`, `028 9012 3456`, `01632 960123`, `0161 496 0123`, `02079460958` (`020 7946 095`, `07700 900123` 은 거부) | **score 사용 필요**. `01`/`02` + 8-9자리는 다른 숫자열과 광범위하게 겹치고, 지역번호 길이가 3-5자리로 가변이라 구분자 위치로도 걸러지지 않는다. `01` 분기는 총 10-13자리를 허용한다(실제 번호는 최대 11자리. 6자리 지역번호 `013873` 등도 있어 정확히 좁히려면 지역번호 표가 필요). 지역번호 표(약 600개)를 넣으면 좁아진다 |

    오탐: 휴대전화는 중간, 유선은 높다.
  - **byte-scan handwritten**: 가능. 유선번호는 지역번호 표를 코드 표로 두면 DFA 비대화를 피한다.
  - **Aho-Corasick**: 휴대전화에 부분적으로 적합. `+44`(3바이트)는 anchor 로 좋고, 국내 표기 `07` 은 2바이트라 흔하지만 `kr_phonenumber` 의 `010` 과 비슷한 역할을 한다(`07` 뒤에 숫자 9자리가 이어지는지 verifier 가 검사). 기존 automaton 에 추가할 수 있다.
  - **권장**: 휴대전화는 regex(또는 Aho-Corasick), 유선은 점수 체계 도입 후 낮은 `score` 의 별도 recognizer(`gb_phonenumber_landline`).
- **검증기**:
  - 현재: 없음
  - 구현 가능: 휴대전화는 `07` 접두 외 규칙 없음(`070` 개인 번호, `076` 호출기 제외 가능). 유선은 Ofcom 지역번호 표(최신 공고로 재확인 필요).
- **채택 여부 및 근거**: 휴대전화는 채택. 유선은 채택하되 점수 체계 도입이 선행 조건이며 그 전에는 등록하지 않는다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `phone`, `telephone`, `mobile`, `mobile number`, `tel`(3글자, 제외), `call`, `text`, `contact number`, `landline`, `whatsapp`

### gb_vehicle_plate

- **설명**: 차량 등록 번호판(registration mark). 2001년 9월 이후 형식은 `지역 문자 2 + 연령 숫자 2 + 공백 + 임의 문자 3`(`AB12 CDE`)이며, 문자에서 `I` 와 `Q` 를 쓰지 않고 지역 문자 자리에는 `Z` 도 쓰지 않는다. 1983-2001년의 접두 형식(`A123 BCD`)과 그 이전의 접미 형식(`ABC 123D`)도 도로에 남아 있다. 번호판은 차량 평생 불변이 아니며(개인화 번호판 이전 가능) DVLA 등록부에서 등록 보유자(keeper)와 연결된다.
  - 예시: `AB12 CDE`, `AB12CDE`, `LM70 XYZ` (형식 예시)
- **법적 근거**:
  - 법령: Vehicle Excise and Registration Act 1994 제22조–제23조 (등록부, 번호판 부여), Road Vehicles (Registration and Licensing) Regulations 2002 제27조 (DVLA 보유자 정보 공개 조건), UK GDPR 제4조. ICO 는 번호판을 보유자와 결합 가능한 개인정보로 본다(ANPR·주차 관리 지침).
  - 감독기관: DVLA, ICO
  - 노출 금지 이유: DVLA 에서 번호판으로 보유자 정보를 조회할 수 있고(정당한 사유 요건 하에), ANPR·주차 기록과 결합하면 위치 추적이 가능하다. 공개 노출되는 번호라 단독 위험도는 낮다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-HJ-PR-Y]{2}[0-9]{2} ?[A-HJ-PR-Z]{3}` | `AB12 CDE`, `AB12CDE`, `LM70 XYZ` (`AI12 CDE`(I 포함), `AB1 CDE`, `AB12 CDI` 는 거부) | 기본. `2+2+3` 구조와 문자 집합 제한으로 오탐이 낮다. 공백 없는 7자리 영숫자 `AB12CDE` 는 제품 코드와 겹칠 수 있으나 문자·숫자 위치가 고정되어 드물다. 접두·접미 구형 형식은 별도 패턴이 필요하며 오탐이 높아 이 문서에서는 다루지 않는다. `boundary_check: true` 적용 |

    오탐: 낮다.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합. 고정 접두가 없다.
  - **권장**: regex.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 문자 집합은 regex 에 포함된다. 연령 숫자(`02`-`50` 은 3-8월, `51`-`99` 는 9-2월 등록. `00`·`01` 은 발급된 적이 없으나 regex 는 허용)로 구간 검증이 가능하나 이득이 작다.
- **채택 여부 및 근거**: 채택. 오탐이 낮고 ICO 가 개인정보로 본다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `registration`, `reg number`, `number plate`, `registration number`, `vehicle`, `car`(3글자, 제외), `dvla`, `licence plate`, `license plate`

### gb_postcode

- **설명**: 영국 우편번호. `outward code(지역 1-2자 + 숫자 1 + 선택 문자·숫자 1) + 공백 + inward code(숫자 1 + 문자 2)` 구조로 `SW1A 1AA`, `M1 1AE`, `DN55 1PT` 처럼 형식이 다양하지만 regex 로 잘 잡힌다. 하나의 우편번호가 평균 15가구를 가리키므로, 다른 국가의 우편번호와 달리 우편번호 + 건물 번호만으로 주소가 특정된다.
  - 예시: `SW1A 1AA`, `M1 1AE`, `B33 8TH`, `CR2 6XH`, `DN55 1PT`, `EC1A1BB` (형식 예시. 대부분 Royal Mail 이 형식 설명에 쓰는 값)
- **법적 근거**:
  - 법령: UK GDPR 제4조. ICO 는 우편번호 단독은 개인정보가 아닐 수 있으나 다른 정보와 결합하면 개인정보라고 해석한다.
  - 감독기관: ICO
  - 노출 금지 이유: 우편번호가 곧 거리 단위 위치이므로 이름과 결합하면 거주지가 특정된다. 단독 노출의 위험도는 낮다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}` | `SW1A 1AA`, `M1 1AE`, `B33 8TH`, `CR2 6XH`, `DN55 1PT`, `EC1A1BB` (`SW1A 1A`, `1AA SW1` 은 거부) | score 사용 고려. 형식은 특이하지만 `AB1 2CD` 같은 제품 코드·좌표 표기와 겹칠 수 있고, 공백 없는 `EC1A1BB` 는 더 자주 겹친다. `boundary_check: true` 적용 |

    오탐: 중간.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합.
  - **권장**: 주소 마스킹 정책이 정해지면 regex 로 등록. 주소를 마스킹하지 않기로 하면 등록하지 않는다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. outward code 의 지역 문자 목록(약 120개)으로 좁힐 수 있다.
- **채택 여부 및 근거**: 조건부 채택. 다른 국가 문서에서 우편번호를 미채택한 것과 달리 영국 우편번호는 형식이 특이하고 위치 특정력이 높다. 다만 주소 자체는 공통 항목·NER 로 다루기로 했으므로, 우편번호만 따로 마스킹할지는 주소 마스킹 정책과 함께 결정한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `postcode`, `post code`, `address`, `postal address`, `delivery address`

### gb_vat

- **설명**: VAT 등록번호. 표준 형식은 9자리 숫자(`GB 123 4567 89`)이며 마지막 2자리가 체크 디지트이다(앞 7자리 가중합 mod 97, 또는 2009-2010년경 이후 신규 등록분에 적용되는 9755 가산 변형. python-stdnum `gb.vat` 는 두 변형을 모두 허용한다. 도입 시점은 확인 필요). 12자리(지점 3자리 추가), `GD`·`HA` + 3자리(정부 부처·보건 당국) 변형이 있다.
  - 예시: `123456782`, `GB 123 4567 82` (형식 예시. python-stdnum 으로 체크 디지트 확인)
- **법적 근거**:
  - 법령: Value Added Tax Act 1994. HMRC 의 VAT 번호 조회 서비스에서 **공개** 확인되고 송장에 기재가 의무이다.
  - 감독기관: HMRC
  - 노출 금지 이유: 약하다. 공개 사업자 번호이다. 개인사업자(sole trader)의 VAT 번호는 이름과 함께 공개된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `GB ?[0-9]{3} ?[0-9]{4} ?[0-9]{2}` | `GB 123 4567 82`, `GB123456782` | 기본에 가깝다. `GB` 접두가 필터. 미채택 항목 |
    | `[0-9]{3} ?[0-9]{4} ?[0-9]{2}` | `123 4567 82`, `123456782` | score 사용 고려. 9자리 숫자열. `gb_vat` 검증기(약 1/97)로 좁힐 수 있다. 미채택 항목 |

  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: `GB` 접두 형태는 공통 IBAN detector 와 anchor 를 공유할 수 있으나 미채택이라 검토만 한다.
  - **권장**: 미채택.
- **검증기**:
  - 현재: 없음
  - 구현 가능: mod 97 / 9755 변형(python-stdnum `gb.vat` 과 동일).
- **채택 여부 및 근거**: 미채택. 공개 사업자 번호이다.
- **기존 구현 여부**: 신규 (미채택이므로 구현하지 않음)
- **context_words 후보** (재검토 시 참고): `vat`, `vat number`, `vat registration`, `vat reg no`

## 4. 검토 후 미채택한 항목

아래 항목은 법령상 PII 이거나 식별번호이지만 결정론적 검출이 불가능하거나 공개 번호라서 recognizer 로 등록하지 않는다.

| 항목 | 법적 근거 | 미채택 이유 |
|---|---|---|
| Company registration number (Companies House, 8자리) | Companies Act 2006 | 공개 등기 번호이다. |
| 북아일랜드 운전면허번호 (8자리 숫자) | Road Traffic (Northern Ireland) Order 1981 | 8자리 숫자만으로 구분 불가하다. 대상 인구가 적다. |
| CHI 번호 (스코틀랜드), H&C 번호 (북아일랜드) | NHS (Scotland) Act 1978 등 | NHS 번호와 같은 10자리이지만 형식이 달라 `gb_nhs_number` 검증기를 그대로 쓸 수 없다. CHI 는 앞 6자리 생년월일 검사를 더한 분기로 `gb_nhs_number` 에 흡수할 수 있으므로 별도 항목을 두지 않는다. |
| Biometric Residence Permit 번호 (`ZU1234567` 등) | UK Borders Act 2007 제5조–제15조; Immigration (Biometric Registration) Regulations 2008 | 형식 명세를 확인하지 못했고, 2024년 말 eVisa 로 대체되어 신규 발급이 없다. 이민 신분 노출 위험은 인정한다. |
| Tax code (`1257L`) | Income Tax (PAYE) Regulations 2003 | 개인 식별자가 아니라 공제 코드이다. |
| UPN (Unique Pupil Number, 13자리) | Education Act 1996 제537A조; Education (Pupil Information) (England) Regulations 2005 | 학생 식별자이나 교육 시스템 내부용이라 일반 텍스트에 나타나지 않는다. 필요 시 python-stdnum `gb.upn` 의 체크 문자 검증을 쓸 수 있다. |
| 주소, 이름, 생년월일 | UK GDPR 제4조 | 국가 종속 항목이 아니며 regex 로 결정론적 검출이 불가능하다. 공통 항목 또는 NER 로 다룬다(우편번호는 `gb_postcode` 참조). |
| 생체정보, 건강 상태, 종교·노조 가입 | UK GDPR 제9조, DPA 2018 제10조 | 특수 범주이지만 번호 형태로 나타나지 않는다. |
| 신용카드번호, 이메일, IP 주소 | UK GDPR, PCI DSS | 국가 종속 항목이 아니므로 이 문서 범위 밖이다. 기존 `card_number` 등이 담당한다. |

## 5. 구현 시 후속 작업 요약

이 문서에서 도출된, YAML·`validator.rs`·`handwritten/`·엔진에 반영할 작업 목록이다. 검증기는 **함수 구현 → YAML 등록** 순서를 지킨다(`validator::validate` 가 fail-open 이므로 순서가 바뀌면 검증 없이 통과한다).

| 순서 | 작업 | 대상 | 종류 |
|---|---|---|---|
| 선행 | recognizer 단위 `score` 필드와 context 가산 방식 도입 (en_US 문서 5절과 공통. 이미 완료되었으면 이 행 삭제) | 엔진 | 엔진 변경 |
| 1 | `gb_national_insurance_number` recognizer 추가. 미배정 접두 배제는 선택적 `gb_nino` 검증기 | gb_national_insurance_number | YAML 신규 (validator 선택) |
| 2 | `gb_nhs` 검증기(가중합 mod 11)와 `gb_nhs_number` recognizer 추가. CHI 분기는 선택 | gb_nhs_number | validator 신규, YAML 신규 |
| 3 | `gb_utr` 검증기(첫 자리 체크)와 `gb_utr` recognizer 추가 | gb_utr | validator 신규, YAML 신규 |
| 4 | `gb_driver_license` recognizer 추가 (월별 일수 검사는 선택적 `gb_dvla` 검증기) | gb_driver_license | YAML 신규 (validator 선택) |
| 5 | sort code + 계좌번호 recognizer 추가. IBAN 부분은 (공통 항목 이관 확정 시) 공통 `iban` recognizer 의 국가 길이 표에 `GB` 22 를 등록. modulus 검사는 VocaLink 표 검토 후 | gb_iban, iban (공통) | YAML 신규, 조사 |
| 6 | `gb_phonenumber` 휴대전화 recognizer 추가 (regex 또는 Aho-Corasick anchor `+44`/`07`) | gb_phonenumber | YAML 신규 또는 handwritten 수정 |
| 7 | `gb_phonenumber_landline` recognizer 추가 (`score` 낮게). **선행 작업 완료 후에만** | gb_phonenumber | YAML 신규 |
| 8 | `gb_vehicle_plate` recognizer 추가 | gb_vehicle_plate | YAML 신규 |
| 9 | `gb_passport` recognizer 추가 (`score` 낮게, `mrz_731` 검증기는 de_DE 작업과 공용). **선행 작업 완료 후에만**. 기존 `us_passport` 가 이미 모든 9자리 숫자를 잡고 있으므로 보류 중에도 검출 공백은 없다 | gb_passport | YAML 신규 |
| 10 | 주소 마스킹 정책 결정 후 `gb_postcode` 등록 여부 결정 | gb_postcode | 정책 결정 |
| 선택 | `gb_vat` recognizer 와 검증기 (개인사업자 보호 요구 시) | gb_vat | validator 신규, YAML 신규 |
