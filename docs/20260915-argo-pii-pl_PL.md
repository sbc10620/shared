# PII 목록: pl_PL (폴란드)

이 문서는 `tinicore/src/guardrails/config/pii_filter_config.yaml` 에 폴란드(pl_PL) 고유 PII recognizer 가 포함되어야 하는 근거를 기록한다. 이미 YAML 에 있는 항목도 근거를 남기기 위해 포함하며, 국가에 종속되지 않는 항목(카드번호, API 키, 비밀번호, 이메일, IP 주소 등)은 다루지 않는다. 2026-09-15 현재 YAML 에 `pl_*` recognizer 는 하나도 없으므로 이 문서의 모든 항목은 신규이다.

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

엔진은 DFA 를 `MatchKind::All` 로 빌드해 겹치는 모든 매치 끝을 보고한 뒤 boundary check 와 dedup 으로 가장 긴 것을 남긴다. 엔진이 `unicode(false)` 로 DFA 를 빌드하므로 폴란드어 특수 문자(`ł`, `ą`, `ż` 등)는 문자 클래스에 넣을 수 없으나(ko_KR·de_DE 문서 참조), 이 문서의 regex 는 모두 ASCII 만 쓴다. PESEL·NIP·REGON·IBAN 의 체크섬과 형식 규칙은 python-stdnum 2.2 의 `stdnum.pl.pesel`, `stdnum.pl.nip`, `stdnum.pl.regon`, `stdnum.iban` 구현과 대조했다. 신분증 번호의 체크 디지트는 stdnum 에 구현이 없어 공개 규칙으로 자체 계산했고 확인 필요로 표시했다. 여권 번호의 자체 체크 디지트는 규칙을 확인하지 못해 계산하지 않았다.

## 1. 적용 법령 및 감독기관

폴란드는 EU 회원국이므로 GDPR 이 직접 적용되고, 2018년 5월 10일 개인정보 보호법(Ustawa o ochronie danych osobowych)이 국내 이행법이다(이하 이 문서에서 UODO 는 이 법률을 가리킨다). 감독기관은 개인정보보호청장(Prezes Urzędu Ochrony Danych Osobowych, PUODO) 단일 기관이다. 폴란드 법제의 특징은 **PESEL 이 출생 시 부여되는 범용 국가 식별번호**라는 점이다. PESEL 안에 생년월일과 성별이 인코딩되어 있고, 행정·의료·은행·통신 등 거의 모든 분야에서 본인확인 키로 쓰인다. PUODO 는 PESEL 을 "특별히 보호해야 할 식별 데이터"로 다루며, PESEL 유출 사고에 대해 GDPR 제33조 통지 의무와 고액 과징금을 반복적으로 적용해 왔다. 2023년 개정 법률로 PESEL 처리 제한(zastrzeżenie numeru PESEL) 제도가 도입되어, 개인이 자신의 PESEL 을 신용 거래에 쓰지 못하도록 잠글 수 있다.

| 법령 | 감독기관 | 적용 범위 요약 |
|---|---|---|
| GDPR (Regulation (EU) 2016/679) 제4조, 제9조, 제32조, 제33조, 제87조 | PUODO (Prezes Urzędu Ochrony Danych Osobowych) | 개인정보 정의, 특수 범주, 처리 보안, 유출 통지, 국가 식별번호 이용 조건 위임 |
| Ustawa z dnia 10 maja 2018 r. o ochronie danych osobowych (약칭 u.o.d.o. 법률. 기관 약어 UODO 와 구분) | PUODO | GDPR 국내 이행, PUODO 의 권한과 절차 |
| Ustawa z dnia 24 września 2010 r. o ewidencji ludności 제15조–제16조 | 디지털부 (Ministerstwo Cyfryzacji), 내무행정부 | PESEL 의 부여·구조·PESEL 등록부 |
| Ustawa z dnia 7 lipca 2023 r. (PESEL 처리 제한 도입 개정) | 디지털부 | PESEL 처리 제한(zastrzeżenie) 제도, 금융기관의 확인 의무 |
| Ustawa z dnia 6 sierpnia 2010 r. o dowodach osobistych 제12조 | 내무행정부 | 신분증(dowód osobisty)의 내용과 번호 |
| Ustawa z dnia 27 stycznia 2022 r. o dokumentach paszportowych | 내무행정부 | 여권 발급과 번호 |
| Ustawa z dnia 13 października 1995 r. o zasadach ewidencji i identyfikacji podatników i płatników 제2조–제3조; Ordynacja podatkowa 제293조 | 재무부 (KAS) | NIP 의 부여(개인은 PESEL 로 대체), 조세 비밀 |
| Prawo o ruchu drogowym (20 czerwca 1997 r.) 제71조–제73조, 제80a조 이하; Ustawa o kierujących pojazdami (5 stycznia 2011 r.) | 인프라부, 디지털부 (CEPiK 운영) | 차량 등록·번호판, 운전면허, 중앙 차량·운전자 등록부(CEPiK) |
| Prawo bankowe 제104조; Ustawa o usługach płatniczych | KNF, NBP | 은행 비밀, 계좌 식별자(NRB/IBAN) |
| Prawo komunikacji elektronicznej (12 lipca 2024 r., 구 Prawo telekomunikacyjne 대체) | UKE, PUODO | 통신 가입자 정보, 동의 없는 마케팅 통신 금지 |
| Kodeks karny 제190a조 제2항, 제267조 | (감독기관 없음. 검찰이 소추) | 신원 도용(타인 개인정보 사칭), 정보 무단 취득 처벌 |
| Ustawa o statystyce publicznej (REGON); Ustawa o Krajowym Rejestrze Sądowym (KRS) | GUS, 법무부 | REGON·KRS 는 공개 사업자 번호 |

## 2. 요약 표

| pii_type | 설명 | 결정론적 검출 | 권장 검출 방식 | 검증기 (현재 / 구현 가능) | score | 기존 구현 | 채택 |
|---|---|---|---|---|---|---|---|
| pl_pesel | 국가 식별번호 (PESEL, 11자리) | 가능 | regex (+ `pl_pesel` 검증기) | 없음 / 가중합 mod 10 체크 디지트 + 생년월일 유효성 | 사용 고려 | 신규 | 채택 |
| pl_id_card | 신분증 번호 (dowód osobisty, `ABA300000`) | 가능 | regex (+ `pl_id_card` 검증기) | 없음 / 가중치 `7 3 1 9 7 3 1 7 3` 체크 디지트 (확인 필요) | 사용 고려 | 신규 | 채택 |
| pl_passport | 여권번호 (`AA1234567`) | 가능 | regex (+ `mrz_731`, 체크 디지트 동반 시) | 없음 / 자체 체크 디지트 (확인 필요), MRZ 7-3-1 (10자리 표기에만) | 사용 고려 | 신규 | 채택 |
| pl_driver_license | 운전면허번호 (`00123/45/6789`) | 가능 (형식 확인 필요) | regex | 없음 / 확인 필요 | 사용 고려 | 신규 | 조건부 채택 (형식 명세 확인 후) |
| pl_iban | 폴란드 IBAN / NRB (26자리 계좌번호) | 가능 | regex 또는 Aho-Corasick (+ `iban` 검증기) | 없음 / ISO 7064 mod 97-10 (NRB 는 `PL` 을 붙여 같은 검증) | 기본 (IBAN) / 사용 고려 (NRB 단독) | 신규 | 조건부 채택 (공통 항목 `iban` 으로 이관 검토, NRB 단독 표기는 폴란드 고유) |
| pl_phonenumber (recognizer `pl_phonenumber`) | 휴대전화번호 (접두 `45`, `50`-`51`, `53`, `57`, `60`, `66`, `69`, `72`-`73`, `78`-`79`, `88`) | 가능 | regex | 없음 / 휴대전화 접두 표 | 사용 고려 | 신규 | 채택 |
| pl_phonenumber (recognizer `pl_phonenumber_landline`) | 유선전화번호 (지역번호 2자리 + 7자리) | 가능 (약함) | regex | 없음 / 지역번호 표 | **사용 필요** | 신규 | 채택 (점수 체계 도입이 선행 조건) |
| pl_vehicle_plate | 차량 번호판 (`WA 12345`) | 가능 (약함) | regex (정밀도 필요 시 byte-scan + 지역 코드 표) | 없음 / 통화·규격 접두 배제 목록, 지역 코드 표 | **사용 필요** | 신규 | 채택 (점수 체계 도입이 선행 조건) |
| pl_nip | 세금 번호 (NIP, 10자리) | 가능 | regex (+ `pl_nip` 검증기) | 없음 / 가중합 mod 11 | 사용 고려 / 기본 (`PL` 접두) | 신규 | 미채택 (보류) |

이외에 검토했으나 결정론적 검출이 불가능하거나 공개 번호라서 미채택한 항목은 4절에 정리했다.

## 3. 항목별 상세

### pl_pesel

- **설명**: PESEL (Powszechny Elektroniczny System Ewidencji Ludności). 출생 시 또는 거주 등록 시 부여되는 11자리 번호로 `YYMMDD SSS G K` 구조이다. `YYMMDD` 는 생년월일이며 세기는 월에 더한 값으로 구분한다(1900년대 `01`-`12`, 2000년대 `21`-`32`, 2100년대 `41`-`52`, 2200년대 `61`-`72`, 1800년대 `81`-`92`). `SSS` 는 일련번호, `G` 는 성별(짝수 여성, 홀수 남성), `K` 는 가중치 `1 3 7 9 1 3 7 9 1 3` 으로 계산한 체크 디지트이다. 신분증·여권·운전면허·건강보험(NFZ)·은행·통신 계약에 예외 없이 기재된다.
  - 예시: `85051012310` (1985-05-10 출생 남성, 형식 예시), `02212200225` (2002-01-22 출생 여성, 형식 예시), `44051401359` (폴란드어 위키백과가 구조 설명에 쓰는 예시). 모두 python-stdnum 으로 체크 디지트와 생년월일을 확인했다.
- **법적 근거**:
  - 법령: Ustawa o ewidencji ludności 제15조–제16조, 2023년 PESEL 처리 제한 개정법, UODO, GDPR 제87조, Kodeks karny 제190a조 제2항
  - 감독기관: PUODO, 디지털부
  - 노출 금지 이유: 폴란드의 범용 식별자이자 생년월일·성별을 그대로 담고 있다. PESEL + 이름 + 신분증 번호로 대출·통신 계약 사기가 가능해 2023년 PESEL 잠금 제도가 도입될 정도로 유출 피해가 크다. PUODO 는 PESEL 유출을 고위험 사고로 보고 통지·과징금을 적용한다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{2}(0[1-9]\|1[0-2]\|2[1-9]\|3[0-2])(0[1-9]\|[12][0-9]\|3[01])[0-9]{5}` | `85051012310`, `02212200225`, `44051401359` (`85131012310`(월 13), 10자리, 뒤에 영문자가 붙은 것은 거부) | score 사용 고려. 월·일 범위로 11자리 숫자열의 상당수를 걸러내지만, 날짜처럼 보이는 11자리(주문번호 등)는 통과하므로 `pl_pesel` 검증기(체크 디지트 1/10 + 월별 일수) 병행이 사실상 필수. 검증기 없이 등록한다면 score 사용 필요. 1900·2000년대만 허용하며 2100년대(`41`-`52`)와 1800년대(`81`-`92`)는 현존 인구가 없어 제외. `boundary_check: true` 적용 |

    오탐: 검증기 없이는 중간, 검증기를 붙이면 낮다.
  - **byte-scan handwritten**: 가능. 숫자열 11자리를 뽑아 날짜·체크 디지트를 코드로 검사한다. 오탐률은 regex + `pl_pesel` 조합과 **동일**하다.
  - **Aho-Corasick**: 부적합. 고정 접두가 없다.
  - **권장**: regex + `pl_pesel` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 앞 10자리에 가중치 `1 3 7 9 1 3 7 9 1 3` 을 곱해 합한 값 s 에 대해 `(10 - s mod 10) mod 10` 이 11번째 자리와 같으면 유효하다. 월 값에서 세기를 분리해 실제 날짜가 유효한지도 검사한다. 검증기 `pl_pesel` 로 구현한다(python-stdnum `pl.pesel` 과 동일. 단 stdnum 은 5개 세기를 모두 허용하고 이 문서의 regex 는 1900·2000년대만 허용하므로, 검증기도 regex 와 같은 범위로 맞춘다).
- **채택 여부 및 근거**: 채택. 폴란드의 최고 등급 식별자이며 검증기가 있다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `pesel`, `numer pesel`, `nr pesel`, `dowód`, `dowod`, `identyfikator`, `national id`

### pl_id_card

- **설명**: 신분증(dowód osobisty) 번호. 대문자 3자 + 숫자 6자리의 9자리이며(예: `ABA300000`), 4번째 자리(첫 숫자)가 체크 디지트이다. 공개된 규칙은 9자리 전체에 가중치 `7 3 1 9 7 3 1 7 3` 을 곱해(문자는 `A`=10 … `Z`=35) 합한 값이 10의 배수이면 유효하다는 것이다(확인 필요). 2019년 이후 발급되는 전자 신분증(e-dowód)도 같은 번호 체계를 쓴다.
  - 예시: `ABA300000`, `ABC523456`, `CAA312345` (형식 예시. 위 규칙을 통과하도록 계산한 값)
- **법적 근거**:
  - 법령: Ustawa o dowodach osobistych 제12조, UODO, GDPR 제87조, Kodeks karny 제190a조 제2항
  - 감독기관: 내무행정부, PUODO
  - 노출 금지 이유: PESEL 과 함께 본인확인의 두 축이다. 신분증 번호 + PESEL 조합이 통신·대출 계약의 본인확인 기준이라 신원 도용에 직결된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{3} ?[0-9]{6}` | `ABA300000`, `ABC 523456` (`AB123456`, `ABCD123456` 는 거부) | score 사용 고려. `대문자 3 + 숫자 6` 은 제품·예약 코드와 겹칠 수 있으나 `pl_id_card` 검증기(1/10)로 보완된다. 스페인 여권(`[A-Z]{3}[0-9]{6}`)과 형식이 같으므로 두 recognizer 가 동시에 활성화되면 같은 값을 잡는다. `boundary_check: true` 적용 |

    오탐: 중간.
  - **byte-scan handwritten**: 가능. 오탐률은 regex + 검증기와 **동일**하다.
  - **Aho-Corasick**: 부적합. 첫 세 문자가 발급 순서에 따른 문자열이라 목록이 열려 있다.
  - **권장**: regex + `pl_id_card` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 위 가중합 규칙. 검증기 `pl_id_card` 로 구현하되, 규칙을 내무행정부 자료로 확인한 뒤 구현한다.
- **채택 여부 및 근거**: 채택. 핵심 신분증이며 체크 디지트가 있다(규칙 확인 필요).
- **기존 구현 여부**: 신규
- **context_words 후보**: `dowód osobisty`, `dowod osobisty`, `numer dowodu`, `seria i numer`, `e-dowód`, `identity card`

### pl_passport

- **설명**: 여권(paszport) 번호. 대문자 2자 + 숫자 7자리의 9자리이다(예: `AA1234567`). 3번째 자리(첫 숫자)가 체크 디지트라는 자료가 있으나 가중치를 확인하지 못했다(확인 필요). MRZ 에는 별도로 7-3-1 체크 디지트가 붙는다.
  - 예시: `AA1234567`, `EK 1234567` (형식 예시. 자체 체크 디지트는 규칙 미확인이라 검증하지 않았다)
- **법적 근거**:
  - 법령: Ustawa o dokumentach paszportowych, UODO, GDPR 제87조
  - 감독기관: 내무행정부, PUODO
  - 노출 금지 이유: 정부 발급 신분증 번호로서 항공·호텔·은행 KYC 에 쓰인다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{2} ?[0-9]{7}[0-9]?` | `AA1234567`, `EK 1234567` | score 사용 고려. `대문자 2 + 숫자 7` 은 이탈리아 여권·구형 신분증과 같은 형식이다. 선택 꼬리는 MRZ 체크 디지트 표기용이며 10자리 매치에만 `mrz_731` 적용. `boundary_check: true` 적용 |

    오탐: 중간.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 부적합.
  - **권장**: regex + `mrz_731`(10자리 매치에만). 자체 체크 디지트 규칙이 확인되면 `pl_passport` 검증기를 추가한다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 자체 체크 디지트(규칙 확인 필요), MRZ 동반 시 `mrz_731`(de_DE 문서).
- **채택 여부 및 근거**: 채택. 정부 발급 신분증 번호이다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `paszport`, `numer paszportu`, `passport`

### pl_driver_license

- **설명**: 운전면허(prawo jazdy) 번호. 카드형 면허증의 번호는 `숫자 5 / 숫자 2 / 숫자 4`(예: `00123/45/6789`) 형식으로 알려져 있으며, 앞 5자리가 일련번호, 가운데 2자리가 발급 연도, 뒤 4자리가 발급 관청 코드라는 자료와 그 반대 순서라는 자료가 있어 공식 명세 확인이 필요하다. 운전면허 기록은 CEPiK 에서 PESEL 로 조회되므로 면허번호 자체의 식별력은 PESEL 보다 낮다.
  - 예시: `00123/45/6789` (형식 예시. 구조 미확인이라 검증하지 않았다)
- **법적 근거**:
  - 법령: Ustawa o kierujących pojazdami, Prawo o ruchu drogowym 제80a조 이하 (CEPiK), UODO
  - 감독기관: 인프라부, 디지털부 (CEPiK), PUODO
  - 노출 금지 이유: 신분증 대용으로 쓰이며 CEPiK 기록과 연결된다.
- **결정론적 검출 가능성**: 가능하나 형식이 확인되지 않았다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{5}/[0-9]{2}/[0-9]{4}` | `00123/45/6789` | score 사용 고려. 슬래시 구분 `5/2/4` 구조는 비교적 특이하지만, 형식 확인 전에는 등록하지 않는다 |

  - **byte-scan handwritten**: 구조 확인 후 판단.
  - **Aho-Corasick**: 부적합.
  - **권장**: 형식 명세 확인 후 결정.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 확인 필요.
- **채택 여부 및 근거**: 조건부 채택. 형식 명세 확인이 조건이다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `prawo jazdy`, `numer prawa jazdy`, `driver's license`, `driving licence`

### pl_iban

- **설명**: 폴란드 IBAN 과 NRB. 국내 계좌번호 NRB(Numer Rachunku Bankowego)는 `체크 2 + 은행·지점 8 + 계좌 16` 의 26자리 숫자이고, IBAN 은 앞에 `PL` 을 붙인 28자리이다. NRB 의 앞 2자리가 곧 IBAN 의 mod 97 체크 디지트이므로 NRB 단독 표기도 `PL` 을 붙여 같은 검증을 할 수 있다. 서면에서는 `61 1090 1014 0000 0712 1981 2874` 처럼 2 + 4×6 으로 띄어 쓴다.
  - 예시: `PL61109010140000071219812874`, `PL61 1090 1014 0000 0712 1981 2874` (IBAN 표준 견본. mod 97 통과), NRB 표기 `61 1090 1014 0000 0712 1981 2874`
- **법적 근거**:
  - 법령: Prawo bankowe 제104조 (은행 비밀), Ustawa o usługach płatniczych, UODO, GDPR 제4조
  - 감독기관: KNF, PUODO
  - 노출 금지 이유: IBAN 만으로 SEPA 자동이체 위조가 가능하고, 폴란드는 급여·임대료가 계좌이체로 처리된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `PL[0-9]{2} ?([0-9]{4} ?){5}[0-9]{4}` | `PL61109010140000071219812874`, `PL61 1090 1014 0000 0712 1981 2874` (27자리, `DE89…` 은 거부) | 기본. `PL` 접두 + 28자리 + `iban` 검증기. BBAN 은 규격(`24!n`)상 모두 숫자. 마지막 그룹을 고정해 뒤따르는 공백이 매치에 들어가지 않게 했다. `boundary_check: true` 적용 |
    | `[0-9]{2} ?[0-9]{4} ?[0-9]{4} ?[0-9]{4} ?[0-9]{4} ?[0-9]{4} ?[0-9]{4}` (NRB 단독 표기) | `61 1090 1014 0000 0712 1981 2874`, `61109010140000071219812874` | score 사용 고려. 구분자 없는 26자리는 드물지만 다른 숫자열과 겹칠 수 있다. `PL` 을 붙여 `iban` 검증기(1/97)를 적용하면 낮아진다 |

    오탐: IBAN 은 낮고, NRB 단독은 검증기 병행 시 낮다.
  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: 공통 IBAN detector 로 확장하면 적합(de_DE 문서 참조). `PL` 을 국가 코드 anchor 목록에 등록한다.
  - **권장**: 공통 `iban` recognizer + `iban` 검증기. NRB 단독 표기는 폴란드 고유로 유지하되 검증은 `PL` 접두를 붙여 `iban` 을 재사용한다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: `iban`(ISO 7064 mod 97-10, de_DE 문서와 동일). NRB 단독 표기는 검증기 안에서 `PL` 을 앞에 붙인 뒤 같은 계산을 한다. 별도 검증기가 필요 없다.
- **채택 여부 및 근거**: 조건부 채택. IBAN 부분은 공통 항목으로 이관하고, NRB 단독 표기 recognizer 만 폴란드 고유로 둔다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `iban`, `numer rachunku`, `nr rachunku`, `rachunek bankowy`, `konto`, `przelew`, `nrb`(3글자, 제외), `bank`

### pl_phonenumber

- **설명**: 폴란드 전화번호. 국가번호 `+48`, 국내 형식은 9자리 고정이며 선행 `0` 이 없다. 휴대전화는 `45`, `50`, `51`, `53`, `57`, `60`, `66`, `69`, `72`, `73`, `78`, `79`, `88` 로 시작하고(`52` 는 비드고슈치 유선 지역번호. 배정 대역은 UKE 공고로 재확인 필요) `501 234 567` 처럼 3-3-3 으로 쓴다. 유선은 지역번호 2자리(`22` 바르샤바, `12` 크라쿠프 등) + 7자리이며 `22 123 45 67` 처럼 2-3-2-2 로 쓴다.
  - 예시: 휴대전화 `501 234 567`, `+48 501 234 567`, `501234567`, `601-234-567`, `+48501234567`. 유선 `22 123 45 67`, `+48 22 123 45 67`, `221234567`, `12-345-67-89`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: GDPR 제4조, Prawo komunikacji elektronicznej (동의 없는 마케팅 통신 금지), UODO
  - 감독기관: UKE, PUODO
  - 노출 금지 이유: 휴대전화번호는 2단계 인증·BLIK(모바일 결제)·mObywatel 인증의 열쇠이다.
- **결정론적 검출 가능성**: 휴대전화는 가능, 유선은 가능하나 약하다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `(\+48 ?)?[4-8][0-9]{2}[ -]?[0-9]{3}[ -]?[0-9]{3}` | `501 234 567`, `+48 501 234 567`, `501234567`, `601-234-567`, `+48501234567` (`301 234 567`, 8자리는 거부) | score 사용 고려. 첫 자리 `4`-`8` 과 9자리 고정 길이가 필터이지만, `[4-8]` 은 유선 지역번호 `41`-`89` 대부분을 포함하므로 구분자 없는 유선번호(`421234567` 등)가 휴대전화로 매칭되고, 다른 9자리 숫자열과도 겹친다. 휴대전화 접두 표(위 목록)를 regex 대안이나 검증기로 넣으면 좁아진다. `boundary_check: true` 적용 |
    | `(\+48 ?)?[1-9][0-9][ -]?[0-9]{3}[ -]?[0-9]{2}[ -]?[0-9]{2}` | `22 123 45 67`, `+48 22 123 45 67`, `221234567`, `12-345-67-89` (`02 …`, 8자리는 거부) | **score 사용 필요**. 첫 자리 제한이 `1`-`9` 뿐이라 구분자 없는 9자리는 휴대전화 패턴과도 겹치고 다른 숫자열과도 겹친다. 지역번호 표(약 50개)를 넣으면 좁아진다 |

    오탐: 휴대전화는 중간, 유선은 높다.
  - **byte-scan handwritten**: 가능하나 이점이 적다.
  - **Aho-Corasick**: `+48`(3바이트)만 anchor 로 적합하다. 국내 표기는 접두가 2자리라 흔하다.
  - **권장**: 휴대전화는 regex, 유선은 점수 체계 도입 후 낮은 `score` 의 별도 recognizer(`pl_phonenumber_landline`).
- **검증기**:
  - 현재: 없음
  - 구현 가능: 휴대전화 접두 표와 유선 지역번호 표(UKE 공고, 최신 공고로 재확인 필요).
- **채택 여부 및 근거**: 휴대전화는 채택. 유선은 채택하되 점수 체계 도입이 선행 조건이며 그 전에는 등록하지 않는다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `telefon`, `numer telefonu`, `nr tel`, `komórka`, `komorka`, `kontakt`, `zadzwoń`, `phone`. (`tel` 은 3글자라 제외한다.)

### pl_vehicle_plate

- **설명**: 차량 번호판(tablica rejestracyjna). 2000년 이후 형식은 `지역 코드 2-3자 + 공백 + 식별자 4-5자(숫자·문자 혼합)` 이다(예: `WA 12345`, `KR 1234A`, `DW 123AC`, `WPR 1234A`). 첫 문자는 주(voivodeship), 이어지는 1-2자는 군(powiat)을 나타내며, 식별자 부분에는 숫자와 혼동되는 `B`, `D`, `I`, `O`, `Z` 를 쓰지 않는다(확인 필요. 아래 regex 는 이 규칙을 반영했다). 번호판은 차량 등록 시 부여되며 CEPiK 에서 소유자와 연결된다.
  - 예시: `WA 12345`, `KR 1234A`, `DW 123AC`, `WPR 1234A`, `WPR A1234`. 모두 형식 예시이다.
- **법적 근거**:
  - 법령: Prawo o ruchu drogowym 제71조–제73조 (등록·번호판), 제80a조 이하 (CEPiK), UODO, GDPR 제4조. PUODO 는 번호판을 소유자와 결합 가능한 개인정보로 본다.
  - 감독기관: 인프라부, 디지털부 (CEPiK), PUODO
  - 노출 금지 이유: CEPiK 에서 번호판으로 소유자 정보를 조회할 수 있고(정당한 이익 요건 하에), 통행 기록과 결합하면 위치 추적이 가능하다. 공개 노출되는 번호라 단독 위험도는 낮다.
- **결정론적 검출 가능성**: 가능하나 정밀도가 낮다.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[A-Z]{2,3} ([0-9][0-9ACEFGHJKLMNPRSTUVWXY]{3,4}\|[ACEFGHJKLMNPRSTUVWXY][0-9][0-9ACEFGHJKLMNPRSTUVWXY]{2,3})` | `WA 12345`, `KR 1234A`, `DW 123AC`, `WPR 1234A`, `WPR A1234` (`W 12345`, `WA 123`, 공백 없는 `WA123456`, `DW 123AB`(B 포함), `THE HOUSE`, `NEW YORK`, `FOR SALE` 은 거부) | **score 사용 필요**. 식별자 문자 집합을 `B`·`D`·`I`·`O`·`Z` 제외로 좁히고 첫 두 자리 중 하나를 숫자로 요구해 대문자 두 단어(`THE HOUSE` 등)는 걸러냈지만, `ISO 9001`, `PLN 12345`, `EUR 10000` 같은 규격·통화 표기는 여전히 매칭된다. 점수 체계 도입 전에는 등록하지 않는다. `boundary_check: true` 적용 |

    오탐: 높다. 문자 집합을 좁히지 않은 `[A-Z]{2,3} [0-9A-Z]{4,5}` 는 임의의 대문자 두 단어를 전부 잡으므로 쓰지 않는다.
  - **byte-scan handwritten**: **적합**. 지역 코드 표(약 400개)를 코드 표로 두고 대조하면 정밀해지면서 DFA 비대화를 피한다(de_DE 번호판과 같은 구조). 오탐률은 지역 코드 표를 쓴 regex 와 **동일**하다.
  - **Aho-Corasick**: 지역 코드 + 공백(`WA `, `KR `)을 anchor 로 등록하는 것이 가능하나 2-3바이트 코드가 많아 verifier 호출이 잦다.
  - **권장**: 점수 체계 도입 후 낮은 `score` 로 등록하고, `ISO`, `PLN`, `NIP`, `VAT`, `EUR`, `USD` 같은 통화·규격 접두를 제외하는 검증기를 병행한다(es_ES 구형 번호판과 같은 처리). 정밀도가 필요하면 byte-scan + 지역 코드 표(약 400개)로 전환한다. de_DE 는 하이픈 구분으로 오탐을 줄일 수 있었지만 폴란드 번호판은 공백 구분만 쓰므로 같은 방법을 쓸 수 없다.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 체크섬 없음. 지역 코드 표 대조와 통화·규격 접두 배제 목록.
- **채택 여부 및 근거**: 채택하되 점수 체계 도입이 선행 조건이다. PUODO 가 개인정보로 보고 CEPiK 조회로 소유자 특정이 가능하지만, 검증기가 없고 공백 구분 형식이라 context 단어 없이는 오탐을 제어할 수 없다.
- **기존 구현 여부**: 신규
- **context_words 후보**: `tablica rejestracyjna`, `numer rejestracyjny`, `nr rej`, `rejestracja`, `pojazd`, `samochód`, `samochod`, `license plate`

### pl_nip

- **설명**: NIP (Numer Identyfikacji Podatkowej). 재무부가 사업자·법인에 부여하는 10자리 세금 번호로, 가중치 `6 5 7 2 3 4 5 6 7` 을 곱해 합한 값을 11 로 나눈 나머지가 10번째 자리와 같으면 유효하다(나머지 10은 발급하지 않음). `856-734-62-15` 또는 `856-73-46-215` 로 구분해 쓰고 EU 거래에서는 `PL` 을 붙인다. 2011년 이후 사업을 하지 않는 개인은 NIP 대신 PESEL 을 세금 식별자로 쓰므로, 현재 NIP 는 사실상 사업자 번호이다.
  - 예시: `856-734-62-15`, `8567346215`, `PL 8567346215` (python-stdnum 문서 예시), `1234567009` (형식 예시. 체크 디지트 통과)
- **법적 근거**:
  - 법령: Ustawa o zasadach ewidencji i identyfikacji podatników i płatników 제2조–제3조, Ordynacja podatkowa 제293조. 사업자의 NIP 는 CEIDG(개인사업자 등록부)와 KRS 에서 **공개 조회**되고 송장·웹사이트에 기재가 의무이다.
  - 감독기관: 재무부 (KAS)
  - 노출 금지 이유: 약하다. 공개가 원칙인 사업자 번호이다. 다만 개인사업자의 NIP 는 CEIDG 에서 이름·주소와 함께 공개된다.
- **결정론적 검출 가능성**: 가능.
  - **regex** (기본):

    | regex | 매칭 예시 | 비고 (score 사용 필요 등) |
    |---|---|---|
    | `[0-9]{3}[- ]?[0-9]{3}[- ]?[0-9]{2}[- ]?[0-9]{2}` | `856-734-62-15`, `8567346215` | score 사용 고려. 10자리 숫자열이지만 `pl_nip` 검증기(1/11)로 좁힐 수 있다. 미채택 항목 |
    | `[0-9]{3}[- ]?[0-9]{2}[- ]?[0-9]{2}[- ]?[0-9]{3}` | `856-73-46-215` | 위와 같다(다른 구분 표기) |
    | `PL ?[0-9]{10}` | `PL 8567346215`, `PL8567346215` | 기본에 가깝다. `PL` 접두가 필터. 미채택 항목 |

  - **byte-scan handwritten**: 가능하나 이점이 없다.
  - **Aho-Corasick**: `PL` 접두 형태는 공통 IBAN detector 와 anchor 를 공유할 수 있으나 미채택이라 검토만 한다.
  - **권장**: (채택 시) regex + `pl_nip` 검증기.
- **검증기**:
  - 현재: 없음
  - 구현 가능: 위 가중합 mod 11. 검증기 `pl_nip` 로 구현한다(python-stdnum `pl.nip` 과 동일).
- **채택 여부 및 근거**: 미채택 (보류). 공개 사업자 번호이므로 마스킹 대상으로 보기 어렵다. 개인사업자 보호 요구가 생기면 검증기가 단순해 도입 비용이 낮다.
- **기존 구현 여부**: 신규 (미채택이므로 구현하지 않음)
- **context_words 후보** (재검토 시 참고): `nip`, `numer nip`, `numer identyfikacji podatkowej`, `vat number`

## 4. 검토 후 미채택한 항목

아래 항목은 법령상 PII 이거나 식별번호이지만 결정론적 검출이 불가능하거나 공개 번호라서 recognizer 로 등록하지 않는다.

| 항목 | 법적 근거 | 미채택 이유 |
|---|---|---|
| REGON (9자리 또는 14자리 사업자 통계번호) | Ustawa o statystyce publicznej | GUS 등록부에서 공개 조회되는 사업자 번호이다. 체크 디지트(9자리 기준 가중치 `8 9 2 3 4 5 6 7`. 14자리는 별도 가중치)는 stdnum 과 대조했으나 미채택이라 구현하지 않는다. |
| KRS 번호 (10자리 법인 등기번호) | Ustawa o KRS | 공개 등기 정보이다. |
| 건강보험 번호 | Ustawa o świadczeniach opieki zdrowotnej | NFZ 는 PESEL 을 식별자로 쓰므로 `pl_pesel` 이 담당한다. EHIC 카드 번호는 형식 명세를 확인하지 못했다. |
| Numer karty pobytu (체류 카드 번호) | Ustawa o cudzoziemcach | 형식 명세를 확인하지 못했다. 이민 신분 노출 위험은 인정한다. |
| Kod pocztowy (`12-345`) | GDPR | `2-3` 숫자 표기는 특이하지만 단독 식별력이 낮다. |
| mObywatel 식별자, 프로필 자우파니(profil zaufany) | Ustawa o informatyzacji | 텍스트에 번호 형태로 나타나지 않는다. |
| 주소, 이름, 생년월일 | GDPR 제4조 | 국가 종속 항목이 아니며 regex 로 결정론적 검출이 불가능하다. 공통 항목 또는 NER 로 다룬다. |
| 생체정보, 건강 상태, 종교·노조 가입 | GDPR 제9조 | 특수 범주이지만 번호 형태로 나타나지 않는다. |
| 신용카드번호, 이메일, IP 주소 | GDPR, PCI DSS | 국가 종속 항목이 아니므로 이 문서 범위 밖이다. 기존 `card_number` 등이 담당한다. |

## 5. 구현 시 후속 작업 요약

이 문서에서 도출된, YAML·`validator.rs`·`handwritten/`·엔진에 반영할 작업 목록이다. 검증기는 **함수 구현 → YAML 등록** 순서를 지킨다(`validator::validate` 가 fail-open 이므로 순서가 바뀌면 검증 없이 통과한다).

| 순서 | 작업 | 대상 | 종류 |
|---|---|---|---|
| 선행 | recognizer 단위 `score` 필드와 context 가산 방식 도입 (en_US 문서 5절과 공통. 이미 완료되었으면 이 행 삭제) | 엔진 | 엔진 변경 |
| 1 | `pl_pesel` 검증기(가중합 mod 10 + 생년월일 유효성)와 `pl_pesel` recognizer 추가 | pl_pesel | validator 신규, YAML 신규 |
| 2 | 신분증 번호 체크 디지트 규칙을 내무행정부 자료로 확인한 뒤 `pl_id_card` 검증기와 recognizer 추가 | pl_id_card | 조사, validator 신규, YAML 신규 |
| 3 | `pl_passport` recognizer 추가 (`mrz_731` 검증기는 de_DE 작업과 공용). 자체 체크 디지트 규칙 확인 시 `pl_passport` 검증기 추가 | pl_passport | YAML 신규, 조사 |
| 4 | NRB 단독 표기 recognizer 추가 (`iban` 검증기에 `PL` 접두 부여 분기). IBAN 부분은 (공통 항목 이관 확정 시) 공통 `iban` recognizer 의 국가 길이 표에 `PL` 28 을 등록 | pl_iban, iban (공통) | YAML 신규, validator 수정 |
| 5 | `pl_phonenumber` 휴대전화 recognizer 추가 (`boundary_check: true`) | pl_phonenumber | YAML 신규 |
| 6 | `pl_phonenumber_landline` recognizer 추가 (`score` 낮게). **선행 작업 완료 후에만** | pl_phonenumber | YAML 신규 |
| 7 | `pl_vehicle_plate` recognizer 추가 (`score` 낮게, 통화·규격 접두 배제 검증기 병행). **선행 작업 완료 후에만**. 정밀도 필요 시 지역 코드 표 기반 byte-scan | pl_vehicle_plate | YAML 신규, validator 신규 |
| 8 | `pl_driver_license` 형식 명세 확인 후 등록 여부 결정 | pl_driver_license | 조사 |
| 선택 | `pl_nip` recognizer 와 검증기 (개인사업자 보호 요구 시) | pl_nip | validator 신규, YAML 신규 |
