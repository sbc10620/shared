# PII 목록: es_MX (멕시코)

이 문서는 `tinicore/src/guardrails/config/pii_filter_config.yaml` 에 멕시코(es_MX) 고유 PII recognizer 가 포함되어야 하는 근거를 기록한다. 이미 YAML 에 있는 항목도 근거를 남기기 위해 포함하며, 국가에 종속되지 않는 항목(카드번호, API 키, 비밀번호, 이메일, IP 주소 등)은 다루지 않는다. 2026-09-15 현재 YAML 에 `mx_*` recognizer 는 하나도 없으므로 이 문서의 모든 항목은 신규이다. `pii_type` 접두는 ISO 3166 국가 코드에 맞춰 `mx_` 를 쓴다(locale 은 es_MX). 스페인(es_ES)과는 언어만 같고 식별번호 체계가 전혀 다르다.

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

엔진은 DFA 를 `MatchKind::All` 로 빌드해 겹치는 모든 매치 끝을 보고한 뒤 boundary check 와 dedup 으로 가장 긴 것을 남긴다. 엔진이 `unicode(false)` 로 DFA 를 빌드하므로 `Ñ` 은 문자 클래스에 넣을 수 없다. RFC 의 이름 부분에는 `Ñ` 이 올 수 있으나(python-stdnum regex `[A-Z&Ñ]`), 이 문서의 regex 는 ASCII `[A-Z&]` 만 쓰고 `Ñ` 포함 RFC 는 놓친다고 명시했다(리터럴 대안 `(Ñ)` 을 추가하면 잡을 수 있다). CURP·RFC 의 체크섬과 형식 규칙은 python-stdnum 2.2 의 `stdnum.mx.curp`, `stdnum.mx.rfc` 구현과 대조했고, NSS 의 Luhn 은 `stdnum.luhn` 으로, CLABE 의 체크 디지트는 공개 규칙(가중치 `3 7 1` 순환)으로 자체 계산했다.

## 1. 적용 법령 및 감독기관

멕시코는 민간 부문에 적용되는 연방 개인정보 보호법(LFPDPPP, 2010년 제정, 2025년 3월 신법으로 대체)과 공공 부문의 LGPDPPSO(2017)로 개인정보를 규율한다. 감독기관은 2025년 개정으로 독립 기구 INAI 가 폐지되고 **반부패·굿거버넌스부(Secretaría Anticorrupción y Buen Gobierno)** 산하로 이관되었다(개정 시행 세부는 확인 필요). 멕시코 법제의 특징은 **CURP(18자리 인구 등록 키)가 범용 식별자**라는 점으로, 이름·생년월일·성별·출생 주가 인코딩되어 있고 2025년 개정으로 생체정보 연계(CURP biométrica)가 의무화되었다. RFC(세금 번호)도 개인의 경우 이름과 생년월일을 담는다. 따라서 CURP·RFC 가 최우선 채택 대상이고, NSS(사회보장번호)·INE(유권자 신분증) 키·CLABE(계좌번호)·여권이 뒤를 잇는다.

| 법령 | 감독기관 | 적용 범위 요약 |
|---|---|---|
| Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP. 2010년 법을 폐지한 2025년 3월 신법. 조문 번호는 2010년 법 기준이며 신법에서 재확인 필요) 제3조, 제19조, 제20조 | Secretaría Anticorrupción y Buen Gobierno (2025년 INAI 대체. 확인 필요) | 민간 부문 개인정보·민감 개인정보 정의, 보안 조치, 유출 통지 |
| Ley General de Protección de Datos Personales en Posesión de Sujetos Obligados (LGPDPPSO, 2017. 2025년 3월 재공포 여부 확인 필요) | 동일 (연방·주 기관) | 공공 부문 개인정보 |
| Ley General de Población 제91조; Reglamento 제86조 이하; Decreto (CURP biométrica, 2025) | RENAPO (Registro Nacional de Población), 내무부 (SEGOB) | CURP 의 부여·구조, 생체정보 연계 |
| Código Fiscal de la Federación 제27조, 제69조 | SAT (Servicio de Administración Tributaria) | RFC 의 부여·기재 의무, 조세 비밀 |
| Ley del Seguro Social 제15조; Reglamento de Afiliación | IMSS | NSS(사회보장번호)의 부여 |
| Ley General de Instituciones y Procedimientos Electorales (LGIPE) 제126조–제136조 | INE (Instituto Nacional Electoral) | 유권자 등록과 INE 신분증(clave de elector, CIC, OCR) |
| Reglamento de Pasaportes y del Documento de Identidad y Viaje; Ley del Servicio Exterior Mexicano | 외무부 (SRE) | 여권 발급 |
| Ley de Instituciones de Crédito 제117조; Banxico 규정 (SPEI, CLABE) | Banco de México (Banxico), CNBV | 은행 비밀, 표준 계좌번호 CLABE |
| Ley Federal de Telecomunicaciones y Radiodifusión (2025년 7월 Ley en Materia de Telecomunicaciones y Radiodifusión 으로 대체된 것으로 알려짐, 확인 필요); REPEP (텔레마케팅 거부 등록) | IFT (2025년 폐지·대체 기구 확인 필요), PROFECO | 통신 가입자 정보, 상업 통신 제한 |
| Reglamento de Tránsito (각 주); NOM-001-SCT-2-2016 | SICT, 각 주 교통 당국 | 차량 번호판 규격 |

## 2. 요약 표

| pii_type | 설명 | 결정론적 검출 | 권장 검출 방식 | 검증기 (현재 / 구현 가능) | score | 기존 구현 | 채택 |
|---|---|---|---|---|---|---|---|
| mx_curp | 인구 등록 키 (CURP, 18자리) | 가능 (형식 엄격) | regex (+ `mx_curp` 검증기) | 없음 / 가중합 mod 10 체크 디지트 + 주 코드 표 | 기본 | 신규 | 채택 |
| mx_rfc | 개인 세금 번호 (RFC persona física, 13자리) | 가능 | regex (+ `mx_rfc` 검증기) | 없음 / 가중합 mod 11 체크 문자 | 사용 고려 | 신규 | 채택 |
| mx_rfc (법인, 12자리) | 법인 세금 번호 (RFC persona moral) | 가능 | regex (+ `mx_rfc` 검증기) | 없음 / 가중합 mod 11 체크 문자 | 사용 고려 | 신규 | 미채택 (공개 사업자 번호) |
| mx_nss | 사회보장번호 (NSS, 11자리) | 가능 | regex (+ `luhn` 검증기) | `luhn` (기존, 그대로 사용) / 없음 | 사용 고려 | 신규 | 채택 |
| mx_voter_key | 선거인 키 (clave de elector, 18자리) | 가능 (형식 엄격) | regex | 없음 / 주 코드 표 + 생년월일 유효성 (주 코드 구간은 regex 에 포함) | 기본 | 신규 | 채택 |
| mx_passport | 여권번호 (`G12345678`) | 가능 | regex (+ `mrz_731`, 체크 디지트 동반 시) | 없음 / MRZ 7-3-1 (10자리 표기에만) | 사용 고려 | 신규 | 채택 |
| mx_clabe | 표준 계좌번호 (CLABE, 18자리) | 가능 | regex (+ `mx_clabe` 검증기) | 없음 / 가중합 mod 10 | 사용 고려 | 신규 | 채택 |
| mx_phonenumber | 전화번호 (10자리) | 가능 | regex | 없음 / 지역번호 표 | 사용 고려 | 신규 | 채택 |
| mx_vehicle_plate | 차량 번호판 (주별 형식) | 가능 (약함) | regex | 없음 / 규격 접두 배제 목록 | **사용 필요** | 신규 | 채택 (점수 체계 도입과 주별 형식 확인이 선행 조건) |

이외에 검토했으나 결정론적 검출이 불가능하거나 공개 번호라서 미채택한 항목은 4절에 정리했다.

## 3. 항목별 상세

### mx_curp

- **설명**: CURP (Clave Única de Registro de Población). RENAPO 가 모든 국민·거주자에게 부여하는 18자리 영숫자 키로, 구조는 `성·이름에서 뽑은 문자 4 + 생년월일 YYMMDD 6 + 성별 1(H 남, M 여. 비이분법 표기 `X` 발급 사례가 보도되었으므로 현행 규칙 확인 필요) + 출생 주 코드 2 + 성·이름의 자음 3 + 동명이인 구분 1(1900년대생은 숫자, 2000년대생은 문자) + 체크 디지트 1` 이다. 체크 디지트는 앞 17자를 `0`-`9`, `A`-`Z`(`Ñ` 포함) 순번으로 바꿔 가중치 `18 … 2` 를 곱한 합의 mod 10 로 계산한다. 학교·병원·은행·고용·정부 서비스 모든 곳에서 요구되며, 2025년 개정으로 생체정보와 연계된다.
  - 예시: `BADD110313HCMLNS06`, `MAHJ280603MSPRRN06`, `GOAR970122HDFMLC04` (형식 예시. 앞 17자는 RENAPO 안내 자료의 예시 구조를 따르고 체크 디지트는 python-stdnum 으로 계산해 통과를 확인했다)
- **법적 근거**:
  - 법령: Ley General de Población 제91조, LFPDPPP 제3조 (개인정보), 2025년 CURP biométrica 개정
  - 감독기관: RENAPO, SEGOB, 개인정보 감독기관
  - 노출 금지 이유: 멕시코의 범용 식별자이며 생년월일·성별·출생 주가 그대로 들어 있다. CURP + INE 번호 조합으로 계좌 개설·SIM 등록·정부 서비스 접근이 가능하고, 생체정보 연계 이후 유출 위험이 더 커졌다.
- **결정론적 검출 가능성**: 가능하며 형식이 엄격하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{4}[0-9]{2}(0[1-9]\|1[0-2])(0[1-9]\|[12][0-9]\|3[01])[HM][A-Z]{5}[0-9A-Z][0-9]` | `BADD110313HCMLNS06`, `MAHJ280603MSPRRN06`, `GOAR970122HDFMLC04` (`BADD111313…`(월 13), `BADD110313X…`(성별 X), 17자리는 거부) | 기본. 18자리 안에서 문자·숫자 위치, 생년월일 범위, 성별 문자가 고정되어 우연히 맞기 어렵고 `mx_curp` 검증기(1/10)로 더 낮아진다. `boundary_check: true` 적용 |

    오탐: 낮다. 소문자 입력은 `(?i)` 로 잡되 검증기 계산 전에 대문자로 바꾼다.
  - **byte-scan handwritten**: 가능하나 단일 패턴이라 이점이 없다.
  - **Aho-Corasick**: 부적합. 접두가 이름에서 나온다.
  - **권장**: regex + `mx_curp` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 앞 17자를 `0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ` 의 순번(RENAPO 규정. python-stdnum 은 24번 자리를 `&` 로 두지만 CURP 에는 두 문자 모두 나타나지 않으므로 결과가 같다)으로 바꿔 가중치 `18 … 2` 를 곱한 합 s 에 대해 `(10 - s mod 10) mod 10` 이 18번째 자리와 같으면 유효하다. 주 코드 표(`AS`, `BC`, `BS`, `CC`, `CL`, `CM`, `CS`, `CH`, `DF`, `DG`, `GT`, `GR`, `HG`, `JC`, `MC`, `MN`, `MS`, `NT`, `NL`, `OC`, `PL`, `QT`, `QR`, `SP`, `SL`, `SR`, `TC`, `TS`, `TL`, `VZ`, `YN`, `ZS`, `NE` 외국 출생)와 생년월일 유효성도 함께 검사한다. 검증기 `mx_curp` 로 구현한다(python-stdnum `mx.curp` 와 동일).
- **채택 여부 및 근거**: 채택. 멕시코의 최고 등급 식별자이며 형식이 엄격하고 검증기가 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `curp`, `clave única de registro de población`, `clave unica`, `renapo`, `población`

### mx_rfc

- **설명**: RFC (Registro Federal de Contribuyentes). SAT 가 부여하는 세금 번호로, 개인은 `성·이름 문자 4 + 생년월일 YYMMDD 6 + homoclave 3` 의 13자리, 법인은 `상호 문자 3 + 설립일 6 + homoclave 3` 의 12자리이다. homoclave 는 SAT 가 부여하는 2자 + 체크 문자 1자이며, 체크 문자는 앞 12자(개인은 앞 12자, 법인은 공백을 앞에 붙인 12자)를 특수 알파벳 순번으로 바꿔 가중치 `13 … 2` 를 곱한 합의 mod 11 로 계산한다. 이름 부분에는 `&` 와 `Ñ` 이 올 수 있다. 송장(CFDI)·급여·계약서에 기재된다.
  - 예시: 개인 `VECJ880326A17`, `GOAR970122B24` (형식 예시. python-stdnum 으로 체크 문자 계산·검증 통과 확인), 법인 `ABC010203AB9` (형식 예시)
- **법적 근거**:
  - 법령: Código Fiscal de la Federación 제27조 (RFC 등록 의무), 제69조 (조세 비밀), LFPDPPP 제3조
  - 감독기관: SAT, 개인정보 감독기관
  - 노출 금지 이유: 개인 RFC 는 이름·생년월일을 담고 있어 CURP 와 함께 신원 도용의 열쇠이다. SAT 포털 접근·전자 서명(e.firma)·송장 발행에 쓰인다. 법인 RFC 는 송장에 기재되는 공개 번호라 개인정보가 아니다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z&]{4}[0-9]{2}(0[1-9]\|1[0-2])(0[1-9]\|[12][0-9]\|3[01])[1-9A-V][1-9A-Z][0-9A]` (개인) | `VECJ880326A17`, `GOAR970122B24` (`VECJ881326A17`(월 13), `VECJ880326XX1`(homoclave 규칙 위반), 12자리 `VEC880326A19` 는 이 패턴에서 거부) | score 사용 고려. `문자 4 + 생년월일 + 3자` 구조가 필터이지만 CURP 의 앞 13자와 형식이 비슷해 CURP 안의 부분 문자열이 `boundary_check` 없이는 매치될 수 있다(`boundary_check: true` 로 방지). `Ñ` 포함 이름은 ASCII 클래스로는 잡지 못하므로 필요하면 `([A-Z&]\|Ñ){4}` 리터럴 대안으로 바꾼다. `mx_rfc` 검증기(1/11) 병행 |
    | `[A-Z&]{3}[0-9]{2}(0[1-9]\|1[0-2])(0[1-9]\|[12][0-9]\|3[01])[0-9A-Z]{3}` (법인) | `ABC010203AB9` | 등록하지 않음. 법인 RFC 는 공개 번호. 미채택 행 |

    오탐: 개인 RFC 는 중간(검증기 병행 시 낮음).
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합.
  - **권장**: 개인 RFC 만 regex + `mx_rfc` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 앞 12자를 알파벳 `0123456789ABCDEFGHIJKLMN&OPQRSTUVWXYZ Ñ` 순번(python-stdnum `mx.rfc` 의 `_alphabet`)으로 바꿔 가중치 `13 … 2` 를 곱한 합 s 에 대해 `(11 - s) mod 11` 을 같은 알파벳으로 바꾼 값이 13번째 자리와 같으면 유효하다. homoclave 앞 2자는 `[1-9A-V][1-9A-Z]`, 체크 자리는 `[0-9A]` 이다. 검증기 `mx_rfc` 로 구현한다. homoclave 없는 10자리 표기(`VECJ880326`)도 존재하나 검증할 수 없으므로 이 문서에서는 다루지 않는다.
- **채택 여부 및 근거**: 채택(개인 RFC). 조세 비밀 대상이자 생년월일을 담은 식별자이며 검증기가 있다. 법인 RFC 는 공개 번호라 미채택.
- **기존 구현 여부**: 신규
- **context_words 후보**: ` rfc ` (3글자라 공백 포함 형태), `registro federal de contribuyentes`, `homoclave`, ` sat `, `contribuyente`, `factura`, `cfdi`

### mx_nss

- **설명**: NSS (Número de Seguridad Social). IMSS 가 피보험자에게 부여하는 11자리 번호로 `지역(subdelegación) 2 + 등록 연도 2 + 출생 연도 2 + 일련번호 4 + 체크 디지트 1` 구조이며 `12 34 56 7890 3` 처럼 띄어 쓴다. 마지막 자리는 Luhn 체크 디지트이다. 고용·의료(IMSS 병원)·연금(AFORE) 기록의 연결 키이다.
  - 예시: `12345678903`, `01938500129`, `45898012344` (형식 예시. Luhn 통과를 python-stdnum 으로 확인)
- **법적 근거**:
  - 법령: Ley del Seguro Social 제15조, Reglamento de Afiliación, LFPDPPP 제3조 (건강·재정 정보)
  - 감독기관: IMSS, 개인정보 감독기관
  - 노출 금지 이유: 의료 기록·고용 기록·연금 계좌(AFORE)의 연결 키이다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{2} ?[0-9]{2} ?[0-9]{2} ?[0-9]{4} ?[0-9]` | `12345678903`, `12 34 56 7890 3`, `01938500129` | score 사용 고려. 구분자 없는 11자리 숫자열은 다른 번호와 겹치므로 기존 `luhn` 검증기(1/10) 병행이 사실상 필수. 검증기 없이 등록한다면 score 사용 필요. `boundary_check: true` 적용 |

    오탐: 검증기 없이는 높고, 검증기를 붙이면 중간이다.
  - **byte-scan handwritten**: 가능. 오탐률은 regex + Luhn 조합과 **동일**하다.
  - **Aho-Corasick**: 부적합.
  - **권장**: regex + 기존 `luhn` 검증기.
- **검증기**:
  - 현재: `luhn` 이 존재하며 그대로 적용 가능하다(숫자만 걸러 계산하므로 공백 표기도 처리된다).
  - 구현 가능: 추가 구현 불필요.
- **채택 여부 및 근거**: 채택. 의료·연금 기록의 연결 키이며 기존 검증기를 재사용한다.
- **기존 구현 여부**: 신규
- **context_words 후보**: ` nss ` (3글자라 공백 포함 형태), `número de seguridad social`, `numero de seguridad social`, `seguro social`, `imss`, `afore`

### mx_voter_key

- **설명**: INE 신분증(credencial para votar)의 clave de elector. 18자리 영숫자로 `성·이름 문자 6 + 생년월일 YYMMDD 6 + 출생 주 코드 2 + 성별 1(H/M) + 동명이인 구분 3` 구조이다. INE 신분증에는 이 밖에 CIC(9자리), OCR(12-13자리) 번호도 인쇄되나 형식이 단순한 숫자열이다. INE 신분증은 멕시코에서 가장 널리 쓰이는 사진 신분증이다.
  - 예시: `ABCDEF80010109H100`, `GMVLMR80070109M100` (형식 예시)
- **법적 근거**:
  - 법령: LGIPE 제126조–제136조, LFPDPPP 제3조. INE 는 선거인 명부와 신분증 정보를 기밀로 취급한다.
  - 감독기관: INE, 개인정보 감독기관
  - 노출 금지 이유: 사진 신분증의 키이며 생년월일·성별·출생 주를 담고 있다. 은행·통신·부동산 거래의 본인확인에 INE 신분증 사본이 관행적으로 요구되어 유출이 잦다.
- **결정론적 검출 가능성**: 가능하며 형식이 엄격하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{6}[0-9]{2}(0[1-9]\|1[0-2])(0[1-9]\|[12][0-9]\|3[01])(0[1-9]\|[12][0-9]\|3[0-2]\|88)[HM][0-9]{3}` | `ABCDEF80010109H100`, `GMVLMR80070109M100`, `ABCDEF80010188H100` (`ABCDEF80130109H100`(월 13), `…0199H100`(주 코드 99)은 거부) | 기본. 18자리 안에서 문자·숫자 위치와 생년월일·성별·주 코드 구간(`01`-`32`, `88` 국외)이 고정되어 우연히 맞기 어렵다. 체크섬은 없다. `boundary_check: true` 적용 |
    | `[0-9]{12,13}` (OCR 번호), `[0-9]{9}` (CIC) | `123456789012`, `1234567890123` | 등록하지 않음. 숫자만이라 오탐이 높고 clave de elector 가 실질 키이다. 미채택 행 |

    오탐: clave de elector 는 낮다.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합.
  - **권장**: regex(clave de elector 만).
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 주 코드 표(`01`-`32`, `88` 국외)와 생년월일 유효성 검사는 가능하다.
- **채택 여부 및 근거**: 채택. 핵심 신분증 키이며 형식이 엄격하다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `clave de elector`, `credencial para votar`, `credencial de elector`, ` ine `, ` ife ` (3글자라 공백 포함 형태), `credencial`

### mx_passport

- **설명**: 멕시코 여권번호. 전자여권은 `대문자 1 + 숫자 8` 의 9자리이다(예: `G12345678`. 첫 문자는 발급 시리즈이며 확인 필요). 번호 자체에 체크섬은 없고 MRZ 에 7-3-1 체크 디지트가 붙는다.
  - 예시: `G12345678` (형식 예시)
- **법적 근거**:
  - 법령: Reglamento de Pasaportes y del Documento de Identidad y Viaje, LFPDPPP 제3조
  - 감독기관: SRE, 개인정보 감독기관
  - 노출 금지 이유: 정부 발급 신분증 번호로서 항공·비자·은행 KYC 에 쓰인다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z][0-9]{8}[0-9]?` | `G12345678` (`G1234567`, `GA1234567` 은 거부) | score 사용 고려. `대문자 1 + 숫자 8` 은 미국 여권(Next Generation `A12345678`)·기존 `us_passport` 패턴과 동일 형식이라 9자리 표기는 같은 값을 잡는다(체크 디지트가 붙은 10자리 `G123456789` 는 `us_passport` 가 boundary check 에서 버리므로 이 패턴만 잡는다). 선택 꼬리는 MRZ 체크 디지트 표기용이며 10자리 매치에만 `mrz_731` 적용. `boundary_check: true` 적용 |

    오탐: 중간.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합.
  - **권장**: regex + `mrz_731`(10자리 매치에만). 9자리 표기는 기존 `us_passport` 가 이미 잡으므로 `pii_type` 표기 외에는 검출 공백이 없고, 10자리 표기는 이 recognizer 가 있어야 잡힌다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 번호 자체에는 없다. MRZ 체크 디지트 동반 시 `mrz_731`(de_DE 문서).
- **채택 여부 및 근거**: 채택. 정부 발급 신분증 번호이다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `pasaporte`, `número de pasaporte`, `passport`, ` sre `

### mx_clabe

- **설명**: CLABE (Clave Bancaria Estandarizada). Banxico 가 정한 18자리 표준 계좌번호로 `은행 코드 3 + 지점(plaza) 코드 3 + 계좌번호 11 + 체크 디지트 1` 구조이다. 체크 디지트는 앞 17자리에 가중치 `3 7 1` 을 순환 적용해 곱한 합 s 에 대해 `(10 - s mod 10) mod 10` 이다. SPEI 송금·급여 입금·자동이체에 쓰이며 멕시코는 IBAN 을 쓰지 않는다.
  - 예시: `002010077777777771` (Banxico·은행 안내 자료에서 관용적으로 쓰는 형식 예시. 체크 디지트 통과), `012180001234567899` (형식 예시. 체크 디지트 통과)
- **법적 근거**:
  - 법령: Ley de Instituciones de Crédito 제117조 (은행 비밀), Banxico SPEI 규정, LFPDPPP 제3조 (재정 정보)
  - 감독기관: Banxico, CNBV, 개인정보 감독기관
  - 노출 금지 이유: CLABE 만으로 SPEI 송금 대상 지정과 자동이체 등록이 가능하다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{3}[ -]?[0-9]{3}[ -]?[0-9]{11}[ -]?[0-9]` | `002010077777777771`, `002 010 07777777777 1`, `012180001234567899` | score 사용 고려. 구분자 없는 18자리 숫자열은 드물지만 다른 번호와 겹칠 수 있으므로 `mx_clabe` 검증기(1/10) 병행. 은행 코드 표(`002` Banamex, `012` BBVA 등)로 더 좁힐 수 있다. `boundary_check: true` 적용 |

    오탐: 검증기 없이는 중간, 검증기를 붙이면 낮다.
  - **byte-scan handwritten**: 가능. 오탐률은 regex + `mx_clabe` 조합과 **동일**하다.
  - **Aho-Corasick**: 은행 코드 3자리(약 100개)를 anchor 로 등록할 수 있으나 3자리 숫자는 흔하다.
  - **권장**: regex + `mx_clabe` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 위 가중합 mod 10. 검증기 `mx_clabe` 로 구현한다(Banxico 공개 규칙. 은행 코드 표 대조는 선택).
- **채택 여부 및 근거**: 채택. 계좌 정보이며 검증기가 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `clabe`, `clabe interbancaria`, `cuenta clabe`, `spei`, `transferencia`, `cuenta bancaria`, `número de cuenta`

### mx_phonenumber

- **설명**: 멕시코 전화번호. 국가번호 `+52`, 국내 형식은 2019년 8월 이후 지역 구분 없이 10자리 고정이다(지역번호 2자리 + 8자리: 멕시코시티 `55`, 과달라하라 `33`, 몬테레이 `81`, 또는 지역번호 3자리 + 7자리). 휴대전화와 유선의 형식이 같아 번호만으로는 구분할 수 없다. 국제 표기에서 휴대전화에 붙이던 `1`(`+52 1 55 …`)은 2019년 8월 번호 계획 개편으로 폐지되었으나 아직 쓰인다(폐지 시점 확인 필요).
  - 예시: `55 1234 5678`, `(55) 1234-5678`, `55-1234-5678`, `+52 55 1234 5678`, `+52 1 55 1234 5678`, `5512345678`, `(33) 1234 5678`, `818 123 4567`, `(999) 123-4567`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: Ley Federal de Telecomunicaciones y Radiodifusión (2025년 대체 법령 확인 필요), REPEP (PROFECO 텔레마케팅 거부 등록), LFPDPPP 제3조
  - 감독기관: IFT, PROFECO, 개인정보 감독기관
  - 노출 금지 이유: 휴대전화번호는 은행 앱·SPEI 인증·WhatsApp 의 열쇠이며, 멕시코는 전화 사기(extorsión telefónica)가 특히 많다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `(\+52[ -]?1?[ -]?)?(\(?[0-9]{2}\)?[ -]?[0-9]{4}[ -]?[0-9]{4}\|\(?[0-9]{3}\)?[ -]?[0-9]{3}[ -]?[0-9]{4})` | `55 1234 5678`, `(55) 1234-5678`, `55-1234-5678`, `+52 55 1234 5678`, `+52-55-1234-5678`, `+52 1 55 1234 5678`, `5512345678`, `(33) 1234 5678`, `818 123 4567`, `(999) 123-4567` (9자리, `1234 5678` 은 거부) | score 사용 고려. 10자리 고정 길이가 필터이지만 첫 자리 제한이 없어 구분자 없는 10자리 숫자열은 미국 전화번호·NHS 번호 등과 겹친다. 지역번호 표(약 400개)를 넣으면 좁아진다. 두 대안(2+8, 3+7)은 `MatchKind::All` 에서 모두 시도된다. `boundary_check: true` 적용 |

    오탐: 중간. 구분자 없는 10자리와 3-3-4 묶음은 기존 `us_phonenumber` 도 잡지만, 멕시코식 2+8 묶음(`55 1234 5678`, `(55) 1234-5678`)은 `us_phonenumber` 가 잡지 못하므로 이 recognizer 가 있어야 검출 공백이 메워진다.
  - **byte-scan handwritten**: 가능하나 이점이 적다.
  - **Aho-Corasick**: `+52`(3바이트)만 anchor 로 적합하다.
  - **권장**: regex. 휴대전화·유선 구분이 불가능하므로 하나의 recognizer 로 둔다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: IFT 지역번호 표(최신 공고로 재확인 필요).
- **채택 여부 및 근거**: 채택. 형식이 고정이라 오탐이 제어 가능하다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `teléfono`, `telefono`, `celular`, `número de teléfono`, `whatsapp`, `llamar`, `contacto`, ` tel ` (3글자라 공백 포함 형태), `phone`

### mx_vehicle_plate

- **설명**: 차량 번호판(placa). 주마다 형식이 다르며 `문자 3 + 숫자 3 + 문자 1`(`ABC-123-A`, 2019년 이후 다수 주), `문자 3 + 숫자 4`(`ABC-1234`), `숫자 3 + 문자 3` 등이 병존한다. NOM-001-SCT-2-2016 이 규격을 정하지만 문자·숫자 배열은 주별 배정에 따른다(주별 형식 확인 필요).
  - 예시: `ABC-123-A`, `ABC 1234`, `ABC1234`, `ABC123A` (형식 예시)
- **법적 근거**:
  - 법령: 각 주 Reglamento de Tránsito, NOM-001-SCT-2-2016, LFPDPPP 제3조. REPUVE(차량 공공 등록부)에서 번호판으로 차량 정보가 조회된다.
  - 감독기관: SICT, 각 주 교통 당국
  - 노출 금지 이유: REPUVE 조회로 차량 정보가, 주 등록부로 소유자가 특정될 수 있다. 공개 노출되는 번호라 단독 위험도는 낮다.
- **결정론적 검출 가능성**: 가능하나 주별 형식 차이로 정밀도가 낮다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{3}[ -]?[0-9]{3,4}([ -]?[A-Z])?` | `ABC-123-A`, `ABC 1234`, `ABC1234`, `ABC123A` (`ABC-12-34` 형식은 잡지 못함) | **score 사용 필요**. `대문자 3 + 숫자 3-4` 는 `ISO-9001`, `DIN 1234` 같은 규격 표기와 정확히 겹친다(pt_BR 구형 번호판과 같은 문제). 점수 체계 도입 전에는 등록하지 않는다. `boundary_check: true` 적용 |

    오탐: 높다.
  - **byte-scan handwritten**: 주별 형식 표를 코드로 두면 정밀해지나 형식 수집이 선행되어야 한다.
  - **Aho-Corasick**: 부적합.
  - **권장**: 주별 형식 확인 후 점수 체계 도입 시 낮은 `score` 로 등록.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 규격 접두(`ISO`, `DIN`, `NOM` 등) 배제 목록.
- **채택 여부 및 근거**: 조건부 채택. 점수 체계 도입과 주별 형식 확인이 조건이다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `placa`, `placas`, `placa del vehículo`, `vehículo`, `vehiculo`, `repuve`, `tarjeta de circulación`

## 4. 검토 후 미채택한 항목

아래 항목은 법령상 PII 이거나 식별번호이지만 결정론적 검출이 불가능하거나 공개 번호라서 recognizer 로 등록하지 않는다.

| 항목 | 법적 근거 | 미채택 이유 |
|---|---|---|
| INE 신분증의 CIC(9자리)·OCR(12-13자리) 번호 | LGIPE | 숫자만이라 오탐이 높고 clave de elector 가 실질 키이다. `mx_voter_key` 항목 참조. |
| 운전면허번호 | 각 주 Reglamento de Tránsito | 주마다 형식이 달라 명세를 확인하지 못했다(멕시코시티는 CURP 기반이라는 자료가 있음). 조사 후 재검토. |
| 군 복무 카드(cartilla militar) 번호 | Ley del Servicio Militar | 형식 명세를 확인하지 못했다. |
| Código postal (5자리) | 해당 없음 | 5자리 숫자는 다른 숫자열과 구분되지 않는다. |
| 주소, 이름, 생년월일 | LFPDPPP 제3조 | 국가 종속 항목이 아니며 regex 로 결정론적 검출이 불가능하다. 공통 항목 또는 NER 로 다룬다. |
| 생체정보, 건강 상태, 종교·인종 | LFPDPPP 제3조 (민감 개인정보) | 민감 개인정보이지만 번호 형태로 나타나지 않는다. |
| 신용카드번호, 이메일, IP 주소 | LFPDPPP, PCI DSS | 국가 종속 항목이 아니므로 이 문서 범위 밖이다. 기존 `card_number` 등이 담당한다. |

## 5. 구현 시 후속 작업 요약

이 문서에서 도출된, YAML·`validator.rs`·`handwritten/`·엔진에 반영할 작업 목록이다. 검증기는 **함수 구현 → YAML 등록** 순서를 지킨다(`validator::validate` 가 fail-open 이므로 순서가 바뀌면 검증 없이 통과한다).

| 순서 | 작업 | 대상 | 종류 |
|---|---|---|---|
| 선행 | recognizer 단위 `score` 필드와 context 가산 방식 도입 (en_US 문서 5절과 공통. 이미 완료되었으면 이 행 삭제) | 엔진 | 엔진 변경 |
| 1 | `mx_curp` 검증기(가중합 mod 10 + 주 코드 표 + 생년월일)와 `mx_curp` recognizer 추가 | mx_curp | validator 신규, YAML 신규 |
| 2 | `mx_rfc` 검증기(특수 알파벳 가중합 mod 11)와 개인 `mx_rfc` recognizer 추가. `Ñ` 포함 이름은 리터럴 대안으로 처리 여부 결정 | mx_rfc | validator 신규, YAML 신규 |
| 3 | `mx_nss` recognizer 추가 (기존 `luhn` 재사용) | mx_nss | YAML 신규 |
| 4 | `mx_voter_key` recognizer 추가 | mx_voter_key | YAML 신규 |
| 5 | `mx_passport` recognizer 추가 (`mrz_731` 검증기는 de_DE 작업과 공용). 기존 `us_passport` 와 같은 값을 같은 점수로 잡으면 등록 순서가 보고 `pii_type` 을 정하므로(`detector.rs` 의 겹침 해소는 점수·길이·시작 위치·등록 순서만 본다) 어느 쪽을 먼저 둘지 결정 | mx_passport | YAML 신규 |
| 6 | `mx_clabe` 검증기(가중치 `3 7 1` 순환 mod 10)와 `mx_clabe` recognizer 추가 | mx_clabe | validator 신규, YAML 신규 |
| 7 | `mx_phonenumber` recognizer 추가 (`boundary_check: true`). `us_phonenumber` 와의 겹침 처리 검토 | mx_phonenumber | YAML 신규 |
| 8 | 주별 번호판 형식(흔한 인쇄 형식 `ABC-12-34` 포함) 확인 후 `mx_vehicle_plate` recognizer 추가 (`score` 낮게). **선행 작업 완료 후에만** | mx_vehicle_plate | 조사, YAML 신규 |
| 9 | 2025년 LFPDPPP 신법의 조문 번호·감독기관 명칭, 통신법 대체 여부, 운전면허 형식 확인 | (문서) | 조사 |
| 선택 | 법인 `mx_rfc` recognizer (사업자 번호 마스킹 요구 시) | mx_rfc | YAML 신규 |
