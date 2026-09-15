# PII 목록: es_ES (스페인)

이 문서는 `tinicore/src/guardrails/config/pii_filter_config.yaml` 에 스페인(es_ES) 고유 PII recognizer 가 포함되어야 하는 근거를 기록한다. 이미 YAML 에 있는 항목도 근거를 남기기 위해 포함하며, 국가에 종속되지 않는 항목(카드번호, API 키, 비밀번호, 이메일, IP 주소 등)은 다루지 않는다. 2026-09-15 현재 YAML 에 `es_*` recognizer 는 하나도 없으므로 이 문서의 모든 항목은 신규이다. 멕시코(es_MX)는 언어만 같고 식별번호 체계가 전혀 다르므로 별도 문서로 다룬다.

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

엔진은 DFA 를 `MatchKind::All` 로 빌드해 겹치는 모든 매치 끝을 보고한 뒤 boundary check 와 dedup 으로 가장 긴 것을 남긴다. 엔진이 `unicode(false)` 로 DFA 를 빌드하므로 `Ñ`·악상 문자는 문자 클래스에 넣을 수 없다(ko_KR·de_DE 문서 참조). 이 문서의 regex 는 모두 ASCII 만 쓰며, 번호판 문자 집합에서 `Ñ` 을 제외하는 규칙은 ASCII 자음만 나열하는 것으로 자연히 표현된다. DNI·NIE·CCC·IBAN·CIF 의 체크섬과 형식 규칙은 python-stdnum 2.2 의 `stdnum.es.dni`, `stdnum.es.nie`, `stdnum.es.ccc`, `stdnum.es.iban`, `stdnum.es.cif` 구현과 대조했다. 사회보장번호(NAF)는 stdnum 에 구현이 없어 공개 규칙(앞 10자리 mod 97)으로 자체 계산했다.

## 1. 적용 법령 및 감독기관

스페인은 EU 회원국이므로 GDPR 이 직접 적용되고, 개인정보 보호 및 디지털 권리 보장에 관한 조직법(Ley Orgánica 3/2018, LOPDGDD)이 국내 이행법이다. 감독기관은 AEPD(Agencia Española de Protección de Datos) 단일 기관이며, 카탈루냐·바스크·안달루시아는 공공 부문에 한해 자치 감독기관을 둔다. 스페인 법제의 특징은 **DNI 번호가 곧 세금 번호(NIF)이자 운전면허 번호**라는 점이다. 하나의 9자리 번호가 신분증·세무·운전면허·사회보장·의료 기록을 모두 연결하므로, DNI/NIE 가 이 문서의 최우선 채택 대상이다. AEPD 는 DNI 번호 자체는 "식별 데이터"로 보아 특수 범주로 분류하지 않지만, 공개 게시나 과잉 수집에 대해 반복적으로 제재해 왔다.

| 법령 | 감독기관 | 적용 범위 요약 |
|---|---|---|
| GDPR (Regulation (EU) 2016/679) 제4조, 제9조, 제32조, 제87조 | AEPD (Agencia Española de Protección de Datos) | 개인정보 정의, 특수 범주, 처리 보안, 국가 식별번호 이용 조건 위임 |
| Ley Orgánica 3/2018 (LOPDGDD) 제9조, 제20조, 제28조 | AEPD, 자치 감독기관 (카탈루냐 APDCAT, 바스크 AVPD, 안달루시아 CTPDA) | 특수 범주 처리 조건, 신용정보 시스템, 보안 조치 |
| Real Decreto 1553/2005; Ley Orgánica 4/2015 제8조–제9조 | 내무부 (Dirección General de la Policía) | DNI 의 발급·구조·제시 의무 |
| Ley Orgánica 4/2000 제4조; Real Decreto 557/2011 제206조 | 내무부, 이민청 | 외국인 신원번호(NIE) |
| Ley 58/2003 General Tributaria 제95조; Real Decreto 1065/2007 제18조–제22조 | AEAT (Agencia Tributaria) | 조세 정보 비밀, NIF 보유 의무(제18조)와 구성(스페인 국적 개인은 DNI: 제19조, 외국 국적 개인은 NIE: 제20조, 법인은 CIF: 제22조) |
| Real Decreto Legislativo 8/2015 (LGSS); Real Decreto 84/1996 제21조 | TGSS (Tesorería General de la Seguridad Social) | 사회보장 가입번호(NAF/NUSS) |
| Real Decreto 896/2003 | 내무부 | 여권 발급과 번호 |
| Real Decreto Legislativo 6/2015 (Ley de Tráfico); Real Decreto 2822/1998 (Reglamento General de Vehículos) 제25조; Real Decreto 818/2009 (Reglamento General de Conductores) | DGT (Dirección General de Tráfico) | 차량 등록·번호판, 운전면허(번호는 DNI 와 동일) |
| Ley 11/2022 General de Telecomunicaciones; Ley 34/2002 (LSSI) 제21조 | CNMC, AEPD | 통신 가입자 정보, 동의 없는 상업 통신 금지 |
| Ley 10/2010 (자금세탁 방지); Real Decreto-ley 19/2018 (지급 서비스) | SEPBLAC, Banco de España | 금융 거래 정보와 계좌 식별자(IBAN/CCC) 취급 |
| Ley 41/2002 (환자 자율성·임상 정보) | 보건부, AEPD | 건강 정보(건강 카드 포함) |

## 2. 요약 표

| pii_type | 설명 | 결정론적 검출 | 권장 검출 방식 | 검증기 (현재 / 구현 가능) | score | 기존 구현 | 채택 |
|---|---|---|---|---|---|---|---|
| es_dni | 국가 신분증 번호 (DNI, = NIF·운전면허번호) | 가능 | regex (+ `es_dni` 검증기) | 없음 / mod 23 체크 문자 | 기본 | 신규 | 채택 |
| es_nie | 외국인 신원번호 (NIE) | 가능 | regex (+ `es_nie` 검증기) | 없음 / mod 23 체크 문자 (X/Y/Z → 0/1/2) | 기본 | 신규 | 채택 |
| es_social_security_number | 사회보장 가입번호 (NAF/NUSS, 12자리) | 가능 | regex (+ `es_naf` 검증기) | 없음 / 앞 10자리 mod 97 | 사용 고려 | 신규 | 채택 |
| es_passport | 여권번호 (`ABC123456`) | 가능 | regex (+ `mrz_731`, 체크 디지트 동반 시) | 없음 / MRZ 7-3-1 (10자리 표기에만) | 사용 고려 | 신규 | 채택 |
| es_iban | 스페인 IBAN (CCC 포함) | 가능 | regex 또는 Aho-Corasick (+ `iban` 검증기, `es_ccc` 검증기) | 없음 / ISO 7064 mod 97-10, CCC 이중 체크 디지트 | 기본 (IBAN) / 사용 고려 (CCC 단독) | 신규 | 조건부 채택 (공통 항목 `iban` 으로 이관 검토, CCC 는 스페인 고유) |
| es_phonenumber | 전화번호 (9자리, `6`-`9` 시작) | 가능 | regex | 없음 / 없음 (접두 규칙은 regex 에 포함) | 사용 고려 | 신규 | 채택 |
| es_vehicle_plate | 차량 번호판 (`1234 BBB`, 구형 `M-1234-AB`) | 가능 | regex | 없음 / 없음 (문자 집합은 regex 에 포함) | 기본 (신형) / **사용 필요** (구형) | 신규 | 채택 (신형은 바로, 구형은 점수 체계 도입이 선행 조건) |
| es_cif | 법인 세금 번호 (CIF) | 가능 | regex (+ `es_cif` 검증기) | 없음 / 유형별 체크 문자 | 사용 고려 | 신규 | 미채택 |

이외에 검토했으나 결정론적 검출이 불가능하거나 공개 번호라서 미채택한 항목은 4절에 정리했다.

## 3. 항목별 상세

### es_dni

- **설명**: DNI (Documento Nacional de Identidad) 번호. 경찰청이 모든 스페인 국민에게(14세부터 보유 의무) 부여하는 숫자 8자리 + 체크 문자 1자의 9자리 번호이며, 평생 불변이다. 같은 번호가 세금 번호(NIF)이고 운전면허증에도 면허 번호로 인쇄되므로, 스페인에서는 DNI 번호 하나가 신분·세무·운전·사회보장·의료 기록을 모두 연결한다. 체크 문자는 8자리 숫자를 23으로 나눈 나머지를 `TRWAGMYFPDXBNJZSQVHLCKE` 에서 고른 것이다(`I`, `Ñ`, `O`, `U` 는 쓰지 않는다). 서면에서는 `12345678Z`, `12345678-Z`, `12.345.678-Z` 로 표기한다.
  - 예시: `12345678Z` (스페인 행정 안내에서 관용적으로 쓰는 형식 예시. 체크 문자 `Z` 통과), `87654321X`, `00000000T` (모두 python-stdnum 으로 확인)
- **법적 근거**:
  - 법령: Real Decreto 1553/2005 (DNI 구조), Ley Orgánica 4/2015 제8조–제9조 (제시 의무), Real Decreto 1065/2007 제19조 (스페인 국적 개인의 NIF = DNI), LOPDGDD, GDPR 제87조
  - 감독기관: AEPD, 내무부, AEAT
  - 노출 금지 이유: 스페인의 범용 식별자이자 세금 번호이다. DNI 번호 + 이름만으로 계약·대출·통신 개통 사기가 가능해 AEPD 가 DNI 사본 요구 관행 자체를 제재해 왔다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{8}[- ]?[TRWAGMYFPDXBNJZSQVHLCKE]` | `12345678Z`, `12345678-Z`, `87654321 X` (`12345678I`(무효 문자), 7자리, 소문자는 거부) | 기본. 8자리 + 체크 문자 집합(23자)이 필터이고 `es_dni` 검증기(1/23)로 더 낮아진다. `12.345.678-Z` 점 표기를 잡으려면 `[0-9]{2}\.?[0-9]{3}\.?[0-9]{3}` 로 완화. `boundary_check: true` 적용 |

    오탐: 낮다. 소문자 입력은 `(?i)` 로 잡되 검증기 계산 전에 대문자로 바꾼다.
  - **byte-scan handwritten**: 가능. 오탐률은 regex + `es_dni` 조합과 **동일**하다. 단일 패턴이라 이점이 없다.
  - **Aho-Corasick**: 부적합. 고정 접두가 없다.
  - **권장**: regex + `es_dni` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 8자리 숫자를 23으로 나눈 나머지 r 에 대해 `"TRWAGMYFPDXBNJZSQVHLCKE"[r]` 이 체크 문자와 같으면 유효하다. 검증기 `es_dni` 로 구현한다(python-stdnum `es.dni` 와 동일).
- **채택 여부 및 근거**: 채택. 스페인의 최고 등급 식별자이며 강한 검증기가 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: ` dni `, ` nif ` (공백 포함 형태. `nif` 는 `significa`·`planificación` 에 포함되므로 단독 등록 불가), `documento nacional de identidad`, `número de identificación fiscal`, `carnet de conducir`, `permiso de conducir`, `identity card`
- **비고**: 운전면허번호는 DNI 와 같으므로 별도 `es_driver_license` 항목을 두지 않는다. 법인 NIF(CIF)는 아래 `es_cif` 참조.

### es_nie

- **설명**: NIE (Número de Identificación de Extranjero). 스페인 거주 외국인에게 부여하는 번호로 `X`·`Y`·`Z` 중 한 문자 + 숫자 7자리 + 체크 문자 1자이다. 체크 문자는 첫 문자를 `X`→0, `Y`→1, `Z`→2 로 바꾼 8자리 숫자에 DNI 와 같은 mod 23 규칙을 적용한다. 외국인의 NIF 이기도 하다.
  - 예시: `X1234567L`, `Y1234567X`, `Z1234567R` (형식 예시. python-stdnum 으로 체크 문자 확인)
- **법적 근거**:
  - 법령: Ley Orgánica 4/2000 제4조, Real Decreto 557/2011 제206조, Real Decreto 1065/2007 제20조 (외국 국적 개인의 NIF = NIE), LOPDGDD, GDPR 제87조
  - 감독기관: AEPD, 내무부, 이민청
  - 노출 금지 이유: DNI 와 같은 역할이며, 번호 보유 사실 자체가 외국인 신분을 드러낸다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[XYZ][- ]?[0-9]{7}[- ]?[TRWAGMYFPDXBNJZSQVHLCKE]` | `X1234567L`, `Y-1234567-X`, `Z1234567R` (`A1234567L`, 6자리는 거부) | 기본. 첫 문자 3종 + 7자리 + 체크 문자 집합. `es_nie` 검증기 병행. `boundary_check: true` 적용 |

    오탐: 낮다.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 첫 문자 `X`/`Y`/`Z` 는 1바이트라 anchor 로 부적합하다.
  - **권장**: regex + `es_nie` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 첫 문자를 0/1/2 로 바꾼 뒤 `es_dni` 와 같은 mod 23 계산. 검증기 `es_nie` 로 구현하거나 `es_dni` 에 분기를 둔다.
- **채택 여부 및 근거**: 채택. DNI 와 동급이며 이민 신분을 드러낸다.
- **기존 구현 여부**: 신규
- **context_words 후보**: ` nie ` (공백 포함 형태. `nie` 는 `teniendo`·`conveniente`·`nieve` 에 포함되므로 단독 등록 불가), `número de identificación de extranjero`, `extranjero`, `tarjeta de residencia`. (`tie` 는 3글자라 제외한다.)

### es_social_security_number

- **설명**: Número de afiliación a la Seguridad Social (NAF, NUSS). TGSS 가 부여하는 12자리 번호로 `PP NNNNNNNN CC` 구조이다. `PP` 는 최초 가입 지방 코드(2자리), `NNNNNNNN` 은 일련번호 8자리, `CC` 는 앞 10자리를 97 로 나눈 나머지인 체크 디지트 2자리이다. `28/12345678/40` 처럼 슬래시로 구분해 표기하는 경우가 많다.
  - 예시: `281234567840`, `28/12345678/40`, `28 12345678 40`, `08-01234567-17` (형식 예시. mod 97 규칙을 통과하도록 계산한 값)
- **법적 근거**:
  - 법령: Real Decreto 84/1996 제21조 (가입번호), LGSS, LOPDGDD, GDPR 제87조
  - 감독기관: TGSS, AEPD
  - 노출 금지 이유: 고용·연금·실업급여·의료 기록의 연결 키이다. 급여명세서에 인쇄되어 유출이 잦다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{2}[ /-]?[0-9]{8}[ /-]?[0-9]{2}` | `281234567840`, `28/12345678/40`, `28 12345678 40`, `08-01234567-17` (10자리, 7자리 일련번호는 거부) | score 사용 고려. 구분자 없는 12자리 숫자열은 다른 번호와 겹치므로 `es_naf` 검증기(1/97) 병행이 사실상 필수. 검증기 없이 등록한다면 score 사용 필요. `boundary_check: true` 적용 |

    오탐: 검증기 없이는 높고, 검증기를 붙이면 낮다.
  - **byte-scan handwritten**: 가능. 오탐률은 regex + `es_naf` 조합과 **동일**하다.
  - **Aho-Corasick**: 부적합. 접두 2자리가 지방 코드(약 52종)라 짧고 많다.
  - **권장**: regex + `es_naf` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 앞 10자리를 정수로 읽어 97 로 나눈 나머지를 2자리로 맞춘 값이 마지막 2자리와 같으면 유효하다. 검증기 `es_naf` 로 구현한다(공개 규칙 기준. stdnum 에는 구현이 없으므로 TGSS 자료로 재확인 권장. 특히 일련번호가 `0` 으로 시작할 때 지방 코드와 일련번호를 각각 정수로 이어 붙이는 변형 구현이 있으므로, 예시 `08-01234567-17` 이 그 분기점이다).
- **채택 여부 및 근거**: 채택. 사회보장 기록의 연결 키이고 검증기가 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `seguridad social`, `número de afiliación`, `afiliación`, `nuss`, `naf`(3글자, 제외), `tgss`, `social security`

### es_passport

- **설명**: 여권번호. 2006년 이후 전자여권은 영문 대문자 3자 + 숫자 6자리의 9자리이다(예: `ABC123456`). 앞 3자가 발급 순서에 따른 문자열이라는 자료가 있으나 확인 필요. 번호 자체에 체크섬은 없고 MRZ 에 7-3-1 체크 디지트가 붙는다.
  - 예시: `ABC123456`, `PAB123456` (형식 예시)
- **법적 근거**:
  - 법령: Real Decreto 896/2003, LOPDGDD, GDPR 제87조
  - 감독기관: 내무부, AEPD
  - 노출 금지 이유: 정부 발급 신분증 번호로서 항공·호텔·은행 KYC 에 쓰인다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{3}[0-9]{6}[0-9]?` | `ABC123456`, `PAB123456`, `ABC1234567` (`AB123456`, `ABC12345` 는 거부) | score 사용 고려. `대문자 3 + 숫자 6` 은 제품·예약 코드와 겹칠 수 있다. 선택 꼬리는 MRZ 체크 디지트 표기용이며 10자리 매치에만 `mrz_731` 적용. `boundary_check: true` 적용 |

    오탐: 중간.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합.
  - **권장**: regex + `mrz_731`(10자리 매치에만).
- **검증기**:
  - 현재: 없음
  - 구현 가능: 번호 자체에는 없다. MRZ 체크 디지트 동반 시 `mrz_731`(de_DE 문서).
- **채택 여부 및 근거**: 채택. 정부 발급 신분증 번호이다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `pasaporte`, `número de pasaporte`, `passport`

### es_iban

- **설명**: 스페인 IBAN 과 CCC. IBAN 은 `ES` + 키 2자리 + CCC 20자리 = 24자리이며, CCC(Código Cuenta Corriente)는 `은행 4 + 지점 4 + 체크 디지트 2 + 계좌 10` 의 모두 숫자인 구조이다. CCC 의 체크 디지트 2자리는 각각 `00` + 은행·지점 8자리와 계좌 10자리에 가중치 `2^i`(i = 0…) 를 곱해 합한 값을 11 로 나눈 나머지에서 계산한다(python-stdnum `es.ccc` 와 동일). 즉 스페인 계좌는 IBAN mod 97 과 CCC 이중 체크 디지트를 모두 갖는다. 2014년 2월 SEPA 전환 이후 IBAN 이 표준이지만 CCC 단독 표기(`2100 0418 45 0200051332`)도 아직 쓰인다.
  - 예시: `ES9121000418450200051332`, `ES91 2100 0418 4502 0005 1332` (널리 쓰이는 견본 IBAN. mod 97 통과, 안의 CCC 체크 디지트 `45` 통과를 stdnum 으로 확인), `ES7712341234161234567890` (stdnum 문서 예시), CCC 표기 `2100 0418 45 0200051332`, `1234-1234-16-1234567890`
- **법적 근거**:
  - 법령: Ley 10/2010, Real Decreto-ley 19/2018, LOPDGDD, GDPR 제4조
  - 감독기관: Banco de España, SEPBLAC, AEPD
  - 노출 금지 이유: IBAN 만으로 SEPA 자동이체 위조가 가능하다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `ES[0-9]{2} ?([0-9]{4} ?){4}[0-9]{4}` | `ES9121000418450200051332`, `ES91 2100 0418 4502 0005 1332`, `ES7712341234161234567890` (23자리, `FR76…` 은 거부) | 기본. `ES` 접두 + 24자리 + `iban` 검증기. CCC 는 규격(`20!n`)상 모두 숫자이므로 영숫자 완화가 필요 없다. 마지막 그룹을 고정해 뒤따르는 공백이 매치에 들어가지 않게 했다(fr_FR·it_IT 와 같은 관례). `boundary_check: true` 적용 |
    | `[0-9]{4}[ -]?[0-9]{4}[ -]?[0-9]{2}[ -]?[0-9]{10}` (CCC 단독 표기) | `2100 0418 45 0200051332`, `21000418450200051332`, `1234-1234-16-1234567890` | score 사용 고려. 구분자 없는 20자리는 다른 숫자열과 겹칠 수 있으나 `es_ccc` 검증기(이중 체크 디지트, 각 자리가 0-9 로 사상되므로 약 1/100)로 보완된다 |

    오탐: IBAN 은 낮고, CCC 단독은 검증기 병행 시 낮다.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 공통 IBAN detector 로 확장하면 적합(de_DE 문서 참조). `ES` 를 국가 코드 anchor 목록에 등록한다.
  - **권장**: 공통 `iban` recognizer + `iban` 검증기. CCC 단독 표기와 `es_ccc` 검증기는 스페인 고유로 유지한다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: (1) `iban`: ISO 7064 mod 97-10 (de_DE 문서와 동일). (2) `es_ccc`: `00` + 은행 4 + 지점 4 의 10자리와 계좌 10자리 각각에 대해, 왼쪽부터 i 번째 자리에 `2^i` 를 곱해 합한 값을 11 로 나눈 나머지 r 을 `r < 2 이면 r, 아니면 11 - r` 로 바꾼 것이 체크 디지트 첫째·둘째 자리와 각각 같으면 유효하다. IBAN 매치에도 CCC 부분에 추가 적용해 이중 검증한다.
- **채택 여부 및 근거**: 조건부 채택. IBAN 부분은 공통 항목으로 이관하고, CCC 단독 표기와 `es_ccc` 검증기는 스페인 고유로 유지한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `iban`, `cuenta bancaria`, `número de cuenta`, `transferencia`, `domiciliación`, `sepa`, `banco`, `entidad bancaria`. (`ccc` 는 3글자라 제외한다.)

### es_phonenumber

- **설명**: 스페인 전화번호. 국가번호 `+34`, 국내 형식은 9자리 고정이며 선행 `0` 이 없다. 첫 자리 `6`·`7` 은 휴대전화, `8`·`9` 는 유선(`91` 마드리드, `93` 바르셀로나 등 지역번호는 번호의 일부), `800`/`900` 은 무료 번호이다. 표기는 `612 345 678`(3-3-3) 또는 `91 234 56 78`(2-3-2-2) 이 흔하다.
  - 예시: `612 345 678`, `612 34 56 78`, `91 234 56 78`, `+34 612 34 56 78`, `612345678`, `912.345.678`, `+34612345678`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: GDPR 제4조, Ley 11/2022, LSSI 제21조 (동의 없는 상업 통신 금지), Ley 11/2022 제66조 (텔레마케팅 거부권)
  - 감독기관: AEPD, CNMC
  - 노출 금지 이유: 휴대전화번호는 2단계 인증·Bizum(모바일 송금)의 열쇠이고, AEPD 는 동의 없는 텔레마케팅에 고액 제재를 부과해 왔다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `(\+34 ?)?[6-9][0-9]([ .-]?[0-9]{3}[ .-]?[0-9]{2}[ .-]?[0-9]{2}\|[0-9]([ .-]?[0-9]{3}[ .-]?[0-9]{3}\|([ .-]?[0-9]{2}){3}))` | `612 345 678`, `612 34 56 78`, `91 234 56 78`, `+34 612 34 56 78`, `+34 91 234 56 78`, `612345678`, `912.345.678`, `+34612345678` (`512 345 678`, 8자리는 거부) | score 사용 고려. 9자리 고정 길이와 첫 자리 `6`-`9` 가 필터이지만, 구분자 없는 9자리 숫자열은 다른 번호와 겹친다. 세 대안(2-3-2-2, 3-3-3, 3-2-2-2)은 `MatchKind::All` 에서 모두 시도된다. CNMC 가 배정한 `51x` 노마딕(VoIP) 번호는 의도적으로 제외했다. `boundary_check: true` 적용 |

    오탐: 중간. 길이가 고정이라 유선·휴대전화를 한 패턴으로 다룰 수 있다.
  - **byte-scan handwritten**: 가능하나 단일 패턴이라 이점이 없다.
  - **Aho-Corasick**: `+34`(3바이트)만 anchor 로 적합하다. 국내 표기는 첫 자리 한 글자라 부적합하다.
  - **권장**: regex.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 첫 자리 규칙은 regex 에 포함. 필요하면 `800`/`900` 무료 번호와 `70x` 개인 번호를 제외하는 규칙을 검증기로 둘 수 있다.
- **채택 여부 및 근거**: 채택. 형식이 고정이라 오탐이 제어 가능하다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `teléfono`, `telefono`, `móvil`, `movil`, `celular`, `número de teléfono`, `llamar`, `contacto`, `whatsapp`, `phone`. (`tel`, `tlf` 는 3글자라 제외한다.)

### es_vehicle_plate

- **설명**: 차량 번호판(matrícula). 2000년 9월 이후 형식은 `숫자 4 + 자음 3`(`1234 BBB`)이며 문자에서 모음·`Ñ`·`Q` 를 제외한 `BCDFGHJKLMNPRSTVWXYZ` 20자만 쓴다. 2000년 이전 구형은 `지방 약어 1-2자 + 숫자 4 + 문자 1-2자`(`M-1234-AB`)이며 아직 도로에 남아 있다.
  - 예시: 신형 `1234 BBB`, `1234BCD`, `0000 ZZZ`. 구형 `M-1234-AB`, `B1234CD`, `GC-1234-A`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: Real Decreto 2822/1998 제25조·제49조 및 Anexo XVIII (번호판 부착 의무와 규격), RDL 6/2015, LOPDGDD, GDPR 제4조. AEPD 는 번호판을 소유자와 결합 가능한 개인정보로 본다(주차·카메라 관련 결정).
  - 감독기관: DGT, AEPD
  - 노출 금지 이유: DGT 차량 등록부에서 소유자 정보를 조회할 수 있고(정당한 이익 요건 하에), 통행 기록과 결합하면 위치 추적이 가능하다. 공개 노출되는 번호라 단독 위험도는 낮다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{4}[ -]?[BCDFGHJKLMNPRSTVWXYZ]{3}` | `1234 BBB`, `1234-BBB`, `1234BCD`, `0000 ZZZ` (`1234 ABC`(모음), `123 BBB`, `1234 BBÑ` 은 거부) | 기본. `숫자 4 + 자음 3` 구조와 문자 집합 제한으로 오탐이 낮다. `boundary_check: true` 적용 |
    | `[A-Z]{1,2}-?[0-9]{4}-?[A-Z]{1,2}` | `M-1234-AB`, `B1234CD`, `GC-1234-A` | **score 사용 필요**. 구형. `대문자 + 숫자 4 + 대문자` 는 제품 코드·주소 표기와 광범위하게 겹친다. 점수 체계 도입 전에는 등록하지 않는다 |

    오탐: 신형은 낮고 구형은 높다.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합. 고정 접두가 없다.
  - **권장**: 신형은 regex 기본 점수, 구형은 점수 체계 도입 후 낮은 `score`.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 문자 집합은 regex 에 포함된다.
- **채택 여부 및 근거**: 채택. 신형 형식은 오탐이 낮고 AEPD 가 개인정보로 본다. 구형은 점수 체계 도입이 선행 조건이다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `matrícula`, `matricula`, `vehículo`, `vehiculo`, `coche`, `placa`, `license plate`

### es_cif

- **설명**: CIF (Código de Identificación Fiscal, 현재는 법인 NIF). AEAT 가 법인·단체에 부여하는 9자리 번호로 `법인 유형 문자 1 + 숫자 7 + 체크 1자(숫자 또는 문자)` 이다. 유형 문자(`A` 주식회사, `B` 유한회사, `Q` 공공기관 등)에 따라 체크 자리가 숫자인지 문자인지 정해진다(공개 규칙상 `A`·`B`·`E`·`H` 는 숫자, `K`·`P`·`Q`·`S` 는 문자, 나머지는 양쪽 허용. AEAT 자료로 재확인 필요).
  - 예시: `A58000001`, `B12345674`, `Q2826000H` (형식 예시. python-stdnum 으로 체크 값 확인. stdnum 은 유형별 분기 없이 숫자·문자 둘 다 허용한다)
- **법적 근거**:
  - 법령: Real Decreto 1065/2007 제22조–제24조 (법인·단체의 NIF). 상업 등기부와 AEAT 조회로 **공개**되며 송장·웹사이트에 기재가 의무이다.
  - 감독기관: AEAT
  - 노출 금지 이유: 없다. 법인 식별자이지 개인정보가 아니다. 개인사업자(autónomo)는 CIF 가 아니라 자신의 DNI 를 NIF 로 쓰므로 `es_dni` 가 담당한다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[ABCDEFGHJNPQRSUVW][0-9]{7}[0-9A-J]` | `A58000001`, `B12345674`, `Q2826000H` | score 사용 고려. `es_cif` 검증기로 보완 가능. 미채택 항목 |

  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합.
  - **권장**: 미채택.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 숫자 7자리에 **Luhn** 을 적용해 체크 숫자를 구하고(기존 `luhn` 로직 재사용 가능), 그 숫자를 그대로 쓰거나 `JABCDEFGHI` 의 해당 위치 문자로 바꿔 마지막 자리와 비교한다. python-stdnum `es.cif` 는 유형 문자와 무관하게 숫자·문자 양쪽을 허용하며, 유형별 분기는 공개 규칙(Orden EHA/451/2008)을 따로 확인해 구현한다.
- **채택 여부 및 근거**: 미채택. 법인 공개 번호이며 개인정보가 아니다.
- **기존 구현 여부**: 신규 (미채택이므로 구현하지 않음)
- **context_words 후보** (재검토 시 참고): `cif`, `nif de empresa`, `razón social`

## 4. 검토 후 미채택한 항목

아래 항목은 법령상 PII 이거나 식별번호이지만 결정론적 검출이 불가능하거나 공개 번호라서 recognizer 로 등록하지 않는다.

| 항목 | 법적 근거 | 미채택 이유 |
|---|---|---|
| 운전면허번호 | Real Decreto 818/2009 | DNI/NIE 와 같은 번호이므로 `es_dni`·`es_nie` 가 담당한다. |
| 건강 카드 번호 (tarjeta sanitaria, CIP-SNS) | Ley 41/2002, GDPR 제9조 | 자치주마다 카드 번호 형식이 다르고, 전국 공통 CIP-SNS(16자리 영숫자)의 자리 구조를 확인하지 못했다(확인 필요). 건강 데이터라 확인되면 채택 검토. |
| Referencia catastral (부동산 등기 참조번호, 20자리) | Ley del Catastro | 부동산 식별자이며 공개 조회된다. |
| CUPS (에너지 공급 지점 코드, `ES` + 20-22자리) | Real Decreto 1435/2002 | 공급 지점 식별자로 개인과의 결합이 간접적이다. |
| Código postal (5자리) | GDPR | 5자리 숫자는 다른 숫자열과 구분되지 않는다. |
| Número de colegiado, número de la tarjeta de transporte | 해당 없음 | 형식 명세가 없거나 공개 번호이다. |
| 주소, 이름, 생년월일 | GDPR 제4조 | 국가 종속 항목이 아니며 regex 로 결정론적 검출이 불가능하다. 공통 항목 또는 NER 로 다룬다. |
| 생체정보, 건강 상태, 종교·노조 가입 | GDPR 제9조, LOPDGDD 제9조 | 특수 범주이지만 번호 형태로 나타나지 않는다. |
| 신용카드번호, 이메일, IP 주소 | GDPR, PCI DSS | 국가 종속 항목이 아니므로 이 문서 범위 밖이다. 기존 `card_number` 등이 담당한다. |

## 5. 구현 시 후속 작업 요약

이 문서에서 도출된, YAML·`validator.rs`·`handwritten/`·엔진에 반영할 작업 목록이다. 검증기는 **함수 구현 → YAML 등록** 순서를 지킨다(`validator::validate` 가 fail-open 이므로 순서가 바뀌면 검증 없이 통과한다).

| 순서 | 작업 | 대상 | 종류 |
|---|---|---|---|
| 선행 | recognizer 단위 `score` 필드와 context 가산 방식 도입 (en_US 문서 5절과 공통. 이미 완료되었으면 이 행 삭제) | 엔진 | 엔진 변경 |
| 1 | `es_dni` 검증기(mod 23 체크 문자)와 `es_dni` recognizer 추가 | es_dni | validator 신규, YAML 신규 |
| 2 | `es_nie` 검증기(X/Y/Z → 0/1/2 후 mod 23)와 `es_nie` recognizer 추가 (`es_dni` 와 helper 공유) | es_nie | validator 신규, YAML 신규 |
| 3 | `es_naf` 검증기(앞 10자리 mod 97)와 `es_social_security_number` recognizer 추가. TGSS 자료로 규칙 재확인 | es_social_security_number | validator 신규, YAML 신규, 조사 |
| 4 | `es_passport` recognizer 추가 (`mrz_731` 검증기는 de_DE 작업과 공용) | es_passport | YAML 신규 |
| 5 | `es_ccc` 검증기(이중 체크 디지트)와 CCC 단독 표기 recognizer 추가. IBAN 부분은 (공통 항목 이관 확정 시) 공통 `iban` recognizer 의 국가 길이 표에 `ES` 24 를 등록하고 CCC 에 `es_ccc` 추가 적용 | es_iban, iban (공통) | validator 신규, YAML 신규 |
| 6 | `es_phonenumber` recognizer 추가 (`boundary_check: true`) | es_phonenumber | YAML 신규 |
| 7 | `es_vehicle_plate` recognizer 추가 (신형 패턴만). 구형 패턴은 **선행 작업 완료 후에만** 낮은 `score` 로 | es_vehicle_plate | YAML 신규 |
| 8 | 건강 카드(CIP-SNS) 번호 구조 확인 후 채택 여부 결정 | (미정) | 조사 |
| 선택 | `es_cif` recognizer (법인 번호 마스킹 요구 시. `es_cif` 검증기는 stdnum 과 동일하게) | es_cif | validator 신규, YAML 신규 |
