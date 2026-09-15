# PII 목록: en_IN (인도)

이 문서는 `tinicore/src/guardrails/config/pii_filter_config.yaml` 에 인도(en_IN) 고유 PII recognizer 가 포함되어야 하는 근거를 기록한다. 이미 YAML 에 있는 항목도 근거를 남기기 위해 포함하며, 국가에 종속되지 않는 항목(카드번호, API 키, 비밀번호, 이메일, IP 주소 등)은 다루지 않는다. 2026-09-15 현재 YAML 에 `in_*` recognizer 는 하나도 없으므로 이 문서의 모든 항목은 신규이다. `pii_type` 접두는 ISO 3166 국가 코드에 맞춰 `in_` 를 쓴다(locale 은 en_IN).

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

- lazy DFA 이므로 **lookahead·lookbehind·역참조를 쓸 수 없다.** 배제 규칙(예: 특정 접두·구간을 발급하지 않는 번호에서 그 값을 제외하는 규칙. en_US 의 SSN `000`·`666`·`9xx` 배제가 대표 사례)은 regex 가 아니라 `validator.rs` 의 검증 함수로 구현하거나, handwritten detector 안에서 코드로 처리한다.
- 현재 `validator.rs` 에 존재하는 검증기는 `luhn`, `rrn`, `phonenumber` 세 가지뿐이다. `rrn` 은 자릿수만 확인하고 `phonenumber` 는 항상 `true` 를 돌려준다. 아래 "검증기" 필드에서 "현재"는 이 세 가지 기준이고, "구현 가능"은 새로 작성해야 하는 검증 논리를 뜻한다.
- **`validator::validate` 는 fail-open 이다.** 모르는 검증기 이름이 오면 `true` 를 돌려준다. 따라서 YAML 에 `ssn`, `aba_routing` 같은 이름을 먼저 적고 함수를 나중에 구현하면 경고 없이 모든 매치가 통과한다. 반드시 **검증기 구현 → YAML 등록** 순서로 작업한다.
- 단어 경계 처리는 `boundary_check` 와 `boundary_check_reject_before/after` 설정으로 한다. `config.rs` 의 `boundary_check_reject_before` 필드 주석은 패턴 안의 `(?-u:\b)` 대신 이 설정을 쓰도록 안내한다(DFA 상태 수 감소). handwritten detector 도 같은 설정을 따른다.
- `RecognizerConfig` 에 대소문자 무시 옵션이 없다. 소문자 입력까지 잡으려면 패턴 안에 `(?i)` 인라인 플래그를 넣거나 문자 클래스에 소문자를 포함해야 한다. 기존 `us_passport` 는 `[a-zA-Z]` 로 소문자를 허용하고, 각 국가 문서의 신규 제안은 대문자 `[A-Z]` 만 쓰는 것을 기본으로 한다. 구현 시 통일한다.

### regex 표의 형식

각 항목의 regex 는 다음 3열 표로 기술한다. 표에 실린 모든 regex 는 Python `re` 로 예시와의 매칭을 확인했다(`(?-u:\b)` 는 `\b` 로 치환, `boundary_check` 는 인접 문자 검사로 모사).

| regex | 매칭 예시 | 비고 (score 사용 필요 등) |
|---|---|---|

"비고" 열의 표기는 다음 뜻이다.
- **score 사용 필요**: 형식만으로는 정확도가 낮다. 점수 체계 도입 후 낮은 `score` 로 등록해서 context 단어가 있을 때만 통과시킨다. 신규 패턴은 점수 체계가 없는 동안 등록하지 않는다. 이미 YAML 에 있는 기존 recognizer(en_US 의 `us_passport` 등)는 예외로, 현재 상태(오탐 감수)로 유지하다가 점수 체계 도입 후 낮은 `score` 로 전환한다.
- **score 사용 고려**: 형식만으로는 정확도가 중간이다. 검증기가 있으면 기본 점수로 충분하고, 검증기가 없거나 검증기 없이 등록한다면 낮은 `score` 를 권장한다.
- **기본**: 형식 자체가 충분히 특이해서 기본 점수 0.5 로 등록해도 된다.


### 이 문서의 regex 검증 방법에 대한 보충

엔진은 DFA 를 `MatchKind::All` 로 빌드해 겹치는 모든 매치 끝을 보고한 뒤 boundary check 와 dedup 으로 가장 긴 것을 남긴다. 이 문서의 regex 는 모두 ASCII 만 쓴다(인도 신분 번호는 모두 라틴 문자·숫자로 표기된다). Aadhaar·VID·PAN·EPIC·GSTIN 의 체크섬과 형식 규칙은 python-stdnum 2.2 의 `stdnum.in_.aadhaar`, `stdnum.in_.vid`, `stdnum.in_.pan`, `stdnum.in_.epic`, `stdnum.in_.gstin` 구현과 대조했다.

## 1. 적용 법령 및 감독기관

인도는 2023년 디지털 개인정보 보호법(Digital Personal Data Protection Act, DPDP Act)이 GDPR 형 포괄법으로 제정되었고, 2025년 시행 규칙(DPDP Rules)과 함께 단계적으로 시행 중이다. 감독기관은 Data Protection Board of India 이다. DPDP Act 시행 전까지는 정보기술법(IT Act 2000) 제43A조와 2011년 SPDI 규칙(민감 개인정보 규칙)이 적용되었으며, 비밀번호·금융정보·건강정보·생체정보를 "민감 개인정보"로 열거한다. 인도 법제의 특징은 **Aadhaar(12자리 생체 연계 식별번호)에 대한 독자 법률**이 있다는 점이다. Aadhaar Act 2016 제29조는 Aadhaar 번호의 공개·공유를 제한하고, 시행 규정과 UIDAI·MeitY 지침은 앞 8자리를 가린 "masked Aadhaar" 사용을 요구하며, 2018년 대법원 판결(Puttaswamy)이 민간의 Aadhaar 요구를 제한했다. 따라서 Aadhaar 가 이 문서의 최우선 채택 대상이고, PAN(세금 번호)·유권자 ID·여권·운전면허가 뒤를 잇는다.

| 법령 | 감독기관 | 적용 범위 요약 |
|---|---|---|
| Digital Personal Data Protection Act 2023 (DPDP Act) 제4조–제8조, 제33조; DPDP Rules 2025 | Data Protection Board of India, 전자정보기술부 (MeitY) | 개인정보 처리 원칙, 보안 조치, 유출 통지, 과징금 |
| Information Technology Act 2000 제43A조, 제72A조; IT (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules 2011 (SPDI Rules) 제3조 | MeitY, CERT-In | 민감 개인정보(비밀번호, 금융정보, 건강정보, 생체정보) 정의와 보호 의무, 유출 통지 |
| Aadhaar (Targeted Delivery of Financial and Other Subsidies, Benefits and Services) Act 2016 제29조, 제37조–제38조; Aadhaar (Sharing of Information) Regulations 2016 제6조; UIDAI·MeitY 마스킹 지침 | UIDAI (Unique Identification Authority of India) | Aadhaar 번호의 공개·공유 제한(제6조는 가림 처리를 요구하며 자릿수는 UIDAI·MeitY 지침이 앞 8자리로 정함), 무단 공개 처벌 |
| Income-tax Act 1961 제139A조, 제138조 | CBDT, 소득세국 | PAN 의 부여와 기재 의무, 납세자 정보 공개의 조건·제한 |
| Representation of the People Act 1950; ECI 지침 | Election Commission of India (ECI) | 유권자 등록과 EPIC(유권자 ID) 발급 |
| Passports Act 1967 | 외무부 (MEA), Passport Seva | 여권 발급 |
| Motor Vehicles Act 1988 제9조, 제41조; Central Motor Vehicles Rules 1989 제50조–제51조 | 도로교통부 (MoRTH), 각 주 RTO, Vahan·Sarathi 데이터베이스 | 운전면허, 차량 등록과 등록 번호판 |
| Payment and Settlement Systems Act 2007; RBI Master Direction on KYC | Reserve Bank of India (RBI) | 계좌 정보(IFSC + 계좌번호), KYC 문서(Aadhaar·PAN) 취급 |
| Telecommunications Act 2023; TRAI Telecom Commercial Communications Customer Preference Regulations 2018 (TCCCPR) | TRAI, 통신부 (DoT) | 통신 가입자 정보, 동의 없는 상업 통신 금지 (DND 등록) |
| Ayushman Bharat Digital Mission (ABDM) 정책, Health Data Management Policy | National Health Authority (NHA) | 건강 계정(ABHA) 번호와 건강 기록 |
| Central Goods and Services Tax Act 2017 제25조; Companies Act 2013 | CBIC, MCA | GSTIN·CIN 은 공개 사업자 번호 |

## 2. 요약 표

| pii_type | 설명 | 결정론적 검출 | 권장 검출 방식 | 검증기 (현재 / 구현 가능) | score | 기존 구현 | 채택 |
|---|---|---|---|---|---|---|---|
| in_aadhaar | Aadhaar 번호 (12자리) 및 VID (16자리) | 가능 | regex (+ `verhoeff` 검증기) | 없음 / Verhoeff 체크 디지트 + 회문 배제 | 사용 고려 | 신규 | 채택 |
| in_pan | 영구 계정 번호 (PAN, `ABCPD1234E`) | 가능 (형식 엄격) | regex | 없음 / 일련번호 `0000` 배제 (선택. 체크 문자 알고리즘은 비공개) | 기본 | 신규 | 채택 |
| in_voter_id | 유권자 ID (EPIC, `ABC1234566`) | 가능 | regex (+ `luhn` 검증기) | `luhn` (기존, 그대로 사용. 숫자만 걸러 계산하므로 결과적으로 뒤 7자리 Luhn) / 없음 | 사용 고려 | 신규 | 채택 |
| in_passport | 여권번호 (`A1234567`) | 가능 | regex (+ `mrz_731`, 체크 디지트 동반 시) | 없음 / MRZ 7-3-1 (9자리 표기에만) | 사용 고려 | 신규 | 채택 |
| in_driver_license | 운전면허번호 (`MH12 20110012345`) | 가능 | regex (+ `in_state_code` 검증기) | 없음 / 주 코드 표 | 사용 고려 | 신규 | 채택 |
| in_bank_account | IFSC + 계좌번호 | 가능 (조합 표기만) | regex | 없음 / IFSC 은행 코드 표 | 사용 고려 | 신규 | 조건부 채택 (IFSC 와 계좌번호가 함께 적힌 경우만) |
| in_phonenumber (recognizer `in_phonenumber`) | 휴대전화번호 (10자리, `6`-`9` 시작) | 가능 | regex | 없음 / 없음 (접두 규칙은 regex 에 포함) | 사용 고려 | 신규 | 채택 |
| in_phonenumber (recognizer `in_phonenumber_landline`) | 유선전화번호 (STD 코드 + 번호) | 가능 (약함) | regex | 없음 / STD 코드 표 | **사용 필요** | 신규 | 채택 (점수 체계 도입이 선행 조건) |
| in_vehicle_plate | 차량 등록번호 (`MH 12 AB 1234`, BH 시리즈) | 가능 | regex (+ `in_state_code` 검증기) | 없음 / 주 코드 표 | 사용 고려 / 기본 (BH 시리즈) | 신규 | 채택 |
| in_abha | 건강 계정 번호 (ABHA, 14자리) | 가능 (형식 확인 필요) | regex | 없음 / 확인 필요 | 사용 고려 | 신규 | 조건부 채택 (형식·체크섬 확인 후) |
| in_gstin | GST 등록번호 (GSTIN, 15자리) | 가능 | regex (+ `luhn` 변형 검증기) | 없음 / 36진 Luhn 변형 | 기본 | 신규 | 미채택 |

이외에 검토했으나 결정론적 검출이 불가능하거나 공개 번호라서 미채택한 항목은 4절에 정리했다.

## 3. 항목별 상세

### in_aadhaar

- **설명**: Aadhaar 번호. UIDAI 가 거주자에게 생체정보(지문·홍채)와 연계해 부여하는 12자리 번호로 `2345 6789 0124` 처럼 4-4-4 로 띄어 쓴다. 첫 자리는 `2`-`9` 이고, 마지막 자리는 Verhoeff 알고리즘 체크 디지트이며, 번호는 무작위로 생성된다(회문은 발급하지 않는다). Aadhaar 대신 인증에 쓰는 VID(Virtual ID)는 16자리이며 같은 규칙(첫 자리 `2`-`9`, Verhoeff)을 따른다. 은행 계좌·통신 가입·복지 수급·세금 신고(PAN 연계)에 사실상 필수이다.
  - 예시: `2345 6789 0124`, `234567890124`, `9876-5432-1096` (형식 예시. python-stdnum 으로 Verhoeff 체크 디지트 확인), VID `3456 7890 1234 5673`
- **법적 근거**:
  - 법령: Aadhaar Act 2016 제29조 (공개·공유 제한), 제37조–제38조 (무단 공개·접근 처벌), Aadhaar (Sharing of Information) Regulations 2016 제6조 (공개 시 가림 처리), UIDAI·MeitY 지침 (앞 8자리 마스킹), SPDI Rules 2011 제3조 (생체정보는 민감 개인정보), DPDP Act 2023, 대법원 Puttaswamy 판결 (2018년 Aadhaar 판결. 2017년 프라이버시 기본권 판결과 구분)
  - 감독기관: UIDAI, Data Protection Board of India
  - 노출 금지 이유: 생체정보와 직접 연계된 범용 식별자이며, 독자 법률이 공개를 명시적으로 제한하는 인도 번호이다(PAN 에도 CBDT 마스킹 표준이 있으나 법률 차원의 공개 제한은 Aadhaar 가 가장 강하다). Aadhaar + OTP 조합으로 계좌 개설·SIM 발급·복지 수급이 이루어지므로 유출 시 금융 사기와 신원 도용에 직결된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[2-9][0-9]{3}[ -]?[0-9]{4}[ -]?[0-9]{4}` | `2345 6789 0124`, `234567890124`, `9876-5432-1096` (`1234 5678 9012`(첫 자리 1), 11자리는 거부) | score 사용 고려. 구분자 없는 12자리 숫자열은 다른 번호와 겹치므로 `verhoeff` 검증기(1/10) 병행이 사실상 필수. 검증기 없이 등록한다면 score 사용 필요. `boundary_check: true` 적용 |
    | `[2-9][0-9]{3}([ -]?[0-9]{4}){3}` (VID) | `3456 7890 1234 5673`, `3456789012345673` | score 사용 고려. 16자리는 카드번호와 길이가 같으므로 `verhoeff` 검증기 병행이 필수이고, 카드번호는 Luhn·BIN 으로 구분된다 |

    오탐: 검증기 없이는 높고, 검증기를 붙이면 중간이다.
  - **byte-scan handwritten**: 가능. 오탐률은 regex + `verhoeff` 조합과 **동일**하다.
  - **Aho-Corasick**: 부적합. 고정 접두가 없다.
  - **권장**: regex + `verhoeff` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: Verhoeff 알고리즘(순열표·곱셈표 기반 mod 10). 검증기 `verhoeff` 로 구현하면 Aadhaar·VID 에 공통으로 쓸 수 있다. 회문 배제도 함께 둔다(python-stdnum `in_.aadhaar` 와 동일).
- **채택 여부 및 근거**: 채택. 법률이 공개를 제한하는 최고 등급 식별자이며 검증기가 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `aadhaar`, `aadhar`, `adhar`, `uidai`, `uid`(3글자, 제외), `aadhaar number`, `virtual id`, `vid`(3글자, 제외), `e-kyc`, `ekyc`
- **비고**: masked Aadhaar 표기(`XXXX XXXX 0124`)는 이 패턴에 매치되지 않으며, 이미 마스킹된 값이므로 검출할 필요가 없다.

### in_pan

- **설명**: Permanent Account Number (PAN). 소득세국이 개인·법인에 부여하는 10자리 영숫자로 `대문자 5 + 숫자 4 + 대문자 1` 구조이다. 4번째 문자는 보유자 유형(`P` 개인, `C` 회사, `H` 힌두 공동가족, `F` 조합, `A` 단체, `T` 신탁, `B`·`L`·`J`·`G` 등), 5번째 문자는 개인의 경우 성(姓)의 첫 글자, 마지막 문자는 체크 문자이나 알고리즘은 공개되어 있지 않다. 은행 계좌·주식 거래·부동산 거래·고액 현금 거래에 기재가 의무이다.
  - 예시: `ABCPD1234E` (개인 PAN 형식 예시), `AAAPL1234C` (인도 세무 안내에서 관용적으로 쓰는 형식 예시). python-stdnum 으로 형식 확인.
- **법적 근거**:
  - 법령: Income-tax Act 1961 제139A조 (PAN 기재 의무), 제138조 (납세자 정보 공개의 조건·제한), SPDI Rules 2011 (금융정보), DPDP Act 2023
  - 감독기관: CBDT, Data Protection Board of India
  - 노출 금지 이유: Aadhaar 와 연계된 금융 식별자이며 PAN + 생년월일로 소득세 포털 접근과 신용 조회가 가능하다. PAN 도용으로 타인 명의 대출·고액 거래 기록을 만드는 사기가 빈발한다.
- **결정론적 검출 가능성**: 가능하며 형식이 엄격하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{3}[ABCFGHLJPT][A-Z][0-9]{4}[A-Z]` | `ABCPD1234E`, `AAAPL1234C` (`ABCXD1234E`(유형 문자 X), 9자리, 소문자는 거부) | 기본. `5 + 4 + 1` 구조와 4번째 문자 집합이 필터라 우연히 맞기 어렵다. 유형 문자 집합은 소득세국 공식 목록 10종이며, python-stdnum 이 추가로 허용하는 `K`(폐지 추정)는 의도적으로 뺐다. `boundary_check: true` 적용 |

    오탐: 낮다. 소문자 입력은 `(?i)` 로 잡는다.
  - **byte-scan handwritten**: 가능하나 단일 패턴이라 이점이 없다.
  - **Aho-Corasick**: 부적합. 접두가 열려 있다.
  - **권장**: regex.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크 문자 알고리즘이 비공개라 구현할 수 없다. 숫자 4자리가 `0000` 이 아닌지만 검사할 수 있다(python-stdnum 과 동일).
- **채택 여부 및 근거**: 채택. 금융 식별자이며 형식이 엄격하다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `pan`(3글자이지만 인도 영어에서 `PAN card`, `PAN number` 로 흔히 쓰이므로 ` pan ` 공백 포함 형태로 등록), `pan card`, `pan number`, `permanent account number`, `income tax`, `itr`(3글자, 제외)

### in_voter_id

- **설명**: EPIC (Electors Photo Identity Card) 번호, 통칭 Voter ID. 선거관리위원회(ECI)가 18세 이상 시민에게 발급하는 10자리 영숫자로 `대문자 3 + 숫자 7` 구조이며, 뒤 7자리는 Luhn 체크섬을 따른다. 앞 3자는 발급 선거구 계열 코드이다. 신분증으로 널리 쓰인다.
  - 예시: `ABC1234566`, `XYZ9876541` (형식 예시. python-stdnum 으로 Luhn 확인)
- **법적 근거**:
  - 법령: Representation of the People Act 1950, ECI 의 EPIC 지침, DPDP Act 2023. 선거인 명부는 공개되며 텍스트 명부에는 EPIC 번호가 실리기도 하지만, 사진 명부의 공개는 ECI 가 제한한다(EPIC 번호 공개 범위는 확인 필요).
  - 감독기관: ECI, Data Protection Board of India
  - 노출 금지 이유: 사진 신분증으로서 SIM 발급·은행 KYC 에 쓰인다. 선거인 명부와 결합하면 이름·주소·나이가 특정된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{3}[0-9]{7}` | `ABC1234566`, `XYZ9876541` (`AB1234567`, `ABC123456` 은 거부) | score 사용 고려. `대문자 3 + 숫자 7` 은 제품·예약 코드와 겹칠 수 있으나 뒤 7자리 Luhn(1/10)으로 보완된다. `boundary_check: true` 적용 |

    오탐: 중간.
  - **byte-scan handwritten**: 가능. 오탐률은 regex + Luhn 조합과 **동일**하다.
  - **Aho-Corasick**: 부적합.
  - **권장**: regex + 뒤 7자리 Luhn 검증기.
- **검증기**:
  - 현재: `luhn` 이 존재하지만 매치 전체가 아니라 뒤 7자리에만 적용해야 한다. 기존 `luhn` 은 숫자만 걸러 계산하므로 문자 3자를 무시하면 결과적으로 뒤 7자리에 적용되어 그대로 쓸 수 있다.
  - 구현 가능: 별도 구현 불필요(python-stdnum `in_.epic` 와 동일).
- **채택 여부 및 근거**: 채택. 신분증 번호이며 기존 `luhn` 을 재사용할 수 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `voter id`, `voter card`, `epic`, `epic number`, `election card`, `electoral`

### in_passport

- **설명**: 인도 여권번호. `대문자 1 + 숫자 7` 의 8자리이다(예: `A1234567`). 첫 문자는 발급 시리즈이다. 번호 자체에 체크섬은 없고 MRZ 에 7-3-1 체크 디지트가 붙는다.
  - 예시: `A1234567`, `N9876543` (형식 예시)
- **법적 근거**:
  - 법령: Passports Act 1967, DPDP Act 2023
  - 감독기관: MEA (Passport Seva), Data Protection Board of India
  - 노출 금지 이유: 정부 발급 신분증 번호로서 항공·비자·은행 KYC 에 쓰인다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z][0-9]{7}[0-9]?` | `A1234567`, `N9876543` (`AB123456`, 7자리는 거부) | score 사용 고려. `대문자 1 + 숫자 7` 은 제품 코드·주문번호와 자주 겹친다. 미국 A-Number(`A` + 7-9자리)와도 형식이 겹친다. 선택 꼬리는 MRZ 체크 디지트 표기용이며 9자리 매치에만 `mrz_731` 적용. `boundary_check: true` 적용 |

    오탐: 중간~높음. 기존 `us_passport` 패턴 `([a-zA-Z]\d{8}|[0-9]{9})` 가 9자리 표기 `A12345678` 을 이미 잡으므로 겹침이 생긴다. 실제 MRZ 표기는 `A1234567<` + 체크 디지트이며 `<` 의 가중치 값이 0 이라 `mrz_731` 계산 결과는 같다.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합.
  - **권장**: regex + `mrz_731`(9자리 매치에만). 점수 체계 도입 후 낮은 `score` 검토.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 번호 자체에는 없다. MRZ 체크 디지트 동반 시 `mrz_731`(de_DE 문서).
- **채택 여부 및 근거**: 채택. 정부 발급 신분증 번호이다. 오탐이 중간 이상이므로 점수 체계 도입 후 낮은 `score` 로 전환을 검토한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `passport`, `passport number`, `passport no`, `passport seva`

### in_driver_license

- **설명**: 운전면허번호. 주 코드 2자 + RTO 코드 2자리 + 발급 연도 4자리 + 일련번호 7자리의 15자리이며, `MH12 20110012345`, `MH-12-2011-0012345`, `MH1220110012345` 처럼 구분자 표기가 주마다 다르다. 2019년 전국 통일 형식이 도입되었으나 구형 번호가 병존한다. Sarathi 데이터베이스에서 조회된다.
  - 예시: `MH12 20110012345`, `MH-12-2011-0012345`, `MH1220110012345`, `DL0420180012345` (형식 예시)
- **법적 근거**:
  - 법령: Motor Vehicles Act 1988 제9조, Central Motor Vehicles Rules 1989, DPDP Act 2023
  - 감독기관: MoRTH, 각 주 RTO, Data Protection Board of India
  - 노출 금지 이유: 사진 신분증으로 널리 쓰이며 Sarathi 에서 이름·생년월일·주소와 연결된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{2}[- ]?[0-9]{2}[- ]?(19\|20)[0-9]{2}[- ]?[0-9]{7}` | `MH12 20110012345`, `MH-12-2011-0012345`, `MH1220110012345`, `DL0420180012345` (`MH12 30110012345`(연도 30xx), 14자리는 거부) | score 사용 고려. 주 코드 2자 + 연도 `19xx`/`20xx` 구조가 필터이지만 구분자 없는 13자리 숫자 부분은 다른 번호와 겹칠 수 있다. 주 코드 표(약 37개)를 넣으면 좁아진다. `boundary_check: true` 적용 |

    오탐: 중간.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 주 코드 37개(`MH`, `DL`, `KA` …)를 anchor 로 등록할 수 있으나 2바이트라 흔하다.
  - **권장**: regex. 주 코드 표는 검증기로 둔다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 주 코드 표(`AN`, `AP`, `AR`, `AS`, `BR`, `CH`, `CG`, `DD`, `DL`, `GA`, `GJ`, `HR`, `HP`, `JK`, `JH`, `KA`, `KL`, `LA`, `LD`, `MP`, `MH`, `MN`, `ML`, `MZ`, `NL`, `OD`, `PY`, `PB`, `RJ`, `SK`, `TN`, `TS`, `TR`, `UP`, `UK`, `WB` 등. 최신 목록으로 재확인 필요) 대조.
- **채택 여부 및 근거**: 채택. 신분증 번호이며 형식이 비교적 특이하다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `driving licence`, `driving license`, `dl number`, `dl no`, `rto`, `sarathi`, `licence number`

### in_bank_account

- **설명**: 인도는 IBAN 을 쓰지 않는다. 계좌 식별은 IFSC(Indian Financial System Code, 11자리: 은행 코드 4자 + `0` + 지점 코드 6자, 예: `SBIN0001234`) + 계좌번호(은행마다 9-18자리 숫자)의 조합으로 한다. IFSC 자체는 지점 코드라 공개 정보이고, 계좌번호 단독은 형식이 없어 검출할 수 없으므로 두 값이 함께 적힌 경우만 대상으로 한다.
  - 예시: `SBIN0001234 12345678901`, `HDFC0000123, 50100123456789` (형식 예시. 계좌번호는 가상)
- **법적 근거**:
  - 법령: SPDI Rules 2011 제3조 (금융정보는 민감 개인정보), Payment and Settlement Systems Act 2007, RBI KYC Master Direction, DPDP Act 2023
  - 감독기관: RBI, Data Protection Board of India
  - 노출 금지 이유: IFSC + 계좌번호로 NEFT/RTGS/IMPS 송금 대상 지정과 계좌 도용 시도가 가능하다.
- **결정론적 검출 가능성**: 조합 표기만 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{4}0[A-Z0-9]{6}[ ,:/-]+[0-9]{9,18}` | `SBIN0001234 12345678901`, `HDFC0000123, 50100123456789` | score 사용 고려. IFSC 의 `대문자 4 + 0 + 6자리` 구조가 필터이고 계좌번호가 뒤따르는 조합은 자연어에서 드물다. `boundary_check: true` 적용 |
    | `[A-Z]{4}0[A-Z0-9]{6}` (IFSC 단독) | `SBIN0001234`, `HDFC0000123` (`SBIN1001234`(5번째 자리 1), 10자리는 거부) | 기본에 가깝다(형식이 특이함). 그러나 IFSC 는 공개 지점 코드라 단독으로는 개인정보가 아니므로 등록하지 않는다. 미채택 행 |

    오탐: 조합 표기는 낮다.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 은행 코드(`SBIN0`, `HDFC0`, `ICIC0` …)를 anchor 로 등록할 수 있다(5바이트). 은행 코드 표는 상업은행 기준 약 150개이며 협동조합 은행까지 포함하면 훨씬 많다(RBI 목록 기준 확인 필요).
  - **권장**: regex(조합 표기). 계좌번호 단독은 검출 불가.
- **검증기**:
  - 현재: 없음
  - 구현 가능: IFSC 은행 코드 표(RBI 공개) 대조. 계좌번호는 은행별 체크섬이 공개되어 있지 않다.
- **채택 여부 및 근거**: 조건부 채택. IFSC 와 계좌번호가 함께 적힌 경우만 검출하며, 계좌번호 단독 검출은 불가능하다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `ifsc`, `account number`, `a/c no`, `bank account`, `neft`, `rtgs`, `imps`, `beneficiary`

### in_phonenumber

- **설명**: 인도 전화번호. 국가번호 `+91`. 휴대전화는 `6`-`9` 로 시작하는 10자리(`98765 43210`, 5-5 로 띄어 쓰는 관행)이고, 국내에서는 앞에 `0` 을 붙이기도 한다. 유선은 STD 코드(2-4자리, `011` 델리, `022` 뭄바이, `0413` 푸두체리 등) + 가입자 번호로 선행 `0` 포함 11자리이다.
  - 예시: 휴대전화 `98765 43210`, `+91 98765 43210`, `9876543210`, `+91-9876543210`, `09876543210`. 유선 `011-2345 6789`, `022 2345 6789`, `+91 11 2345 6789`, `0413-2345678`, `04562 234567`, `01123456789`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: Telecommunications Act 2023, TRAI TCCCPR 2018 (DND 등록·상업 통신 제한), DPDP Act 2023
  - 감독기관: TRAI, DoT, Data Protection Board of India
  - 노출 금지 이유: 휴대전화번호는 Aadhaar 인증 OTP·UPI 결제·은행 앱의 열쇠이며, 인도는 OTP 사기와 스팸 전화가 특히 많다.
- **결정론적 검출 가능성**: 휴대전화는 가능, 유선은 가능하나 약하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `(\+91[ -]?\|0)?[6-9][0-9]{4}[ -]?[0-9]{5}` | `98765 43210`, `+91 98765 43210`, `9876543210`, `+91-9876543210`, `09876543210` (`58765 43210`, 9자리는 거부) | score 사용 고려. 첫 자리 `6`-`9` 와 10자리 고정 길이가 필터이지만, 구분자 없는 10자리 숫자열은 미국 전화번호·NHS 번호 등과 겹친다. `boundary_check: true` 적용 |
    | `(\+91[ -]?\|0)[1-9][0-9]{1,3}[ -]?[0-9]{3,4}[ -]?[0-9]{2,4}` | `011-2345 6789`, `022 2345 6789`, `+91 11 2345 6789`, `0413-2345678`, `04562 234567`, `01123456789` (`11-2345 6789`(선행 0 없음), `011-234` 는 거부) | **score 사용 필요**. STD 코드(2-4자리) + 가입자 번호(6-8자리) 조합을 넓게 허용하며, 구분자 없는 `09876543210`·`+919876543210` 은 휴대전화 패턴과도 동시에 매치된다(같은 `pii_type` 이라 겹침 해소에서 합쳐진다). STD 코드 표(약 2,600개)를 넣으면 좁아진다 |

    오탐: 휴대전화는 중간, 유선은 높다.
  - **byte-scan handwritten**: 가능. 유선번호는 STD 코드 표를 코드 표로 두면 DFA 비대화를 피한다.
  - **Aho-Corasick**: `+91`(3바이트)만 anchor 로 적합하다. 국내 표기는 첫 자리 한 글자라 부적합하다.
  - **권장**: 휴대전화는 regex, 유선은 점수 체계 도입 후 낮은 `score` 의 별도 recognizer(`in_phonenumber_landline`).
- **검증기**:
  - 현재: 없음
  - 구현 가능: 휴대전화는 첫 자리 규칙 외 없음. 유선은 STD 코드 표(DoT 공고, 최신 목록으로 재확인 필요).
- **채택 여부 및 근거**: 휴대전화는 채택. 유선은 채택하되 점수 체계 도입이 선행 조건이며 그 전에는 등록하지 않는다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `mobile`, `mobile number`, `phone`, `phone number`, `contact`, `whatsapp`, `otp`(3글자, 제외), `call me`, `mob`(3글자, 제외)

### in_vehicle_plate

- **설명**: 차량 등록번호. `주 코드 2자 + RTO 코드 1-2자리 + 시리즈 문자 1-3자 + 숫자 4자리`(`MH 12 AB 1234`) 구조이며 구분자 없이 `MH12AB1234` 로도 쓴다. 델리는 RTO 코드 뒤에 차종 문자가 붙어 `DL 1C AB 1234` 로 쓴다. 2021년 도입된 BH(Bharat) 시리즈는 `연도 2자리 + BH + 숫자 4 + 문자 2`(`22 BH 1234 AA`) 형식이다. Vahan 데이터베이스에서 소유자와 연결된다.
  - 예시: `MH 12 AB 1234`, `MH12AB1234`, `DL 1C AB 1234`, `DL-1C-AB-1234`, `KA-01-A-1234`, BH `22 BH 1234 AA`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: Motor Vehicles Act 1988 제41조, Central Motor Vehicles Rules 1989 제50조–제51조, DPDP Act 2023. Vahan 의 소유자 정보 공개는 2019년 이후 제한되었다.
  - 감독기관: MoRTH, 각 주 RTO
  - 노출 금지 이유: Vahan 에서 번호로 소유자 이름·주소를 조회할 수 있었고(현재는 부분 마스킹), 통행·주차 기록과 결합하면 위치 추적이 가능하다. 공개 노출되는 번호라 단독 위험도는 낮다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{2}[ -]?[0-9]{1,2}[A-Z]?[ -]?[A-Z]{1,3}[ -]?[0-9]{4}` | `MH 12 AB 1234`, `MH12AB1234`, `DL 1C AB 1234`, `DL-1C-AB-1234`, `KA-01-A-1234` (`MH 12 AB 123`, `M 12 AB 1234` 는 거부) | score 사용 고려. `대문자 2 + 숫자 + 대문자 + 숫자 4` 는 제품 코드와 겹칠 수 있다. `[A-Z]?` 는 델리의 차종 문자용. 주 코드 표(약 37개)를 리터럴 대안으로 넣으면 좁아진다. `boundary_check: true` 적용 |
    | `[0-9]{2}[ -]?BH[ -]?[0-9]{4}[ -]?[A-Z]{2}` (BH 시리즈) | `22 BH 1234 AA`, `22BH1234AA` | 기본. `BH` 리터럴이 필터. 공식 형식은 문자 2자 고정 |

    오탐: 중간.
  - **byte-scan handwritten**: 주 코드 표를 코드 표로 두면 정밀해진다. 오탐률은 주 코드 표를 쓴 regex 와 **동일**하다.
  - **Aho-Corasick**: BH 시리즈는 anchor `BH` 가 2바이트라 흔하다. 일반 형식은 주 코드가 열려 있다.
  - **권장**: regex + 주 코드 표 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 주 코드 표 대조(운전면허와 공유).
- **채택 여부 및 근거**: 채택. Vahan 조회로 소유자 특정이 가능하고 형식이 비교적 특이하다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `vehicle number`, `registration number`, `number plate`, `rc number`, `vahan`, `car number`, `bike number`

### in_abha

- **설명**: ABHA (Ayushman Bharat Health Account) 번호. 국가보건청(NHA)이 ABDM 정책에 따라 부여하는 14자리 건강 계정 번호로 `91-1234-5678-9012` 처럼 2-4-4-4 로 표기한다. 첫 두 자리와 체크섬 규칙은 공개 명세를 확인하지 못했다(확인 필요). ABHA 주소(`name@abdm`)라는 이메일 형태의 식별자도 함께 쓰인다.
  - 예시: `91-1234-5678-9012` (형식 예시. 구조 미확인이라 검증하지 않았다)
- **법적 근거**:
  - 법령: ABDM Health Data Management Policy, SPDI Rules 2011 제3조 (건강정보는 민감 개인정보), DPDP Act 2023
  - 감독기관: NHA, Data Protection Board of India
  - 노출 금지 이유: 전자 건강기록의 연결 키이며 건강정보는 민감 개인정보이다.
- **결정론적 검출 가능성**: 가능하나 형식이 확인되지 않았다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{2}-[0-9]{4}-[0-9]{4}-[0-9]{4}` | `91-1234-5678-9012` | score 사용 고려. 하이픈 `2-4-4-4` 구조는 비교적 특이하지만, 구조 확인 전에는 등록하지 않는다 |

  - **byte-scan handwritten**: 구조 확인 후 판단.
  - **Aho-Corasick**: 첫 두 자리가 고정(`91`?)이면 anchor `91-` 로 가능하나 확인 필요.
  - **권장**: 형식·체크섬 확인 후 결정.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 확인 필요.
- **채택 여부 및 근거**: 조건부 채택. 건강 데이터의 연결 키이지만 형식 명세를 확인하지 못했다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `abha`, `abha number`, `health id`, `abdm`, `ayushman`

### in_gstin

- **설명**: GSTIN (Goods and Services Tax Identification Number). 사업자에게 부여하는 15자리 영숫자로 `주 코드 2자리 + PAN 10자 + 등록 순번 1자 + Z + 체크 문자 1자` 구조이며, 체크 문자는 36진 Luhn 변형이다. 사업자의 PAN 이 그대로 들어 있다.
  - 예시: `27AAPFU0939F1ZV` (python-stdnum 문서 예시. 체크 문자 통과)
- **법적 근거**:
  - 법령: CGST Act 2017 제25조. GST 포털에서 **공개 조회**되고 송장·간판에 기재가 의무이다.
  - 감독기관: CBIC
  - 노출 금지 이유: 약하다. 공개 사업자 번호이다. 다만 개인사업자(proprietorship)의 GSTIN 은 개인 PAN 을 포함한다. GSTIN 을 붙여 쓴 경우(`27AAPFU0939F1ZV`)에는 `in_pan` 이 `boundary_check` 때문에 안의 PAN 을 잡지 못하고, `27 AAPFU0939F 1ZV` 처럼 띄어 쓴 경우에만 잡는다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]` | `27AAPFU0939F1ZV` | 기본. 15자리 구조와 `Z` 고정 자리가 강한 필터. 미채택 항목 |

  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합.
  - **권장**: 미채택. 개인사업자 보호가 필요해지면 GSTIN 전체를 잡는 이 recognizer 를 등록하는 편이, `in_pan` 의 부분 매치에 기대는 것보다 확실하다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 36진 Luhn 변형(python-stdnum `in_.gstin` 과 동일).
- **채택 여부 및 근거**: 미채택. 공개 사업자 번호이다.
- **기존 구현 여부**: 신규 (미채택이므로 구현하지 않음)
- **context_words 후보** (재검토 시 참고): `gstin`, `gst number`, `gst no`

## 4. 검토 후 미채택한 항목

아래 항목은 법령상 PII 이거나 식별번호이지만 결정론적 검출이 불가능하거나 공개 번호라서 recognizer 로 등록하지 않는다.

| 항목 | 법적 근거 | 미채택 이유 |
|---|---|---|
| UPI ID / VPA (`9876543210@paytm`, `name@upi`) | Payment and Settlement Systems Act 2007 | 이메일과 같은 `local@handle` 형태라 공통 이메일 recognizer 와 겹친다. 휴대전화번호 기반 VPA 는 `in_phonenumber` 가 앞부분을 잡는다. |
| CIN (Corporate Identification Number, 21자리) | Companies Act 2013 | 공개 법인 번호이다. |
| TAN (Tax Deduction Account Number, `ABCD12345E`) | Income-tax Act 1961 제203A조 | 원천징수 사업자 번호이며 공개 조회된다. |
| Ration card, NREGA job card, PDS 번호 | 각 주 규정 | 주마다 형식이 다르고 명세가 없다. |
| PIN code (6자리 우편번호) | 해당 없음 | 6자리 숫자는 다른 숫자열과 구분되지 않는다. |
| 주소, 이름, 생년월일 | DPDP Act 제2조 | 국가 종속 항목이 아니며 regex 로 결정론적 검출이 불가능하다. 공통 항목 또는 NER 로 다룬다. |
| 생체정보, 건강 상태, 카스트·종교 | SPDI Rules 2011 제3조 | 민감 개인정보이지만 번호 형태로 나타나지 않는다. |
| 신용카드번호, 이메일, IP 주소 | SPDI Rules, PCI DSS | 국가 종속 항목이 아니므로 이 문서 범위 밖이다. 기존 `card_number` 등이 담당한다. |

## 5. 구현 시 후속 작업 요약

이 문서에서 도출된, YAML·`validator.rs`·`handwritten/`·엔진에 반영할 작업 목록이다. 검증기는 **함수 구현 → YAML 등록** 순서를 지킨다(`validator::validate` 가 fail-open 이므로 순서가 바뀌면 검증 없이 통과한다).

| 순서 | 작업 | 대상 | 종류 |
|---|---|---|---|
| 선행 | recognizer 단위 `score` 필드와 context 가산 방식 도입 (en_US 문서 5절과 공통. 이미 완료되었으면 이 행 삭제) | 엔진 | 엔진 변경 |
| 1 | `verhoeff` 검증기(회문 배제 포함)와 `in_aadhaar` recognizer 추가 (Aadhaar·VID 두 패턴) | in_aadhaar | validator 신규, YAML 신규 |
| 2 | `in_pan` recognizer 추가 | in_pan | YAML 신규 |
| 3 | `in_voter_id` recognizer 추가 (기존 `luhn` 재사용) | in_voter_id | YAML 신규 |
| 4 | `in_passport` recognizer 추가 (`mrz_731` 검증기는 de_DE 작업과 공용). 낮은 `score` 전환은 선행 작업 후 | in_passport | YAML 신규 |
| 5 | `in_driver_license` recognizer 추가. 주 코드 표 검증기 `in_state_code` 는 번호판과 공용 | in_driver_license | YAML 신규, validator 신규 |
| 6 | `in_bank_account` recognizer 추가 (IFSC + 계좌번호 조합만) | in_bank_account | YAML 신규 |
| 7 | `in_phonenumber` 휴대전화 recognizer 추가 (`boundary_check: true`) | in_phonenumber | YAML 신규 |
| 8 | `in_phonenumber_landline` recognizer 추가 (`score` 낮게). **선행 작업 완료 후에만** | in_phonenumber | YAML 신규 |
| 9 | `in_vehicle_plate` recognizer 추가 (일반 + BH 시리즈) | in_vehicle_plate | YAML 신규 |
| 10 | ABHA 번호 형식·체크섬 확인 후 `in_abha` 등록 여부 결정 | in_abha | 조사 |
| 선택 | `in_gstin` recognizer (사업자 번호 마스킹 요구 시) | in_gstin | validator 신규, YAML 신규 |
