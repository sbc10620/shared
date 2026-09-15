# PII 목록: de_DE (독일)

이 문서는 `tinicore/src/guardrails/config/pii_filter_config.yaml` 에 독일(de_DE) 고유 PII recognizer 가 포함되어야 하는 근거를 기록한다. 이미 YAML 에 있는 항목도 근거를 남기기 위해 포함하며, 국가에 종속되지 않는 항목(카드번호, API 키, 비밀번호, 이메일, IP 주소 등)은 다루지 않는다. 2026-09-15 현재 YAML 에 `de_*` recognizer 는 하나도 없으므로 이 문서의 모든 항목은 신규이다.

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

엔진은 DFA 를 `MatchKind::All` 로 빌드해 겹치는 모든 매치 끝을 보고한 뒤 boundary check 와 dedup 으로 가장 긴 것을 남긴다. 따라서 `[0-9]?` 처럼 선택적 꼬리가 있는 패턴은 꼬리 없는 매치와 있는 매치를 모두 찾고 긴 쪽이 남는다. 또한 엔진이 `unicode(false)` 로 DFA 를 빌드하므로 움라우트(`Ä`, `Ö`, `Ü`)는 문자 클래스 `[A-ZÄÖÜ]` 안에 넣을 수 없고(`regex-syntax` 가 `UnicodeNotAllowed` 로 거부), `([A-Z]|Ä|Ö|Ü)` 처럼 리터럴 대안으로 써야 한다(ko_KR 문서의 한글 처리와 같은 이유).

## 1. 적용 법령 및 감독기관

독일은 EU 회원국이므로 GDPR(일반 개인정보 보호 규정)이 직접 적용되고, 연방 개인정보 보호법(BDSG)이 GDPR 의 개방 조항을 채우는 국내 이행법이다. 감독기관은 연방 차원의 BfDI 와 16개 주(Land)의 개별 감독기관으로 나뉘며, 민간 기업은 소재지 주의 감독기관이 담당한다. GDPR 제87조는 국가 식별번호의 이용 조건을 회원국이 정하도록 위임하고, 독일은 이를 세금 ID(AO 제139b조), 신분증 번호(PAuswG 제20조), 사회보험번호(SGB IV) 등 개별법으로 정한다. 개별법이 "이 번호를 다른 데이터의 연결 키로 쓰지 말라"고 명시한 번호가 이 문서의 최우선 채택 대상이다.

| 법령 | 감독기관 | 적용 범위 요약 |
|---|---|---|
| GDPR (Regulation (EU) 2016/679) 제4조, 제9조, 제32조, 제87조 | BfDI (Bundesbeauftragte für den Datenschutz und die Informationsfreiheit), 16개 주 감독기관 (Landesdatenschutzbehörden), 조정 기구 DSK | 개인정보 정의, 특수 범주(건강·생체 등), 처리 보안, 국가 식별번호 이용 조건 위임 |
| Bundesdatenschutzgesetz (BDSG) 제22조, 제26조 | BfDI, 주 감독기관 | 특수 범주 처리의 국내 조건, 고용 관계에서의 개인정보 |
| Abgabenordnung (AO) 제139b조, 제30조 | Bundeszentralamt für Steuern (BZSt), 재무부 | 세금 식별번호(IdNr)의 발급과 이용 제한. 제139b조 제2항은 재정 당국 외의 이용을 원칙적으로 금지. 제30조는 조세 비밀 |
| Sozialgesetzbuch VI (SGB VI) 제147조; Sozialgesetzbuch IV (SGB IV) 제18f조–제18h조 | Deutsche Rentenversicherung Bund, 연방 노동사회부 | SGB VI 제147조는 사회보험번호(Versicherungsnummer)의 구조와 "생년월일 외 개인정보 포함 금지", SGB IV 제18f조–제18h조는 이용 제한 |
| Sozialgesetzbuch V (SGB V) 제290조 | GKV-Spitzenverband, 연방 보건부 | 건강보험 피보험자 번호(Krankenversichertennummer)의 구조 |
| Personalausweisgesetz (PAuswG) 제20조 | 연방 내무부, 각 주 신분증 발급 관청 | 신분증 일련번호를 자동화된 개인정보 조회나 파일 연결에 사용하는 것을 금지 |
| Passgesetz (PassG) 제16조 (조문 번호 확인 필요) | 연방 내무부 | 여권 일련번호에 대해 PAuswG 제20조와 같은 이용 제한 |
| Straßenverkehrsgesetz (StVG) 제2조, 제39조; Fahrerlaubnis-Verordnung (FeV) | Kraftfahrt-Bundesamt (KBA), 각 주 운전면허 관청 | 운전면허 발급, 차량 보유자 정보 조회(Halterauskunft) 조건 |
| Telekommunikationsgesetz (TKG), Telekommunikation-Digitale-Dienste-Datenschutz-Gesetz (TDDDG, 2024년 5월까지의 명칭은 TTDSG) | Bundesnetzagentur, BfDI | 통신 가입자 정보(전화번호 포함) 보호, 통신 비밀 |
| Umsatzsteuergesetz (UStG) 제14조 | 재무부 | 송장에 Steuernummer 또는 USt-IdNr 기재 의무 (이 번호들이 준공개인 근거) |
| Geldwäschegesetz (GwG), Zahlungsdiensteaufsichtsgesetz (ZAG) | BaFin | 금융 거래 정보와 계좌 식별자(IBAN) 취급 |

## 2. 요약 표

| pii_type | 설명 | 결정론적 검출 | 권장 검출 방식 | 검증기 (현재 / 구현 가능) | score | 기존 구현 | 채택 |
|---|---|---|---|---|---|---|---|
| de_tax_id | 세금 식별번호 (Steuer-IdNr) | 가능 | regex (+ `de_idnr` 검증기) | 없음 / ISO 7064 변형 체크 디지트 + 반복 규칙 | 사용 고려 | 신규 | 채택 |
| de_social_security_number | 사회보험번호 (Versicherungsnummer, RVNR) | 가능 (형식 엄격) | regex (+ `de_svnr` 검증기) | 없음 / 가중 교차합 체크 디지트 | 기본 | 신규 | 채택 |
| de_id_card | 신분증 일련번호 (Personalausweis) | 가능 | regex (+ `mrz_731` 검증기, 체크 디지트 동반 시) | 없음 / MRZ 7-3-1 체크 디지트 | 사용 고려 | 신규 | 채택 |
| de_passport | 여권 일련번호 (Reisepass) | 가능 | regex (+ `mrz_731` 검증기, 체크 디지트 동반 시) | 없음 / MRZ 7-3-1 체크 디지트 | 사용 고려 | 신규 | 채택 |
| de_health_insurance_number | 건강보험 피보험자 번호 (KVNR) | 가능 | regex (+ `de_kvnr` 검증기) | 없음 / 가중 교차합 체크 디지트 | 사용 고려 | 신규 | 채택 |
| de_iban | 독일 IBAN | 가능 | regex 또는 Aho-Corasick (+ `iban` 검증기) | 없음 / ISO 7064 mod 97-10 | 기본 | 신규 | 조건부 채택 (공통 항목 `iban` 으로 이관 검토) |
| de_phonenumber (recognizer `de_phonenumber`) | 휴대전화번호 (015x/016x/017x) | 가능 | Aho-Corasick handwritten (anchor `015`, `016`, `017`, `+49`) 또는 regex | 없음 / 없음 | 사용 고려 | 신규 | 채택 |
| de_phonenumber (recognizer `de_phonenumber_landline`) | 유선전화번호 | 가능 (매우 약함) | regex | 없음 / 지역번호 표 (5,200여 개) | **사용 필요** | 신규 | 채택 (점수 체계 도입이 선행 조건) |
| de_vehicle_plate | 차량 번호판 (Kfz-Kennzeichen) | 가능 | regex (움라우트는 리터럴 대안) | 없음 / 지역 코드 표 (약 700개) | 사용 고려 | 신규 | 채택 |
| de_driver_license | 운전면허번호 (Führerscheinnummer) | 가능 (형식 확인 필요) | regex | 없음 / 확인 필요 | **사용 필요** | 신규 | 조건부 채택 (형식 명세 확인 후) |
| de_tax_number | 세금 번호 (Steuernummer) | 가능 | regex | 없음 / 없음 | 사용 고려 | 신규 | 미채택 (보류) |

이외에 검토했으나 결정론적 검출이 불가능하거나 공개 번호라서 미채택한 항목은 4절에 정리했다.

## 3. 항목별 상세

### de_tax_id

- **설명**: Steuerliche Identifikationsnummer (IdNr, Steuer-ID). 2008년부터 연방 중앙세무청(BZSt)이 모든 거주자에게 출생 시 또는 전입 시 부여하는 11자리 평생 불변 번호. 첫 자리는 `0` 이 아니고, 앞 10자리 중 정확히 한 숫자가 두 번(2016년 이후 발급분은 세 번까지) 나타나며 한 숫자는 나타나지 않는다. 마지막 자리는 체크 디지트이다. 세무 서류에는 `36 574 261 809` 처럼 `2-3-3-3` 으로 띄어 쓴다.
  - 예시: `36574261809`, `36 574 261 809` (BZSt 안내 자료에 쓰이는 형식 예시. 체크 디지트와 반복 규칙을 통과한다)
- **법적 근거**:
  - 법령: AO 제139b조 (제2항: 재정 당국 외에는 법률이 허용한 경우에만 수집·이용 가능, 다른 목적의 연결 키로 사용 금지), AO 제30조 (조세 비밀), GDPR 제87조
  - 감독기관: BZSt, BfDI
  - 노출 금지 이유: 평생 불변의 범용 식별자라서 GDPR 제87조가 특별히 다루는 국가 식별번호에 해당한다. 세금 환급 사기와 신원 도용에 쓰이며, 고용주(2013년 ELStAM 이후)·은행(2016년 Freistellungsauftrag 이후)·보험사가 모두 수집하므로 유출 경로가 넓다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[1-9][0-9]{10}` | `36574261809` (`06574261809`, 10자리는 거부) | score 사용 고려. 구분자 없는 11자리 숫자는 전화번호·주문번호와 겹치므로 `de_idnr` 검증기 병행이 사실상 필수이다. 검증기 없이 등록한다면 score 사용 필요 |
    | `[1-9][0-9] [0-9]{3} [0-9]{3} [0-9]{3}` | `36 574 261 809` | 기본. `2-3-3-3` 공백 표기는 특이하다 |

    오탐: 검증기 없이는 높다(11자리 숫자열). 검증기를 붙이면 체크 디지트(1/10)와 반복 규칙(무작위 11자리 중 약 4%만 통과: 2회 반복 1.6% + 3회 반복 2.2%)이 결합해 약 0.4% 수준으로 낮아진다. `boundary_check: true` 를 적용한다.
  - **byte-scan handwritten**: 가능. 숫자열 11자리를 뽑아 반복 규칙과 체크 디지트를 매칭 단계에서 계산한다. 오탐률은 regex + `de_idnr` 조합과 **동일**하다.
  - **Aho-Corasick**: 부적합. 고정 리터럴 접두가 없다.
  - **권장**: regex + `de_idnr` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 두 규칙을 합쳐 `de_idnr` 로 구현한다. (1) 반복 규칙: 앞 10자리 중 정확히 하나의 숫자만 2회 또는 3회 나타나고 나머지는 1회 이하(3회 반복 시 같은 숫자가 세 자리 연속으로 올 수 없다는 부가 조건이 있다는 자료가 있음, 확인 필요). (2) 체크 디지트: ISO 7064 MOD 11,10 변형. `product = 10` 에서 시작해 앞 10자리 각각에 대해 `sum = (digit + product) mod 10`, `sum` 이 0이면 10으로, `product = (sum × 2) mod 11` 을 반복한 뒤 `check = 11 - product`, 결과가 10이면 0. 이 값이 11번째 자리와 같으면 유효하다.
- **채택 여부 및 근거**: 채택. 법률이 이용을 제한하는 국가 식별번호이며 검증기로 정밀도를 확보할 수 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `steuer-id`, `steuerid`, `steuerliche identifikationsnummer`, `identifikationsnummer`, `idnr`, `steuer id`, `tax id`, `tin`(3글자라 제외), `finanzamt`, `elster`

### de_social_security_number

- **설명**: Versicherungsnummer (Sozialversicherungsnummer, Rentenversicherungsnummer). 독일 연금보험(Deutsche Rentenversicherung)이 부여하는 12자리 번호로 `BB DDMMYY L SS P` 구조이다. `BB` 는 연금보험 관할 지역번호(2자리), `DDMMYY` 는 생년월일, `L` 은 출생 시 성(姓)의 첫 글자(대문자), `SS` 는 일련번호(남성 `00`-`49`, 여성 `50`-`99`), `P` 는 체크 디지트이다. 생일 미상은 `00`, 같은 날 일련번호가 소진되면 일(DD)에 32를 더한다(`32`-`63`)는 규칙이 있다는 자료가 있으므로(확인 필요), 아래 regex 는 이런 예외 번호를 놓친다. 2022년까지 발급된 사회보험 카드(Sozialversicherungsausweis)와 2023년부터 대체된 서면 통지(Versicherungsnummernachweis)에 `65 170839 J 003` 처럼 인쇄된다.
  - 예시: `65170839J003`, `65 170839 J 003` (독일어 위키백과가 구조 설명에 쓰는 예시. 체크 디지트 `3` 을 통과한다), `12 190564 T 125` (계산으로 만든 형식 예시)
- **법적 근거**:
  - 법령: SGB VI 제147조 (구조), SGB IV 제18f조–제18h조 (사회보험 목적 외 이용 금지), GDPR 제87조
  - 감독기관: Deutsche Rentenversicherung Bund, BfDI
  - 노출 금지 이유: 생년월일과 성의 첫 글자가 번호 안에 그대로 들어 있어 번호 자체가 개인정보를 드러낸다. 고용·연금·실업급여 기록의 연결 키이며 SGB IV 가 목적 외 이용을 금지한다.
- **결정론적 검출 가능성**: 가능하며 형식이 엄격하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{2} ?(0[1-9]\|[12][0-9]\|3[01])(0[1-9]\|1[0-2])[0-9]{2} ?[A-Z] ?[0-9]{3}` | `65170839J003`, `65 170839 J 003`, `12 190564 T 125` (`65170839j003`, `65321339J003`(월 `13`), `65170839J00` 은 거부) | 기본. 생년월일 범위와 가운데 대문자 1자 덕분에 무작위 문자열이 우연히 맞기 어렵다. `de_svnr` 검증기 병행 시 더 낮아진다. `boundary_check: true` 적용 |

    오탐: 낮다. 소문자 `j` 는 규격 밖이지만 사용자 입력에 나타날 수 있으므로 `(?i)` 적용 여부를 구현 시 결정한다.
  - **byte-scan handwritten**: 가능. 오탐률은 regex + `de_svnr` 조합과 **동일**하다. 단일 패턴이라 메모리 이점이 없다.
  - **Aho-Corasick**: 부적합. 접두 2자리가 지역번호(50여 종)라 anchor 로 너무 짧고 많다.
  - **권장**: regex + `de_svnr` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크 디지트. 문자 `L` 을 알파벳 순번 2자리(`A`=01 … `Z`=26)로 바꿔 12자리 숫자열을 만들고, 가중치 `2 1 2 5 7 1 2 1 2 1 2 1` 을 곱한 각 곱의 자릿수 합(교차합)을 모두 더해 10으로 나눈 나머지가 체크 디지트와 같으면 유효하다. 검증기 `de_svnr` 로 구현한다. 생년월일의 월별 일수 검사도 함께 넣을 수 있다.
- **채택 여부 및 근거**: 채택. 형식이 엄격하고 검증기가 있으며 SGB IV 가 목적 외 이용을 금지한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `sozialversicherungsnummer`, `versicherungsnummer`, `rentenversicherungsnummer`, `sv-nummer`, `svnr`, `rvnr`, `sozialversicherung`, `rentenversicherung`, `social security`

### de_id_card

- **설명**: Personalausweis(신분증) 일련번호(Seriennummer). 2010년 11월 도입된 신형 신분증(nPA)은 9자리 영숫자이며, 앞 4자리는 발급 관청 식별번호(Behördenkennzahl)이며 그 첫 문자는 `L`, `M`, `N`, `P`, `R`, `T`, `V`, `W`, `X`, `Y` 중 하나이고 나머지 8자리는 숫자와 자음(`C F G H J K L M N P R T V W X Y Z`, 모음과 `B`·`D`·`Q`·`S` 제외)으로 구성된다. 카드 앞면과 MRZ 에 인쇄되며 MRZ 에서는 10번째 자리에 체크 디지트가 붙는다. 전자체류허가증(eAT)도 같은 구조를 쓴다. 문자 집합은 연방 인쇄국 명세로 재확인이 필요하다.
  - 예시: `L01X00T47` (연방 인쇄국의 Erika Mustermann 견본 신분증 번호), `L01X00T471` (MRZ 체크 디지트 `1` 포함 표기. 7-3-1 규칙을 통과한다)
- **법적 근거**:
  - 법령: PAuswG 제20조 제2항 (일련번호를 자동화된 개인정보 조회나 파일 연결에 사용 금지), GDPR 제87조
  - 감독기관: 연방 내무부, BfDI
  - 노출 금지 이유: 법이 일련번호의 연결 키 사용을 명시적으로 금지한다. 신분증 번호는 온라인 본인확인(Video-Ident, PostIdent)과 계약 체결에 쓰이므로 이름·생년월일과 결합되면 신원 도용에 직결된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[LMNPRTVWXY][CFGHJKLMNPRTVWXYZ0-9]{8}[0-9]?` | `L01X00T47`, `L01X00T471` (`A01X00T47`, `L01X00T4`, `L01A00T47`(모음 포함)은 거부) | score 사용 고려. 첫 문자 10종과 자음 전용 문자 집합이 필터 역할을 하지만, 9자리 영숫자는 제품 코드와 겹칠 수 있다. 체크 디지트가 동반된 10자리 매치는 `mrz_731` 검증기로 확인 가능. `boundary_check: true` 적용 |

    오탐: 중간. 대문자만 허용하므로 일반 텍스트와의 충돌은 제한적이다.
  - **byte-scan handwritten**: 가능. 오탐률은 regex + 검증기와 **동일**하다.
  - **Aho-Corasick**: 부적합. 첫 문자 10종은 1바이트 anchor 라 이득이 없다.
  - **권장**: regex + `mrz_731` 검증기(10자리 매치에만 적용. 9자리 매치는 검증 없이 통과시키되, 점수 체계 도입 후 낮은 점수 검토).
- **검증기**:
  - 현재: 없음
  - 구현 가능: ICAO 9303 MRZ 체크 디지트. 앞 9자리 각 문자를 숫자는 그대로, 문자는 `A`=10 … `Z`=35 로 바꾸고 가중치 `7 3 1` 을 순환 적용해 합한 뒤 10으로 나눈 나머지가 10번째 자리와 같으면 유효하다. 검증기 `mrz_731` 로 구현하면 여권 등 다른 국가의 MRZ 기반 번호에도 재사용할 수 있다. 매치가 9자리이면 검증기가 적용할 대상이 없으므로 통과시킨다.
- **채택 여부 및 근거**: 채택. 법이 이용을 명시적으로 제한하는 번호이다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `personalausweis`, `ausweisnummer`, `ausweis-nr`, `seriennummer`, `identity card`, `id card`, `npa`, `aufenthaltstitel`

### de_passport

- **설명**: Reisepass(여권) 일련번호. 2007년 이후 발급되는 전자여권은 9자리 영숫자이며 첫 문자는 여권 발급 관청 식별 문자(`C`, `F`, `G`, `H`, `J`, `K` 중 하나. 목록 확인 필요)이고 나머지는 신분증과 같은 문자 집합이다. MRZ 에 10번째 체크 디지트가 붙는다.
  - 예시: `C01X00T47` (형식 예시), `C01X00T478` (체크 디지트 `8` 포함, 7-3-1 규칙 통과)
- **법적 근거**:
  - 법령: PassG 제16조 (일련번호 이용 제한, PAuswG 제20조와 동일 취지), GDPR 제87조
  - 감독기관: 연방 내무부, BfDI
  - 노출 금지 이유: 신분증과 같다. 항공·호텔·출입국 기록과 연결된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[CFGHJK][CFGHJKLMNPRTVWXYZ0-9]{8}[0-9]?` | `C01X00T47`, `C01X00T478` (`L01X00T47` 은 신분증이므로 이 패턴에서 거부) | score 사용 고려. 신분증과 같은 이유. `boundary_check: true` 적용 |

    오탐: 중간. 신분증 패턴과 첫 문자 집합이 겹치지 않으므로 두 recognizer 가 동시에 매치되지 않는다.
  - **byte-scan handwritten**: 가능하지만 이득이 없다.
  - **Aho-Corasick**: 부적합.
  - **권장**: regex + `mrz_731` 검증기(10자리 매치에만).
- **검증기**: 신분증과 동일(`mrz_731`).
- **채택 여부 및 근거**: 채택. PassG 가 이용을 제한한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `reisepass`, `passnummer`, `pass-nr`, `passport`, `reisepassnummer`

### de_health_insurance_number

- **설명**: Krankenversichertennummer (KVNR). SGB V 제290조(2004년 GMG 개정)에 근거해 GKV(공적 건강보험) 피보험자에게 평생 불변으로 부여되는 10자리 번호로(실제 부여 개시 시점과 PKV 확대 연도는 확인 필요), 대문자 1자 + 숫자 9자리이며 마지막 자리가 체크 디지트이다. 건강보험 카드(eGK)에 인쇄되고 전자 처방·진료 기록의 연결 키이다. 민간 보험(PKV)도 같은 체계를 쓴다.
  - 예시: `A123456780`, `Q123456784` (계산으로 만든 형식 예시. 체크 디지트를 통과한다)
- **법적 근거**:
  - 법령: SGB V 제290조 (구조와 이용), GDPR 제9조 (건강정보는 특수 범주), BDSG 제22조
  - 감독기관: GKV-Spitzenverband, BfDI
  - 노출 금지 이유: 건강정보의 연결 키이므로 GDPR 특수 범주 데이터와 직결된다. 번호로 전자 처방·진료 기록 조회가 가능하다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z][0-9]{9}` | `A123456780`, `Q123456784` (`A12345678`, `AB12345678` 은 거부) | score 사용 고려. 대문자 1자 + 숫자 9자리는 제품·주문 코드와 겹치므로 `de_kvnr` 검증기 병행이 필요하다. 검증기 없이 등록한다면 score 사용 필요. `boundary_check: true` 적용 |

    오탐: 검증기 없이는 높고, 검증기를 붙이면 1/10 로 준다. `L012345678` 처럼 `L`·`M`·`N` 등으로 시작하는 문자 1 + 숫자 9 는 `de_id_card` 의 10자리 형태와 동시에 매치되며, 동일 span 은 둘 다 남으므로 겹침 해소가 점수에 좌우된다. 두 검증기(`de_kvnr`, `mrz_731`)를 모두 통과하는 값은 드물어 실제 충돌은 적다.
  - **byte-scan handwritten**: 가능. 오탐률은 regex + `de_kvnr` 조합과 **동일**하다.
  - **Aho-Corasick**: 부적합.
  - **권장**: regex + `de_kvnr` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크 디지트. 첫 문자를 알파벳 순번 2자리(`A`=01 … `Z`=26)로 바꿔 숫자 10자리(순번 2자리 + 가운데 8자리)를 만들고, 왼쪽부터 가중치 `1 2 1 2 …` 를 곱한 각 곱의 자릿수 합을 모두 더해 10으로 나눈 나머지가 마지막 자리와 같으면 유효하다. 검증기 `de_kvnr` 로 구현한다.
- **채택 여부 및 근거**: 채택. 특수 범주(건강) 데이터의 연결 키이고 검증기가 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `krankenversichertennummer`, `versichertennummer`, `kvnr`, `krankenkasse`, `gesundheitskarte`, `egk`, `versicherten-nr`, `health insurance`

### de_iban

- **설명**: 독일 IBAN. `DE` + 체크 디지트 2자리 + 은행 코드(BLZ) 8자리 + 계좌번호 10자리 = 22자리이며, 서면에서는 4자리씩 띄어 쓴다. IBAN 은 ISO 13616 국제 표준이고 mod 97 체크섬은 모든 국가에 공통이다. 독일은 2014년 SEPA 전환 이후 BLZ + Kontonummer 대신 IBAN 만 쓴다.
  - 예시: `DE89370400440532013000`, `DE89 3704 0044 0532 0130 00` (독일 은행·위키백과가 형식 설명에 쓰는 견본 IBAN. mod 97 검증을 통과한다)
- **법적 근거**:
  - 법령: GDPR 제4조 (개인 계좌 IBAN 은 개인정보), GwG·ZAG (금융 거래 정보), BDSG
  - 감독기관: BaFin, BfDI
  - 노출 금지 이유: IBAN 만으로 SEPA 자동이체(Lastschrift) 위조가 가능하다. 독일에서 계좌 정보는 이름·주소 다음으로 흔히 유출되는 항목이다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `DE[0-9]{2} ?([0-9]{4} ?){4}[0-9]{2}` | `DE89370400440532013000`, `DE89 3704 0044 0532 0130 00` (`DE8937040044053201300`(21자리), `FR76…` 은 거부) | 기본. `DE` 접두와 22자리 고정 길이로 오탐이 낮고 `iban` 검증기로 더 낮아진다. `boundary_check: true` 적용 |

  - **byte-scan handwritten**: 가능하나 이득이 없다.
  - **Aho-Corasick**: **적합**. anchor `DE` 는 2바이트라 단독으로는 흔하지만, 공통 IBAN detector 로 확장하면 `DE`, `FR`, `GB`, `IT`, `ES`, `PL` … 국가 코드 + 숫자 2자리를 anchor 로 등록하고 verifier 가 국가별 길이와 mod 97 을 검사하는 구조가 자연스럽다. 이 문서 범위의 13개국 중 IBAN 국가는 독일·영국·프랑스·이탈리아·스페인·폴란드·브라질(`BR`, 29자리) 7개국이다.
  - **권장**: 공통 `iban` recognizer(Aho-Corasick 또는 regex) + `iban` 검증기로 통합. 국가별 문서에서는 길이와 예시만 기록한다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: ISO 7064 mod 97-10. 앞 4자리(국가 코드 + 체크 디지트)를 뒤로 옮기고 문자를 `A`=10 … `Z`=35 로 바꾼 뒤 정수로 읽어 97로 나눈 나머지가 1이면 유효하다. 검증기 `iban` 으로 구현하며 모든 IBAN 국가에 공통이다.
- **채택 여부 및 근거**: 조건부 채택. 독일 계좌 정보로서 채택 대상이지만, IBAN 은 국제 표준이므로 `de_` 접두 대신 공통 항목 `iban` 으로 이관하는 것이 맞다. 다른 EU 국가 문서 작성 후 최종 결정한다.
- **기존 구현 여부**: 신규 (YAML 에 IBAN recognizer 가 전혀 없음)
- **context_words 후보**: `iban`, `kontonummer`, `konto`, `bankverbindung`, `überweisung`, `lastschrift`, `sepa`, `bic`, `bank`

### de_phonenumber

- **설명**: 독일 전화번호. 국가번호 `+49`, 국내 접두 `0`. 휴대전화는 `015x`, `016x`, `017x` 로 시작하고 접두 뒤 7-8자리이다(예: `0151 12345678`). 유선은 지역번호가 2-5자리(`030` 베를린, `089` 뮌헨, `0221` 쾰른 등 약 5,200개)이고 가입자 번호가 3-8자리라 총 길이가 일정하지 않다. 표기도 `030 12345678`, `030/12345678`, `(030) 1234-5678`, `+49 30 12345678` 로 다양하다.
  - 예시: 휴대전화 `0151 12345678`, `+49 151 12345678`, `015112345678`, `0176/1234567`. 유선 `030 12345678`, `+49 30 12345678`, `089/1234567`, `0221-123456`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: GDPR 제4조, TKG (가입자 정보), TDDDG (구 TTDSG, 통신 비밀), UWG 제7조 (동의 없는 전화 광고 금지)
  - 감독기관: Bundesnetzagentur, BfDI
  - 노출 금지 이유: 휴대전화번호는 2단계 인증·메신저 계정의 열쇠이고, 유선번호는 주소와 결합해 개인을 특정한다. 고유식별번호는 아니므로 위험도는 위 항목들보다 낮다.
- **결정론적 검출 가능성**: 휴대전화는 가능, 유선은 가능하나 매우 약하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `(\+49 ?\|0)1[5-7][0-9][ /-]?[0-9]{7,8}` | `0151 12345678`, `+49 151 12345678`, `015112345678`, `0176/1234567`, `+4915112345678` (`0141 12345678`, `0151 123456` 은 거부) | score 사용 고려. `015`-`017` 접두와 11-12자리 길이가 필터이다. 구분자 없는 형태는 다른 숫자열과 겹칠 수 있다. `boundary_check: true` 적용 |
    | `(\+49 ?\|0)[2-9][0-9]{1,4}[ /-]?[0-9]{3,8}` | `030 12345678`, `+49 30 12345678`, `089/1234567`, `0221-123456`, `03012345678` (`01 12345678` 은 거부. `(030) 1234-5678` 괄호 표기는 이 패턴이 잡지 못함) | **score 사용 필요**. `0` + 5-13자리 숫자는 우편번호·주문번호·날짜와 광범위하게 겹친다. 지역번호 표(5,200개)를 넣으면 좁아지지만 DFA 가 커진다 |

    오탐: 휴대전화는 중간, 유선은 높다.
  - **byte-scan handwritten**: 가능. 유선번호는 지역번호 표(5,200개)를 코드 표로 두고 대조하면 regex 로 넣을 때의 DFA 비대화를 피할 수 있다. 오탐률은 지역번호 표를 쓴 regex 와 **동일**하다.
  - **Aho-Corasick**: 휴대전화에 **적합**. `kr_phonenumber` 의 `010` 과 같은 구조로 anchor `015`, `016`, `017`, `+49` 를 등록하고 verifier 가 뒤따르는 구분자와 7-8자리를 검사한다. 기존 automaton 에 추가하면 텍스트를 한 번만 스캔한다. 유선번호는 고정 접두가 `0` 뿐이라 부적합하다.
  - **권장**: 휴대전화는 Aho-Corasick(또는 regex), 유선은 점수 체계 도입 후 낮은 `score` 의 별도 recognizer(`de_phonenumber_landline`).
- **검증기**:
  - 현재: 없음
  - 구현 가능: 휴대전화는 접두 표 외 규칙 없음. 유선은 Bundesnetzagentur 의 지역번호 목록(ONB) 대조가 가능하다(목록은 수시로 바뀌므로 최신 공고로 재확인 필요).
- **채택 여부 및 근거**: 휴대전화는 채택. 유선은 채택하되 점수 체계 도입이 선행 조건이며 그 전에는 등록하지 않는다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `telefon`, `telefonnummer`, `handy`, `handynummer`, `mobil`, `mobilnummer`, `rufnummer`, `tel`, `festnetz`, `anrufen`, `whatsapp`, `phone`

### de_vehicle_plate

- **설명**: Kfz-Kennzeichen(차량 번호판). `지역 코드 1-3자 + 구분(공백 또는 하이픈) + 식별 문자 1-2자 + 숫자 1-4자리` 구조이며, 전기차는 끝에 `E`, 클래식카는 `H` 가 붙는다(예: `B-MW 1234`, `M-AB 123`, `LÖ-X 1`). 지역 코드는 약 700개이고 일부는 움라우트(`LÖ` 뢰라흐, `TÜ` 튀빙겐, `BÖ` 뵈르데)를 포함한다. 식별 문자와 숫자 사이의 공백은 관례이며 생략되기도 한다.
  - 예시: `B-MW 1234`, `M-AB 123`, `LÖ-X 1`, `HH-AB 12E`, `B MW 1234`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: StVG 제39조 (보유자 정보 조회 조건), FZV 제8조·제10조 (번호판 배정. 2023년 9월 개정 FZV 에서 조문 번호 이동 여부 확인 필요), GDPR 제4조. 독일 감독기관(DSK)과 판례는 번호판을 보유자와 결합 가능한 개인정보로 본다.
  - 감독기관: KBA, 각 주 감독기관
  - 노출 금지 이유: 번호판으로 KBA 중앙 차량 등록부에서 보유자 정보를 조회할 수 있고(StVG 제39조의 조건 하에), 주차·통행 기록과 결합하면 위치 추적이 가능하다. 공개적으로 노출되는 번호이므로 단독 위험도는 낮다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `([A-Z]\|Ä\|Ö\|Ü){1,3}[- ][A-Z]{1,2} ?[0-9]{1,4}[EH]?` | `B-MW 1234`, `M-AB 123`, `LÖ-X 1`, `HH-AB 12E`, `B MW 1234` (`ABCD-MW 1234`, `B-MWX 1234`, `B-MW 12345` 는 거부) | score 사용 고려. `대문자 1-3 + 구분자 + 대문자 1-2 + 숫자` 는 제품 코드(`AB-CD 12`)와 겹칠 수 있다. 지역 코드 표(700개)를 리터럴 대안으로 넣으면 좁아지지만 DFA 가 커진다. 움라우트는 문자 클래스에 넣을 수 없어 리터럴 대안으로 썼다. `boundary_check: true` 적용(움라우트는 비ASCII 라 경계 검사에 영향 없음) |

    오탐: 중간. 공백 구분(`B MW 1234`)을 허용하면 `DIN EN 1234`, `BMW X5`, `VW T4` 같은 흔한 독일어 표기가 그대로 매칭된다(Python 으로 확인). 초기 등록은 하이픈 구분만 허용하는 것을 권장한다. `ABCD-MW 1234` 의 거부는 regex 자체가 아니라 `boundary_check` 가 부분 매치 `BCD-MW 1234` 를 버리기 때문이다.
  - **byte-scan handwritten**: **적합**. 지역 코드 700개를 코드 표로 두고 대조하면 regex 보다 정밀하면서 DFA 비대화를 피한다. 오탐률은 지역 코드 표를 쓴 regex 와 **동일**하다.
  - **Aho-Corasick**: 지역 코드 + 구분자(`B-`, `M-`, `HH-` …)를 anchor 로 등록하는 것이 가능하나, 1-2바이트 코드가 많아 verifier 호출이 잦다.
  - **권장**: 초기에는 regex(지역 코드 표 없이)를 기본 점수로 등록하되 하이픈 구분만 허용해 오탐을 줄이고, 점수 체계 도입 후 낮은 `score` 로 전환한다. 정밀도가 필요해지면 byte-scan + 지역 코드 표.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 지역 코드 표(KBA 공고, 약 700개) 대조가 유일한 검증이다.
- **채택 여부 및 근거**: 채택. 감독기관이 개인정보로 보고 형식이 비교적 특이하다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `kennzeichen`, `kfz-kennzeichen`, `nummernschild`, `autokennzeichen`, `fahrzeug`, `kfz`, `pkw`, `license plate`

### de_driver_license

- **설명**: Führerscheinnummer(운전면허번호). 1999년 이후 카드형 면허증에 11자리 영숫자로 인쇄된다(예: `B072RRE2I55`). 구조는 발급 관청 코드 + 일련번호 + 체크 디지트 + 발급 회차로 알려져 있으나, 각 부분의 자릿수와 체크 디지트 알고리즘은 공개 명세를 확인하지 못했다(확인 필요).
  - 예시: `B072RRE2I55` (형식 예시. 구조가 확인되지 않아 검증하지 않았다)
- **법적 근거**:
  - 법령: StVG 제2조, FeV, GDPR 제4조
  - 감독기관: KBA, 각 주 운전면허 관청
  - 노출 금지 이유: 신원 확인 서류로 쓰이며 KBA 중앙 운전면허 등록부와 연결된다.
- **결정론적 검출 가능성**: 가능하나 형식이 확인되지 않았다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z0-9]{11}` | `B072RRE2I55` | **score 사용 필요**. 11자리 영숫자는 해시·일련번호·토큰과 광범위하게 겹친다. 구조 명세가 확인되면 자리별 문자 집합으로 좁힌다 |

  - **byte-scan handwritten**: 구조 명세 확인 후 판단.
  - **Aho-Corasick**: 부적합.
  - **권장**: 형식 명세 확인 후 결정. 그 전에는 등록하지 않는다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 확인 필요.
- **채택 여부 및 근거**: 조건부 채택. GDPR 상 개인정보이고 신원 서류이지만, 형식 명세를 확인하지 못해 오탐을 제어할 수 없다. 명세 확인이 조건이다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `führerschein`, `fuehrerschein`, `führerscheinnummer`, `fahrerlaubnis`, `driver's license`, `driving licence`

### de_tax_number

- **설명**: Steuernummer. 관할 세무서(Finanzamt)가 납세자·사업자에게 부여하는 번호로, 주(Land)마다 `12/345/67890`, `181/815/08155` 처럼 형식이 다르고(10-11자리 숫자, 슬래시 구분), ELSTER 전자신고용으로는 13자리 통일 형식(`1121081508150`)이 있다. 이사하면 바뀌며 IdNr 로 대체되는 과정에 있다.
  - 예시: `12/345/67890`, `181/815/08155`, `1121081508150`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: AO 제30조 (조세 비밀). 그러나 UStG 제14조가 송장에 Steuernummer 또는 USt-IdNr 기재를 의무화하므로 사업자의 번호는 준공개이다.
  - 감독기관: 각 주 재무부, 세무서
  - 노출 금지 이유: 약하다. 개인 납세자의 번호는 세무 서류에만 나타나지만, 사업자의 번호는 모든 송장에 인쇄된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{2,3}/[0-9]{3,4}/[0-9]{4,5}` | `12/345/67890`, `181/815/08155` | score 사용 고려. 슬래시 구분 숫자는 날짜·분수와 겹칠 수 있다. 미채택 항목 |
    | `[0-9]{13}` | `1121081508150` | **score 사용 필요**. 13자리 숫자열. 미채택 항목 |

  - **byte-scan handwritten**: 가능하나 이득 없음.
  - **Aho-Corasick**: 부적합.
  - **권장**: (채택 시) 슬래시 형식만 regex.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음(주별로 내부 규칙이 있다는 자료가 있으나 공개 명세 없음).
- **채택 여부 및 근거**: 미채택 (보류). 송장 기재 의무 때문에 준공개인 번호이고 IdNr 로 대체 중이다. 개인 납세자 보호 요구가 생기면 재검토한다.
- **기존 구현 여부**: 신규 (미채택이므로 구현하지 않음)
- **context_words 후보** (재검토 시 참고): `steuernummer`, `steuer-nr`, `st-nr`, `finanzamt`

## 4. 검토 후 미채택한 항목

아래 항목은 법령상 PII 이거나 식별번호이지만 결정론적 검출이 불가능하거나 공개 번호라서 recognizer 로 등록하지 않는다.

| 항목 | 법적 근거 | 미채택 이유 |
|---|---|---|
| Umsatzsteuer-Identifikationsnummer (USt-IdNr, `DE123456789`) | UStG 제27a조 | 사업자 번호이며 EU VIES 에서 누구나 조회할 수 있는 공개 번호이다. |
| Handelsregisternummer (`HRB 12345`) | HGB | 법인 등기번호이며 공개 정보이다. |
| Postleitzahl (5자리 우편번호) | GDPR | 5자리 숫자는 다른 숫자열과 구분되지 않고 단독 식별력이 낮다. |
| Bankleitzahl + Kontonummer (구 계좌 표기, `37040044 / 0532013000`) | GwG | 2014년 SEPA 전환 이후 IBAN 으로 대체되었고, 8자리 + 10자리 숫자는 구분자 없이는 검출 불가하다. |
| Zugangsnummer (CAN, 신분증 접근번호 6자리) | PAuswG | 6자리 숫자만으로 구분 불가하다. |
| Personenkennziffer (연방군 인식번호) | Soldatengesetz | 형식이 `DDMMYY-L-NNNNN` 으로 알려져 있으나 공개 명세가 없고 대상 인구가 적다. |
| 주소, 이름, 생년월일 | GDPR 제4조 | 국가 종속 항목이 아니며 regex 로 결정론적 검출이 불가능하다. 공통 항목 또는 NER 로 다룬다. |
| 생체정보, 종교(Kirchensteuer 항목), 건강 상태 | GDPR 제9조, BDSG 제22조 | 특수 범주이지만 번호 형태로 나타나지 않는다. |
| 신용카드번호, 이메일, IP 주소 | GDPR, PCI DSS | 국가 종속 항목이 아니므로 이 문서 범위 밖이다. 기존 `card_number` 등이 담당한다. |

## 5. 구현 시 후속 작업 요약

이 문서에서 도출된, YAML·`validator.rs`·`handwritten/`·엔진에 반영할 작업 목록이다. 검증기는 **함수 구현 → YAML 등록** 순서를 지킨다(`validator::validate` 가 fail-open 이므로 순서가 바뀌면 검증 없이 통과한다).

| 순서 | 작업 | 대상 | 종류 |
|---|---|---|---|
| 선행 | recognizer 단위 `score` 필드와 context 가산 방식 도입 (en_US 문서 5절과 공통. 이미 완료되었으면 이 행 삭제) | 엔진 | 엔진 변경 |
| 1 | `de_idnr` 검증기(반복 규칙 + ISO 7064 변형 체크 디지트)와 `de_tax_id` recognizer 추가 | de_tax_id | validator 신규, YAML 신규 |
| 2 | `de_svnr` 검증기(가중 교차합)와 `de_social_security_number` recognizer 추가 | de_social_security_number | validator 신규, YAML 신규 |
| 3 | `mrz_731` 검증기(ICAO 9303, 10자리 매치에만 적용)와 `de_id_card`·`de_passport` recognizer 추가. 문자 집합과 첫 문자 목록은 연방 인쇄국 명세로 확인 | de_id_card, de_passport | validator 신규, YAML 신규 |
| 4 | `de_kvnr` 검증기와 `de_health_insurance_number` recognizer 추가 | de_health_insurance_number | validator 신규, YAML 신규 |
| 5 | (공통 항목 이관 확정 시) 공통 `iban` 검증기(mod 97)와 `iban` recognizer 추가. 국가 코드별 길이 표(`DE` 22, `BR` 29 등) 포함. Aho-Corasick 으로 국가 코드 anchor 등록 검토 | iban (공통) | validator 신규, YAML 신규 또는 handwritten 신규 |
| 6 | `de_phonenumber` 휴대전화 recognizer 추가 (Aho-Corasick anchor `015`/`016`/`017`/`+49` 또는 regex) | de_phonenumber | handwritten 수정 또는 YAML 신규 |
| 7 | `de_phonenumber_landline` recognizer 추가 (`score` 낮게). **선행 작업 완료 후에만** | de_phonenumber | YAML 신규 |
| 8 | `de_vehicle_plate` recognizer 추가 (움라우트는 리터럴 대안, 초기에는 하이픈 구분만). 낮은 `score` 전환은 선행 작업 후. 정밀도 필요 시 지역 코드 표 기반 byte-scan | de_vehicle_plate | YAML 신규 (또는 handwritten 신규) |
| 9 | `de_driver_license` 형식 명세 확인 후 등록 여부 결정 | de_driver_license | 조사 |
| 선택 | `de_kvnr` 검증기는 `de_svnr` 와 같은 "문자→순번 2자리 + 가중 교차합" 계열이므로 공용 helper 로 구현 | validator | validator 리팩터 |
