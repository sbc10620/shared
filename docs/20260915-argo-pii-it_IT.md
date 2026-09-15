# PII 목록: it_IT (이탈리아)

이 문서는 `tinicore/src/guardrails/config/pii_filter_config.yaml` 에 이탈리아(it_IT) 고유 PII recognizer 가 포함되어야 하는 근거를 기록한다. 이미 YAML 에 있는 항목도 근거를 남기기 위해 포함하며, 국가에 종속되지 않는 항목(카드번호, API 키, 비밀번호, 이메일, IP 주소 등)은 다루지 않는다. 2026-09-15 현재 YAML 에 `it_*` recognizer 는 하나도 없으므로 이 문서의 모든 항목은 신규이다.

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

엔진은 DFA 를 `MatchKind::All` 로 빌드해 겹치는 모든 매치 끝을 보고한 뒤 boundary check 와 dedup 으로 가장 긴 것을 남긴다. 엔진이 `unicode(false)` 로 DFA 를 빌드하므로 악상 문자는 문자 클래스에 넣을 수 없으나(ko_KR·de_DE 문서 참조), 이 문서의 regex 는 모두 ASCII 만 쓴다. Codice Fiscale·Partita IVA·IBAN mod 97 의 체크섬과 형식 규칙은 python-stdnum 2.2 의 `stdnum.it.codicefiscale`, `stdnum.it.iva`, `stdnum.iban` 구현과 대조했다. IBAN 의 CIN 은 stdnum 에 구현이 없어 자체 계산으로 ISO 견본 1건만 재현했다.

## 1. 적용 법령 및 감독기관

이탈리아는 EU 회원국이므로 GDPR 이 직접 적용되고, 개인정보 보호법전(Codice in materia di protezione dei dati personali, D.Lgs. 196/2003, 2018년 D.Lgs. 101/2018 로 GDPR 에 맞게 개정)이 국내 이행법이다. 감독기관은 Garante per la protezione dei dati personali(이하 Garante) 단일 기관이다. 이탈리아 법제의 특징은 **Codice Fiscale(세금 코드)이 사실상 범용 국가 식별번호**라는 점이다. DPR 605/1973 이 모든 행정·금융·의료 거래에 이 코드의 기재를 의무화했고, 코드 안에 성명·성별·생년월일·출생지가 인코딩되어 있어 코드 자체가 개인정보를 드러낸다. GDPR 제87조가 위임한 국가 식별번호 규율은 Codice Privacy 제2-ter조(공익 목적 처리)와 Garante 의 일반 조치로 이루어진다.

| 법령 | 감독기관 | 적용 범위 요약 |
|---|---|---|
| GDPR (Regulation (EU) 2016/679) 제4조, 제9조, 제32조, 제87조 | Garante per la protezione dei dati personali | 개인정보 정의, 특수 범주, 처리 보안, 국가 식별번호 이용 조건 위임 |
| Codice in materia di protezione dei dati personali (D.Lgs. 196/2003, D.Lgs. 101/2018 개정) 제2-ter조, 제2-sexies조, 제2-septies조, 제130조 | Garante | 공익 목적 처리, 특수 범주(건강 등) 처리 조건, 건강 데이터 보호 조치, 원치 않는 통신(텔레마케팅) |
| DPR 605/1973 제6조 | Agenzia delle Entrate | Codice Fiscale 의 부여와 행정·금융·의료 거래에서의 기재 의무 |
| DPR 445/2000 제35조, 제36조 | 내무부 | 신분 증명 서류(carta d'identità, passaporto, patente 등)의 정의와 효력 |
| D.Lgs. 82/2005 (Codice dell'amministrazione digitale, CAD) 제66조; D.L. 78/2015 제10조 | 내무부, IPZS (국립 인쇄국) | 전자 신분증(CIE) |
| Codice della strada (D.Lgs. 285/1992) 제93조, 제94조, 제100조, 제116조 | 교통부 (Motorizzazione), ACI (PRA) | 차량 등록(제93조), PRA 전사(제94조), 번호판, 운전면허 |
| Testo unico bancario (D.Lgs. 385/1993); D.Lgs. 231/2007 (자금세탁 방지) | Banca d'Italia, UIF | 은행 거래 정보, 계좌 식별자(IBAN) 취급 |
| Codice delle comunicazioni elettroniche (D.Lgs. 259/2003); Legge 5/2018 및 DPR 26/2022 (Registro pubblico delle opposizioni, 구 DPR 178/2010 대체) | AGCOM, Garante | 통신 가입자 정보, 텔레마케팅 거부 등록부 |
| D.L. 269/2003 제50조; D.M. 11 marzo 2004 | 경제재정부 (MEF), Sogei | Tessera Sanitaria(건강 카드) 발급과 번호 |
| DPR 633/1972 제35조 | Agenzia delle Entrate | Partita IVA 부여. VIES 에서 공개 조회 가능 |

## 2. 요약 표

| pii_type | 설명 | 결정론적 검출 | 권장 검출 방식 | 검증기 (현재 / 구현 가능) | score | 기존 구현 | 채택 |
|---|---|---|---|---|---|---|---|
| it_codice_fiscale | 세금 코드 (Codice Fiscale, 개인 16자리) | 가능 (형식 엄격) | regex (+ `it_cf` 검증기) | 없음 / 홀짝 가중 mod 26 체크 문자 | 기본 | 신규 | 채택 |
| it_id_card | 신분증 번호 (CIE `CA12345AB`, 구형 종이 `AA1234567`) | 가능 | regex (+ `mrz_731`, 체크 디지트 동반 시) | 없음 / MRZ 7-3-1 (10자리 표기에만) | 사용 고려 | 신규 | 채택 |
| it_passport | 여권번호 (`YA1234567`) | 가능 | regex (+ `mrz_731`, 체크 디지트 동반 시) | 없음 / MRZ 7-3-1 (10자리 표기에만) | 사용 고려 | 신규 | 채택 (구형 신분증과 동일 형식이므로 통합 검토) |
| it_driver_license | 운전면허번호 (patente) | 가능 (형식 확인 필요) | regex | 없음 / 확인 필요 | **사용 필요** | 신규 | 조건부 채택 (형식 명세 확인 후) |
| it_health_card | 건강 카드 번호 (Tessera Sanitaria, 20자리, `8038` 시작) | 가능 | Aho-Corasick handwritten (anchor `8038`) 또는 regex | 없음 / 확인 필요 | 기본 | 신규 | 채택 |
| it_iban | 이탈리아 IBAN (CIN 포함) | 가능 | regex 또는 Aho-Corasick (+ `iban` 검증기, `it_cin` 검증기) | 없음 / ISO 7064 mod 97-10, CIN 문자 | 기본 | 신규 | 조건부 채택 (공통 항목 `iban` 으로 이관 검토, CIN 은 이탈리아 고유) |
| it_phonenumber (recognizer `it_phonenumber`) | 휴대전화번호 (`3XX`) | 가능 | regex (Aho-Corasick 은 `+39` 만) | 없음 / 없음 | 사용 고려 | 신규 | 채택 |
| it_phonenumber (recognizer `it_phonenumber_landline`) | 유선전화번호 (`0X`) | 가능 (약함) | regex | 없음 / 지역번호 표 | **사용 필요** | 신규 | 채택 (점수 체계 도입이 선행 조건) |
| it_vehicle_plate | 차량 번호판 (`AA 123 BB`) | 가능 | regex | 없음 / 없음 (문자 집합은 regex 에 포함) | 기본 | 신규 | 채택 |
| it_partita_iva | 부가세 번호 (Partita IVA, 11자리) | 가능 | regex (+ `luhn` + 지방 코드 표) | `luhn` (기존) / 지방 코드 표 추가 | 사용 고려 | 신규 | 미채택 (보류) |

이외에 검토했으나 결정론적 검출이 불가능하거나 공개 번호라서 미채택한 항목은 4절에 정리했다.

## 3. 항목별 상세

### it_codice_fiscale

- **설명**: Codice Fiscale (CF). Agenzia delle Entrate 가 모든 개인에게 부여하는 16자리 영숫자 코드로, 구조는 `성 3자 + 이름 3자 + 출생 연도 2자리 + 출생 월 1자(A=1월 … T=12월, `ABCDEHLMPRST`) + 출생 일 2자리(여성은 +40) + 출생지 코드 4자(문자 1 + 숫자 3, Belfiore 코드) + 체크 문자 1자` 이다. 같은 코드가 생기는 경우(omocodia)에는 숫자 자리를 오른쪽부터 문자 `L M N P Q R S T U V`(0-9 대응)로 바꾼다. 법인은 11자리 숫자 코드를 쓰며 대개 Partita IVA 와 같은 번호이다(항상 같지는 않다). 건강 카드·신분증·급여명세서·계약서에 예외 없이 인쇄된다.
  - 예시: `RSSMRA85T10A562S` (이탈리아 행정 안내에서 관용적으로 쓰는 가상 인물 Mario Rossi 형식 예시. 체크 문자 `S` 통과), `RCCMNL83S18D969H` (python-stdnum 문서 예시), `RSSMRA85T10A56NH` (omocodia 치환 예시. 출생지 숫자 `2` 가 `N` 으로 바뀌고 체크 문자가 `H` 로 재계산됨)
- **법적 근거**:
  - 법령: DPR 605/1973 제6조 (기재 의무), Codice Privacy 제2-ter조, GDPR 제87조. Garante 는 CF 를 "식별 코드" 범주의 개인정보로 다루며, 공개 게시(예: 웹사이트에 CF 공개)에 대해 반복적으로 제재해 왔다.
  - 감독기관: Garante, Agenzia delle Entrate
  - 노출 금지 이유: 이탈리아의 범용 식별자이자 성명·성별·생년월일·출생지를 그대로 담고 있다. CF + 신분증 번호 조합이 계약·은행·통신 본인확인의 기준이라 신원 도용에 직결된다.
- **결정론적 검출 가능성**: 가능하며 형식이 엄격하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]` (python-stdnum 의 검증 regex 와 동일) | `RSSMRA85T10A562S`, `RCCMNL83S18D969H`, `RSSMRA85T10A56NH` (월 문자 `F`, 15자리, 소문자는 거부) | 기본. 16자리 안에서 문자·숫자 위치와 월 문자 집합이 고정되어 우연히 맞기 어렵고, `it_cf` 검증기(1/26)로 더 낮아진다. `boundary_check: true` 적용 |

    오탐: 낮다. 대문자 16자리 영숫자가 이 위치 규칙까지 만족하는 일반 텍스트는 드물다. 소문자 입력을 잡으려면 `(?i)` 를 붙이되 검증기 계산 전에 대문자로 바꿔야 한다.
  - **byte-scan handwritten**: 가능. 16자리 영숫자열을 뽑아 자리별 문자 집합과 체크 문자를 코드로 검사한다. 오탐률은 regex + `it_cf` 조합과 **동일**하다. 단일 패턴이라 메모리 이점이 없다.
  - **Aho-Corasick**: 부적합. 접두가 성의 자음 3자라 고정 리터럴이 없다.
  - **권장**: regex + `it_cf` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크 문자. 앞 15자를 왼쪽부터 1번으로 세어, **홀수 자리**는 특수 표(`0`-`9` → 1 0 5 7 9 13 15 17 19 21, `A`-`Z` → 1 0 5 7 9 13 15 17 19 21 2 4 18 20 11 3 6 8 12 14 16 10 22 25 24 23), **짝수 자리**는 `0`-`9` → 0-9, `A`-`Z` → 0-25 로 바꿔 합한 뒤 26으로 나눈 나머지를 `A`-`Z` 로 바꾼 것이 16번째 문자와 같으면 유효하다. omocodia 치환 문자는 regex 가 이미 허용하고, 체크 문자 계산은 치환된 문자 그대로 한다. 생년월일 유효성(월 문자, 일 1-31 또는 41-71)도 함께 검사할 수 있다. 검증기 `it_cf` 로 구현한다.
- **채택 여부 및 근거**: 채택. 이탈리아의 최고 등급 식별자이며 강한 검증기가 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `codice fiscale`, `cod. fiscale`, `c.f.`, `cf:`, `fiscal code`, `tax code`, `tessera sanitaria`, `agenzia delle entrate`

### it_id_card

- **설명**: 신분증(carta d'identità) 번호. 2016년부터 발급되는 전자 신분증 CIE 는 `대문자 2 + 숫자 5 + 대문자 2`(예: `CA12345AB`)이고, 구형 종이 신분증은 `대문자 2 + 숫자 7`(예: `AA1234567`, 공백을 넣어 `AA 1234567` 로도 표기)이다. 구형은 2016년 이후 순차 폐지 중이나 유효 기간이 남은 것이 아직 유통된다. 번호 자체에 체크섬은 없고 CIE 의 MRZ 에 체크 디지트가 있다.
  - 예시: `CA12345AB` (CIE 형식 예시), `AA1234567`, `AA 1234567` (구형 형식 예시)
- **법적 근거**:
  - 법령: DPR 445/2000 제35조 (신분 증명 서류), CAD 제66조·D.L. 78/2015 제10조 (CIE), GDPR 제87조
  - 감독기관: 내무부, IPZS, Garante
  - 노출 금지 이유: CF 와 함께 본인확인의 두 축이다. 통신·은행·임대 계약에서 신분증 사본 제출이 관행이라 유출이 잦다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{2}[0-9]{5}[A-Z]{2}[0-9]?` | `CA12345AB`, `CA12345AB5` (`CA1234AB`, `CA123456AB` 는 거부) | score 사용 고려. `대문자 2 + 숫자 5 + 대문자 2` 는 비교적 특이하지만 제품·예약 코드와 겹칠 수 있다. 선택 꼬리 `[0-9]?` 는 MRZ 체크 디지트가 함께 적힌 10자리 표기용이며 de_DE·fr_FR 와 같이 10자리 매치에만 `mrz_731` 을 적용한다. `boundary_check: true` 적용 |
    | `[A-Z]{2} ?[0-9]{7}[0-9]?` | `AA1234567`, `AA 1234567`, `AA 12345678` | score 사용 고려. **여권 패턴과 동일 형식**이다(아래 `it_passport` 비고). 공백 허용 시 `AB 1234567` 같은 텍스트와 더 자주 겹친다. 선택 꼬리는 MRZ 체크 디지트 표기용 |

    오탐: 중간.
  - **byte-scan handwritten**: 가능하나 이득이 없다.
  - **Aho-Corasick**: 부적합. 고정 접두가 없다(CIE 의 첫 두 문자는 발급 순서에 따른 문자열이며 `CA`, `CB` … 로 증가한다는 자료가 있으나 확인 필요).
  - **권장**: regex. 구형 패턴은 여권과 하나의 recognizer 로 묶는 것을 검토한다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 번호 자체에는 없다. MRZ 체크 디지트가 동반된 10자리 표기는 `mrz_731`(de_DE 문서, ICAO 9303)로 검증한다.
- **채택 여부 및 근거**: 채택. 핵심 신분증이며 CIE 형식은 오탐이 제어 가능하다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `carta d'identità`, `carta di identità`, `documento d'identità`, `numero documento`, `identity card`. (`cie` 는 `società`·`efficiente` 에 포함되므로 ` cie ` 처럼 공백 포함 형태로 쓰거나 제외한다.)

### it_passport

- **설명**: 여권(passaporto) 번호. 2006년 이후 전자여권은 `대문자 2 + 숫자 7`(예: `YA1234567`)이다. 구형 종이 신분증과 형식이 같다.
  - 예시: `YA1234567` (형식 예시)
- **법적 근거**:
  - 법령: DPR 445/2000 제35조, Legge 1185/1967 (여권법), GDPR 제87조
  - 감독기관: 내무부 (Questura), 외교부, Garante
  - 노출 금지 이유: 신분증과 같다. 항공·호텔·출입국 기록과 연결된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{2}[0-9]{7}[0-9]?` | `YA1234567`, `YA12345678` | score 사용 고려. 구형 신분증 패턴의 부분집합이므로 같은 값이 두 recognizer 에 동시에 매치된다. 선택 꼬리는 MRZ 체크 디지트 표기용이며 10자리 매치에만 `mrz_731` 적용. `boundary_check: true` 적용 |

  - **byte-scan handwritten**: 가능하나 이득이 없다.
  - **Aho-Corasick**: 부적합. 첫 두 문자가 발급 시기별 문자열(`YA`, `YB` … 로 알려짐, 확인 필요)이라 목록이 열려 있다.
  - **권장**: regex. 구형 신분증과 같은 값을 잡으므로 `it_id_document` 같은 통합 `pii_type` 으로 묶거나, context_words 로 우선순위를 정하는 방안을 구현 시 결정한다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 번호 자체에는 없다. MRZ 체크 디지트가 동반된 10자리 표기는 `mrz_731` 로 검증한다.
- **채택 여부 및 근거**: 채택. 정부 발급 신분증 번호이다. 구형 신분증과의 통합 여부를 구현 시 결정한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `passaporto`, `numero passaporto`, `passport`, `n. passaporto`

### it_driver_license

- **설명**: 운전면허(patente di guida) 번호. 카드형 면허증의 번호는 10자리 영숫자로 알려져 있으나(예: `MI1234567X` 형태로 앞 2자가 발급 지방 약어라는 자료와, `U1X123456Z` 처럼 문자·숫자가 섞인 형태라는 자료가 있음), 공식 명세를 확인하지 못했다(확인 필요).
  - 예시: `MI1234567X` (형식 예시. 구조 미확인이라 검증하지 않았다)
- **법적 근거**:
  - 법령: Codice della strada 제116조, DPR 445/2000 제35조 (신분 증명 서류로 인정), GDPR 제4조
  - 감독기관: 교통부 (Motorizzazione Civile), Garante
  - 노출 금지 이유: 신분증 대용으로 널리 쓰인다.
- **결정론적 검출 가능성**: 가능하나 형식이 확인되지 않았다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z0-9]{10}` | `MI1234567X` | **score 사용 필요**. 10자리 영숫자는 해시·일련번호와 광범위하게 겹친다. 구조 확인 전에는 등록하지 않는다 |

  - **byte-scan handwritten**: 구조 확인 후 판단.
  - **Aho-Corasick**: 부적합.
  - **권장**: 형식 명세 확인 후 결정.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 확인 필요.
- **채택 여부 및 근거**: 조건부 채택. 형식 명세 확인이 조건이다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `patente`, `patente di guida`, `numero patente`, `driver's license`, `driving licence`

### it_health_card

- **설명**: Tessera Sanitaria (TS, 건강 카드) 번호. 카드 뒷면에 인쇄되는 20자리 숫자로 `80380` 으로 시작한다(`80` 은 보건 카드 식별자, `380` 은 이탈리아 국가 코드. 5자리 고정 여부는 확인 필요). 카드 앞면에는 소지자의 Codice Fiscale 이 함께 인쇄되므로 CF 가 실질적 식별자이고, 이 20자리는 카드 자체의 일련번호이다. 유럽 건강보험카드(EHIC/TEAM) 기능을 겸한다. 마지막 자리가 체크 디지트라는 자료가 있으나 알고리즘은 확인하지 못했다(확인 필요. 아래 예시는 Luhn 을 통과하지 않으므로, Luhn 으로 확인되면 예시를 다시 만든다).
  - 예시: `80380001234567890123`, `8038 0001 2345 6789 0123` (형식 예시)
- **법적 근거**:
  - 법령: D.L. 269/2003 제50조, D.M. 11 marzo 2004, Codice Privacy 제2-septies조 (건강 데이터), GDPR 제9조
  - 감독기관: MEF, Sogei, Garante
  - 노출 금지 이유: 건강보험 자격 증명에 쓰이고 카드 자체가 전자 건강기록(Fascicolo Sanitario Elettronico) 접근 수단(TS-CNS 인증)이므로, 번호는 특수 범주인 건강 데이터와 결합된 식별자이다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `8038 ?0[0-9]{3} ?[0-9]{4} ?[0-9]{4} ?[0-9]{4}` | `80380001234567890123`, `8038 0001 2345 6789 0123` (`80381…` 은 거부) | 기본. `80380` 고정 접두(4자리 그룹 표기 때문에 `8038` 과 `0` 사이에 공백 허용) + 20자리 고정 길이. 카드번호(16자리)와 길이가 달라 충돌하지 않는다. `boundary_check: true` 적용 |

    오탐: 낮다.
  - **byte-scan handwritten**: 불필요.
  - **Aho-Corasick**: **적합**. anchor `8038`(4바이트)은 `kr_phonenumber` 의 `010` 보다 길어 verifier 호출이 드물고, verifier 는 뒤따르는 `0` + 15자리(구분자 선택)만 검사하면 된다. 기존 automaton 에 추가하면 텍스트를 한 번만 스캔한다.
  - **권장**: Aho-Corasick(또는 regex).
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크 디지트 알고리즘 확인 필요. 확인되면 검증기 `it_ts` 로 구현한다.
- **채택 여부 및 근거**: 채택. 특수 범주(건강) 데이터의 접근 키이고 고정 접두 덕분에 오탐이 낮다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `tessera sanitaria`, `tessera`, `servizio sanitario`, `carta nazionale dei servizi`. (`ssn` 은 이탈리아에서 Servizio Sanitario Nazionale 의 약자이지만 en_US 의 `us_social_security_number` 가 같은 단어를 context 로 쓰므로, 이탈리아어 문맥의 `ssn` 이 미국 SSN 매치의 점수를 올리고 그 반대도 성립한다. context_words 는 recognizer 별로 독립이라 교차 오염은 없지만 혼동을 피하기 위해 이 항목에서는 제외한다. `asl`, `cns`, `team` 은 짧거나 일반어라 제외한다.)

### it_iban

- **설명**: 이탈리아 IBAN. `IT` + 키 2자리 + CIN 1자(대문자) + ABI(은행 코드) 5자리 + CAB(지점 코드) 5자리 + 계좌번호 12자리(영숫자) = 27자리이다. CIN(carattere di controllo interno)은 이탈리아 고유의 체크 문자로, IBAN 의 mod 97 키와 별도로 BBAN 22자리(ABI + CAB + 계좌)에서 계산된다. 서면에서는 `IT60 X054 2811 1010 0000 0123 456` 처럼 4자리씩 띄어 쓴다.
  - 예시: `IT60X0542811101000000123456`, `IT60 X054 2811 1010 0000 0123 456` (ISO 13616 IBAN 레지스트리의 이탈리아 견본. mod 97 통과, CIN `X` 통과를 python-stdnum 과 자체 계산으로 확인)
- **법적 근거**:
  - 법령: TUB (D.Lgs. 385/1993), D.Lgs. 231/2007, GDPR 제4조, Codice Privacy
  - 감독기관: Banca d'Italia, Garante
  - 노출 금지 이유: IBAN 만으로 SEPA 자동이체 위조가 가능하다. 이탈리아는 급여·임대료·공과금이 IBAN 제출로 처리된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `IT[0-9]{2} ?[A-Z][0-9]{3} ?[0-9]{4} ?[0-9]{3}[0-9A-Z] ?([0-9A-Z]{4} ?){2}[0-9A-Z]{3}` | `IT60X0542811101000000123456`, `IT60 X054 2811 1010 0000 0123 456`, `IT60X0542811101CC0000123456` (26자리, `FR76…` 은 거부) | 기본. `IT` 접두 + CIN 문자 + 27자리 + `iban` 검증기. 자리 구조는 `IT`+키 2(그룹 1) / CIN 1 + ABI 5 + CAB 5(그룹 2-3 과 그룹 4 앞 세 자리) / 계좌 12(영숫자, 그룹 4 마지막 자리부터 그룹 7 까지)이다. 계좌번호는 규격(`12!c`)상 영숫자이므로 fr_FR 와 같이 영숫자로 두었다. `boundary_check: true` 적용 |

    오탐: 낮다.
  - **byte-scan handwritten**: 가능하나 이득이 없다.
  - **Aho-Corasick**: 공통 IBAN detector 로 확장하면 적합(de_DE 문서 참조). `IT` 를 국가 코드 anchor 목록에 등록한다.
  - **권장**: 공통 `iban` recognizer + `iban` 검증기. `it_cin` 검증기는 이탈리아 고유이므로 BBAN 부분에 추가 적용한다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: (1) `iban`: ISO 7064 mod 97-10 (de_DE 문서와 동일). (2) `it_cin`: BBAN 22자(ABI + CAB + 계좌)를 왼쪽부터 1번으로 세어 **홀수 자리**는 Codice Fiscale 과 같은 특수 표(`0`-`9` 와 `A`-`Z` → 1 0 5 7 9 13 15 17 19 21 …), **짝수 자리**는 `0`-`9` → 0-9, `A`-`Z` → 0-25 로 바꿔 합한 뒤 26으로 나눈 나머지를 `A`-`Z` 로 바꾼 것이 CIN 과 같으면 유효하다. `it_cf` 와 같은 표를 쓰므로 helper 를 공유한다. ISO 견본으로 `X` 가 재현됨을 확인했다.
- **채택 여부 및 근거**: 조건부 채택. IBAN 부분은 공통 항목으로 이관하고, `it_cin` 검증기는 이탈리아 고유로 유지한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `iban`, `conto corrente`, `coordinate bancarie`, `bonifico`, `banca`, `sepa`, `addebito`. (`abi`, `cab` 은 `abitare`·`cabina` 에 포함되므로 제외한다.)

### it_phonenumber

- **설명**: 이탈리아 전화번호. 국가번호 `+39`. 휴대전화는 `3` 으로 시작하는 9-10자리(`3XX XXXXXXX`. 배정된 통신사 접두는 대체로 `31x`-`39x` 이며 정확한 목록은 확인 필요)이고, 유선은 `0` 으로 시작하며 지역번호(`02` 밀라노, `06` 로마, `0577` 시에나 등 2-4자리) + 가입자 번호(4-8자리)로 총 6-11자리라 길이가 일정하지 않다. 이탈리아는 국제 표기에서도 유선의 선행 `0` 을 유지한다(`+39 02 …`).
  - 예시: 휴대전화 `333 123 4567`, `+39 333 1234567`, `3331234567`, `333-123-4567`, `+39 320 123 456`. 유선 `06 12345678`, `02 1234567`, `0577 123456`, `+39 02 12345678`, `0612345678`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: GDPR 제4조, Codice Privacy 제130조 (동의 없는 마케팅 통신 금지), Legge 5/2018·DPR 26/2022 (Registro pubblico delle opposizioni), D.Lgs. 259/2003
  - 감독기관: Garante, AGCOM
  - 노출 금지 이유: 휴대전화번호는 2단계 인증·SPID(디지털 신원) 인증의 열쇠이고, 이탈리아는 텔레마케팅 제재가 강해 번호 유출 자체가 Garante 제재 사유가 된다.
- **결정론적 검출 가능성**: 휴대전화는 가능, 유선은 가능하나 매우 약하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `(\+39 ?)?3[0-9]{2}[ .-]?[0-9]{3}[ .-]?[0-9]{3,4}` | `333 123 4567`, `+39 333 1234567`, `3331234567`, `333-123-4567`, `+39 320 123 456` (`233 …`, `333 12 345` 는 거부) | score 사용 고려. `3` 접두와 9-10자리가 필터이지만, 구분자 없는 `3331234567` 은 다른 10자리 숫자열과 겹친다. `boundary_check: true` 적용 |
    | `(\+39 ?)?0[0-9]{1,3}[ .-]?[0-9]{4,8}` | `06 12345678`, `02 1234567`, `0577 123456`, `+39 02 12345678`, `0612345678`, `012345` (`6 12345678`, `01 123`, 13자리는 거부) | **score 사용 필요**. regex 는 6-12자리를 허용한다(실제 번호는 최대 11자리). `0` + 5-11자리 숫자는 우편번호·주문번호와 광범위하게 겹친다. 지역번호 표(약 230개)를 넣으면 좁아진다 |

    오탐: 휴대전화는 중간, 유선은 높다.
  - **byte-scan handwritten**: 가능. 유선번호는 지역번호 표를 코드 표로 두면 DFA 비대화를 피한다.
  - **Aho-Corasick**: `+39` (3바이트)만 anchor 로 적합하다. 국내 표기 휴대전화는 접두가 `3` 한 글자라 부적합하다.
  - **권장**: 휴대전화는 regex, 유선은 점수 체계 도입 후 낮은 `score` 의 별도 recognizer(`it_phonenumber_landline`).
- **검증기**:
  - 현재: 없음
  - 구현 가능: 휴대전화는 통신사 접두 표(배정된 `3XX` 목록, 확인 필요) 외 규칙 없음. 유선은 지역번호 표(최신 공고로 재확인 필요).
- **채택 여부 및 근거**: 휴대전화는 채택. 유선은 채택하되 점수 체계 도입이 선행 조건이며 그 전에는 등록하지 않는다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `telefono`, `cellulare`, `numero di telefono`, `chiamare`, `contatto`, `recapito`, `whatsapp`, `phone`. (`tel`, `cell` 은 짧아 제외한다.)

### it_vehicle_plate

- **설명**: 차량 번호판(targa). 1994년 이후 형식은 `대문자 2 + 숫자 3 + 대문자 2`(`AA 123 BB`)이며 문자에서 `I`, `O`, `Q`, `U` 를 쓰지 않는다. 카드·서면에서는 공백 없이 `AB123CD` 로도 쓴다. 번호판은 차량 평생 불변이고 PRA(공공 자동차 등록부)에서 소유자와 연결된다.
  - 예시: `AB 123 CD`, `AB123CD`, `ZZ 999 ZZ`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: Codice della strada 제93조 (등록), 제94조 (PRA 전사), 제100조 (번호판), GDPR 제4조. Garante 는 번호판을 소유자와 결합 가능한 개인정보로 본다(주차·과속 카메라·대시캠 관련 조치).
  - 감독기관: ACI (PRA), 교통부, Garante
  - 노출 금지 이유: 번호판으로 PRA 에서 소유자 정보를 조회할 수 있고(유료 공개 조회 `visura PRA` 가 존재해 다른 국가보다 접근이 쉽다), 통행 기록과 결합하면 위치 추적이 가능하다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-HJ-NPR-TV-Z]{2} ?[0-9]{3} ?[A-HJ-NPR-TV-Z]{2}` | `AB 123 CD`, `AB123CD`, `ZZ 999 ZZ` (`AI 123 CD`, `AB 12 CD`, `AB 123 CQ` 는 거부) | 기본. `2-3-2` 구조와 문자 집합 제한으로 오탐이 낮다. 공백 없는 7자리 영숫자 `AB123CD` 는 제품 코드와 겹칠 수 있으나 문자 집합 제한이 걸러 준다. `boundary_check: true` 적용 |

    오탐: 낮다.
  - **byte-scan handwritten**: 가능하나 이득이 없다.
  - **Aho-Corasick**: 부적합. 고정 접두가 없다.
  - **권장**: regex.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 문자 집합은 regex 에 포함된다.
- **채택 여부 및 근거**: 채택. 오탐이 낮고 Garante 가 개인정보로 보며 PRA 조회로 소유자 특정이 쉽다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `targa`, `targato`, `veicolo`, `automobile`, `libretto`, `license plate`. (`auto` 는 `automatico` 에, `pra` 는 `pratica`·`sopra` 에 포함되므로 제외한다.)

### it_partita_iva

- **설명**: Partita IVA (P.IVA). Agenzia delle Entrate 가 사업자(법인·개인사업자)에게 부여하는 11자리 숫자 번호로, 앞 7자리는 일련번호, 다음 3자리는 관할 지방 코드(`001`-`100`, `120`, `121`, `888`, `999`), 마지막 자리는 Luhn 체크 디지트이다. EU 내 거래에서는 `IT` 접두를 붙인다. 법인의 Codice Fiscale 과 같은 번호인 경우가 많다.
  - 예시: `12345670157` (형식 예시. 지방 코드 `015` 와 Luhn 을 통과하도록 계산한 값), `IT 00743110157` (python-stdnum 문서 예시)
- **법적 근거**:
  - 법령: DPR 633/1972 제35조. VIES 와 Agenzia delle Entrate 조회 서비스에서 누구나 확인할 수 있는 **공개 번호**이고, 송장·웹사이트·영수증에 기재가 의무이다.
  - 감독기관: Agenzia delle Entrate
  - 노출 금지 이유: 약하다. 공개가 원칙인 번호이다. 다만 개인사업자(libero professionista, ditta individuale)의 P.IVA 는 개인 이름과 함께 공개된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{11}` | `12345670157`, `00743110157` | score 사용 고려. 11자리 숫자열이지만 기존 `luhn` 검증기(1/10)와 지방 코드 표로 좁힐 수 있다. 미채택 항목 |
    | `IT ?[0-9]{11}` | `IT 00743110157`, `IT00743110157` | 기본에 가깝다. `IT` 접두가 필터. 미채택 항목 |

  - **byte-scan handwritten**: 가능하나 이득이 없다.
  - **Aho-Corasick**: `IT` 접두 형태는 공통 IBAN detector 와 anchor 를 공유할 수 있으나(`IT` 뒤가 숫자 11자리인지 IBAN 인지 verifier 가 구분), 미채택이라 검토만 한다.
  - **권장**: (채택 시) regex + 기존 `luhn` + 지방 코드 표.
- **검증기**:
  - 현재: `luhn` 이 존재하며 그대로 적용 가능하다.
  - 구현 가능: 지방 코드 표(`001`-`100`, `120`, `121`, `888`, `999`)와 앞 7자리가 `0000000` 이 아닌지 검사를 더한 `it_piva` 로 확장할 수 있다(python-stdnum 의 검증과 동일).
- **채택 여부 및 근거**: 미채택 (보류). 공개 번호이므로 마스킹 대상으로 보기 어렵다. 개인사업자 보호 요구가 생기면 기존 `luhn` 으로 즉시 도입할 수 있다.
- **기존 구현 여부**: 신규 (미채택이므로 구현하지 않음)
- **context_words 후보** (재검토 시 참고): `partita iva`, `p.iva`, `p. iva`, `piva`, `vat number`

## 4. 검토 후 미채택한 항목

아래 항목은 법령상 PII 이거나 식별번호이지만 결정론적 검출이 불가능하거나 공개 번호라서 recognizer 로 등록하지 않는다.

| 항목 | 법적 근거 | 미채택 이유 |
|---|---|---|
| 법인 Codice Fiscale (11자리) | DPR 605/1973 | 대개 Partita IVA 와 같은 번호이며 공개 번호이다. |
| Codice destinatario SDI (7자리 영숫자, 전자 송장) | D.Lgs. 127/2015 | 사업자 식별 코드이며 공개 번호이다. |
| Numero REA (상공회의소 등록번호) | D.P.R. 581/1995 | 공개 등기 정보이다. |
| Permesso di soggiorno 번호 | D.Lgs. 286/1998 (TUI) | 형식 명세를 확인하지 못했다. 이민 신분 노출 위험은 인정한다. |
| Numero SPID / CIE 로그인 식별자 | CAD | 텍스트에 번호 형태로 나타나지 않는다. |
| CAP (5자리 우편번호) | GDPR | 5자리 숫자는 다른 숫자열과 구분되지 않는다. |
| Numero tessera elettorale, numero INPS | Codice Privacy | INPS 는 Codice Fiscale 을 식별자로 쓰고, 선거인 카드 번호는 형식 명세가 없다. |
| 주소, 이름, 생년월일 | GDPR 제4조 | 국가 종속 항목이 아니며 regex 로 결정론적 검출이 불가능하다. 공통 항목 또는 NER 로 다룬다. |
| 생체정보, 건강 상태, 종교·노조 가입 | GDPR 제9조, Codice Privacy 제2-sexies조 | 특수 범주이지만 번호 형태로 나타나지 않는다. |
| 신용카드번호, 이메일, IP 주소 | GDPR, PCI DSS | 국가 종속 항목이 아니므로 이 문서 범위 밖이다. 기존 `card_number` 등이 담당한다. |

## 5. 구현 시 후속 작업 요약

이 문서에서 도출된, YAML·`validator.rs`·`handwritten/`·엔진에 반영할 작업 목록이다. 검증기는 **함수 구현 → YAML 등록** 순서를 지킨다(`validator::validate` 가 fail-open 이므로 순서가 바뀌면 검증 없이 통과한다).

| 순서 | 작업 | 대상 | 종류 |
|---|---|---|---|
| 선행 | recognizer 단위 `score` 필드와 context 가산 방식 도입 (en_US 문서 5절과 공통. 이미 완료되었으면 이 행 삭제) | 엔진 | 엔진 변경 |
| 1 | `it_cf` 검증기(홀짝 가중 mod 26 체크 문자, 생년월일 유효성)와 `it_codice_fiscale` recognizer 추가 | it_codice_fiscale | validator 신규, YAML 신규 |
| 2 | `it_id_card` recognizer 추가 (CIE 패턴 + 구형 패턴). 구형 패턴과 여권을 하나의 `pii_type` 으로 묶을지 결정 | it_id_card, it_passport | YAML 신규 |
| 3 | `it_passport` recognizer 추가 (2번과 통합 여부에 따라) | it_passport | YAML 신규 |
| 4 | `it_health_card` recognizer 추가 (Aho-Corasick anchor `8038` 또는 regex). 체크 디지트 알고리즘 확인 후 `it_ts` 검증기 | it_health_card | handwritten 수정 또는 YAML 신규, 조사 |
| 5 | `it_cin` 검증기 추가 (`it_cf` 와 홀짝 표 공유). IBAN 부분은 (공통 항목 이관 확정 시) 공통 `iban` recognizer 의 국가 길이 표에 `IT` 27 을 등록하고 BBAN 에 `it_cin` 추가 적용 | it_iban, iban (공통) | validator 신규, YAML 신규 |
| 6 | `it_phonenumber` 휴대전화 recognizer 추가 (`boundary_check: true`) | it_phonenumber | YAML 신규 |
| 7 | `it_phonenumber_landline` recognizer 추가 (`score` 낮게). **선행 작업 완료 후에만** | it_phonenumber | YAML 신규 |
| 8 | `it_vehicle_plate` recognizer 추가 | it_vehicle_plate | YAML 신규 |
| 9 | `it_driver_license` 형식 명세 확인 후 등록 여부 결정. 등록하더라도 낮은 `score` 가 필요하므로 **선행 작업 완료 후에만** | it_driver_license | 조사 |
| 선택 | `it_partita_iva` recognizer (기존 `luhn` + 지방 코드 표, 개인사업자 보호 요구 시) | it_partita_iva | YAML 신규, validator 확장 |
