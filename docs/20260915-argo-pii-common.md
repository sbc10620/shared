# ARGO PII 공통 항목과 구현 순서 (13개국 종합)

이 문서는 13개 국가별 PII 근거 문서(`docs/20260914-argo-pii-en_US.md`, `docs/20260915-argo-pii-<locale>.md` 12개)가 반복해서 위임한 **공통 요소**를 한곳에 모으고, 구현 순서를 제안한다. 국가별 판단의 근거는 각 문서에 있으며 여기서는 옮겨 적지 않는다. 대상 locale 은 en_US, ko_KR, en_GB, de_DE, fr_FR, it_IT, es_ES, en_IN, pt_BR, es_MX, vi_VN, th_TH, pl_PL 이고, `pii_type` 접두는 ISO 3166 국가 코드(`us`, `kr`, `gb`, `de`, `fr`, `it`, `es`, `in`, `br`, `mx`, `vn`, `th`, `pl`)를 쓴다.

## 1. 집계

13개 문서의 요약 표 130행을 채택 열과 score 열 기준으로 집계한 결과이다(2026-09-15 기준).

| locale | 항목 수 | 채택 | 조건부 채택 | 미채택 | score 사용 필요 |
|---|---|---|---|---|---|
| en_US | 13 | 9 | 2 | 2 | 4 |
| ko_KR | 9 | 7 | 0 | 2 | 1 |
| de_DE | 11 | 7 | 3 | 1 | 2 |
| fr_FR | 9 | 4 | 4 | 1 | 3 |
| it_IT | 10 | 6 | 3 | 1 | 2 |
| es_ES | 8 | 5 | 2 | 1 | 1 |
| pl_PL | 9 | 4 | 4 | 1 | 2 |
| en_GB | 11 | 6 | 4 | 1 | 2 |
| en_IN | 11 | 7 | 3 | 1 | 1 |
| pt_BR | 12 | 7 | 4 | 1 | 3 |
| es_MX | 9 | 7 | 1 | 1 | 1 |
| vi_VN | 10 | 6 | 3 | 1 | 3 |
| th_TH | 8 | 4 | 3 | 1 | 3 |
| **합계** | **130** | **79** | **36** | **15** | **28** |

- 분류 기준: 채택 열이 "미채택"으로 시작하면 미채택, "선행" 또는 "조건부"를 포함하면 조건부 채택, 그 외는 채택으로 셌다. "일부 패턴은 바로, 일부는 점수 체계 후" 구조인 항목 5건(us_alien_registration_number, fr·es·br 번호판, th 은행 계좌)은 문구의 "선행" 유무에 따라 1건이 채택, 4건이 조건부로 갈렸다.
- "조건부 채택" 36건의 조건은 점수 체계 도입 21건, IBAN·VIN 공통 이관 8건, 형식 명세 확인 5건, 그 외 2건(gb_postcode 는 주소 마스킹 정책, in_bank_account 는 IFSC 조합 표기 한정)이다.
- "score 사용 필요" 28건은 점수 체계가 없는 동안 등록하지 않는다(기존 `us_passport` 만 예외로 현 상태 유지). 28건에는 미채택 2건(us_npi, kr_corporate_registration_number)이 포함되어 있으므로, 점수 체계 후 실제로 등록되는 것은 최대 26건이다.
- "미채택" 15건은 대부분 공개 사업자 번호(EIN, SIREN, P.IVA, CIF, NIP, VAT, GSTIN, CNPJ, 법인 RFC, MST, 법인 등록번호)이며, 개인사업자 보호 요구가 생기면 대부분 기존 `luhn` 또는 단순 검증기로 즉시 도입할 수 있다.

## 2. 선행 엔진 변경: 점수 체계

모든 국가 문서의 5절 첫 행이 같은 선행 작업을 가리킨다. 근거는 en_US 문서 0절 "점수 체계와 context_words" 에 있으며 요지는 다음과 같다.

- 현재 `compute_score` (`recognizer.rs`)는 context 단어가 ±50자 안에 있으면 1.0, 없으면 0.5 를 돌려주고 임계값도 0.5 라서, **context_words 는 매치를 걸러내지 못하고 겹침 해소 우선순위에만 쓰인다.**
- 변경안: `RecognizerConfig` 와 `PatternMeta` 에 recognizer 단위 `score` 필드(기본 0.5)를 추가하고, `compute_score` 를 "기본 점수 + context 가산" 으로 바꾼다. 가산값은 **0.5** 를 권장한다. 그러면 기존 recognizer 의 context 매치 점수가 지금과 같은 1.0 으로 유지되어 `tinicore/tests/guardrails/filter_test.rs` 의 `score == 1.0` 단정 3건(5331·5441·5471행)이 그대로 통과한다.
- 정확도가 낮은 패턴은 같은 `pii_type` 의 별도 recognizer(예: `us_driver_license_numeric`, `<cc>_phonenumber_landline`)로 분리해 `score: 0.3` 처럼 낮게 준다. context 없이는 탈락하고 있으면 0.8 로 통과한다.
- 낮은 `score` recognizer 에 `context_words` 를 비워 두면 가산이 없어 모든 매치가 탈락한다.
- `card_number` 와 Aho-Corasick 계열(API 키, `kr_phonenumber`)은 Luhn·고정 접두가 이미 강한 필터라 `score` 를 지정할 필요가 없다.
- 겹침 해소(`detector.rs`)는 점수 → 길이 → 시작 위치 → **등록 순서**(pid) 로만 정한다. 같은 값을 같은 점수로 잡는 recognizer 가 여럿이면 YAML 등록 순서가 보고 `pii_type` 을 정하므로, 4절의 충돌 표를 보고 순서를 정한다. 단 handwritten recognizer 는 YAML 위치와 무관하게 모든 regex 뒤에 pid 를 받는다(`recognizer.rs` 의 deferred 처리).

## 3. 공통 검증기

`validator.rs` 에는 현재 `luhn`, `rrn`(자릿수만), `phonenumber`(항상 `true`) 세 개뿐이고, `validate()` 는 모르는 이름에 `true` 를 돌려주는 **fail-open** 이다. 따라서 모든 검증기는 **함수 구현 → YAML 등록** 순서로 작업한다.

### 3.1 여러 국가가 공유하는 검증기

| 검증기 | 알고리즘 | 쓰는 국가·항목 | 비고 |
|---|---|---|---|
| `luhn` (기존) | 표준 Luhn. 숫자만 걸러 계산하므로 공백·문자 섞인 표기도 처리 | 카드번호(기존), mx_nss, in_voter_id(문자 3자 무시 → 뒤 7자리). 미채택 항목 중 fr_siren_siret, it_partita_iva, es_cif(숫자 7자리), us_npi(래퍼 `npi`: `80840` 접두 후 Luhn)도 채택 시 재사용 | La Poste SIRET(자릿수 합 5의 배수)은 예외 |
| `iban` (신규) | ISO 7064 mod 97-10. 앞 4자를 뒤로 보내고 문자를 `A`=10…`Z`=35 로 바꿔 97 로 나눈 나머지가 1 | de_DE, en_GB, fr_FR, it_IT, es_ES, pl_PL, pt_BR (7개국) | 국가별 길이·영숫자 규칙은 3.2 표 |
| `mrz_731` (신규) | ICAO 9303. 문자 `A`=10…`Z`=35, `<`=0, 가중치 `7 3 1` 순환, mod 10 | 신분증·여권에 MRZ 체크 디지트가 함께 적힌 표기: de_DE·it_IT(신분증·여권 10자리), fr_FR·es_ES·pl_PL·en_GB·es_MX(여권 10자리), en_IN·pt_BR·vi_VN(9자리), th_TH(숫자 8자리 동반 시 9·10자리) | 검증기는 패턴 단위로 붙으므로, 체크 디지트 없는 짧은 표기는 검증기 안에서 길이를 보고 통과시킨다(fail-open 이 아니라 명시적 분기) |
| `verhoeff` (신규) | Verhoeff 순열·곱셈표 mod 10 | in_aadhaar(12자리, 회문 배제), VID(16자리) | |
| `nanp` (신규, `phonenumber` 대체) | NPA·NXX 첫 자리 `2`-`9`, NXX 가 `N11` 이 아님 | us_phonenumber | 기존 `phonenumber` 자리표시자를 이것으로 교체 |

### 3.2 IBAN 국가별 규칙

공통 `iban` recognizer 는 국가 코드 anchor(Aho-Corasick) 또는 국가별 regex 로 구성하고, 검증은 `iban` 하나로 한다. 국가 고유 2차 체크섬은 해당 국가 검증기로 BBAN 부분에 추가 적용한다.

| 국가 | 길이 | BBAN 구조 | 영숫자 자리 | 국가 고유 2차 검증 |
|---|---|---|---|---|
| DE | 22 | 은행 8 + 계좌 10 | 없음(모두 숫자) | 없음 |
| GB | 22 | 은행 코드 4(문자) + sort code 6 + 계좌 8 | 은행 코드 4자 | sort code modulus 검사는 VocaLink 표 필요(보류) |
| FR | 27 | 은행 5 + 지점 5 + 계좌 11 + RIB 키 2 | 계좌 11자리 | `fr_rib`(RIB 키, 문자 치환 후 mod 97) |
| IT | 27 | CIN 1(문자) + ABI 5 + CAB 5 + 계좌 12 | CIN, 계좌 12자리 | `it_cin`(홀짝 가중 mod 26, `it_cf` 와 표 공유) |
| ES | 24 | 은행 4 + 지점 4 + 체크 2 + 계좌 10 | 없음 | `es_ccc`(이중 체크 디지트, 가중치 `2^i` mod 11) |
| PL | 28 | 은행·지점 8 + 계좌 16 (IBAN 키 2자리를 앞에 붙인 26자리가 국내 NRB 표기) | 없음 | 없음(NRB 단독 표기는 `PL` 을 붙여 `iban` 재사용) |
| BR | 29 | 은행 8 + 지점 5 + 계좌 10 + 계좌 유형 1(문자) + 소유자 1(영숫자) | 끝 2자 | 없음 |

국내 계좌 표기 중 IBAN 과 별개로 recognizer 를 두는 것: fr_FR RIB 단독(`5-5-11-2`), es_ES CCC 단독(`4-4-2-10`), pl_PL NRB 단독(26자리), en_GB sort code + 계좌(`2-2-2 + 8`), ko_KR 은행별 8개 형식(기존), en_IN IFSC + 계좌, es_MX CLABE(18자리, 자체 체크 디지트), th_TH `3-1-5-1`. us_bank_account(ABA 라우팅 + 계좌)는 기존 recognizer 를 유지하고 `aba_routing` 검증기를 붙인다. 베트남은 계좌 형식이 없어 미채택.

### 3.3 국가 고유 검증기

| 검증기 | 국가 | 항목 | 알고리즘 요약 |
|---|---|---|---|
| `ssn` | US | 사회보장번호 | 지역 `000`·`666`·`9xx`, 그룹 `00`, 일련 `0000`, 광고용 `987-65-4320`-`4329` 배제 |
| `aba_routing` | US | 라우팅번호 | `3(d1+d4+d7)+7(d2+d5+d8)+(d3+d6+d9)` 가 10의 배수 |
| `dea` | US | DEA 번호 | `(d1+d3+d5)+2(d2+d4+d6)` 의 일의 자리 = d7 |
| `vin` | US(공통 후보) | 차대번호 | 49 CFR §565 치환표, 가중치 `8 7 6 5 4 3 2 10 0 9 8 7 6 5 4 3 2`, mod 11, `X`=10 |
| `rrn` 강화 | KR | 주민등록번호 | 월별 일수 검사 추가. 체크 디지트는 2020-10 이후 번호에 없어 거부 조건으로 쓰지 않음 |
| `de_idnr` | DE | 세금 ID | 반복 규칙(정확히 한 숫자만 2-3회) + ISO 7064 MOD 11,10 변형 |
| `de_svnr` | DE | 사회보험번호 | 문자→순번 2자리, 가중치 `2 1 2 5 7 1 2 1 2 1 2 1` 교차합 mod 10 |
| `de_kvnr` | DE | 건강보험 번호 | 문자→순번 2자리, 가중치 `1 2` 교대 교차합 mod 10 (`de_svnr` 와 helper 공유) |
| `fr_nir` | FR | 사회보장번호 | `97 - (앞 13자리 mod 97)`, 코르시카 `2A`→`19`·`2B`→`18` 치환만 |
| `fr_spi` | FR | 납세자 번호 | 마지막 3자리 = 앞 10자리 mod 511 |
| `fr_rib` | FR | RIB 키 | 문자 치환(A-I→1-9, J-R→1-9, S-Z→2-9) 후 `97-((89×은행+15×지점+3×계좌) mod 97)` |
| `it_cf` | IT | Codice Fiscale | 홀수 자리 특수 표·짝수 자리 순번, 합 mod 26 → 문자 |
| `it_cin` | IT | IBAN CIN | `it_cf` 와 같은 표를 BBAN 22자에 적용 |
| `es_dni` / `es_nie` | ES | DNI / NIE | mod 23 → `TRWAGMYFPDXBNJZSQVHLCKE`. NIE 는 X/Y/Z→0/1/2 치환 |
| `es_naf` | ES | 사회보장번호 | 앞 10자리 mod 97 (선행 0 처리 변형 확인 필요) |
| `es_ccc` | ES | 계좌 CCC | `00`+은행·지점 8, 계좌 10 각각 가중치 `2^i` mod 11, `r<2?r:11-r` |
| `pl_pesel` | PL | PESEL | 가중치 `1 3 7 9 1 3 7 9 1 3` mod 10 + 생년월일(월 값에 세기) |
| `pl_id_card` | PL | 신분증 | 가중치 `7 3 1 9 7 3 1 7 3`, 문자 A=10, 합 mod 10 = 0 (확인 필요) |
| `pl_nip` | PL | NIP(미채택) | 가중치 `6 5 7 2 3 4 5 6 7` mod 11 |
| `gb_nhs` | GB | NHS 번호 | 가중치 `10…2` mod 11, `11-r`(11→0, 10 무효) |
| `gb_utr` | GB | UTR | 첫 자리 체크. 가중치 `6 7 8 9 10 5 4 3 2`, 표 `21987654321` |
| `in_state_code` | IN | 운전면허·번호판 | 주 코드 표 대조 |
| `br_cpf` | BR | CPF | 이중 mod 11 + 동일 숫자 반복 배제 |
| `br_cnh` | BR | 운전면허 | 이중 mod 11(보정값·음수 처리 확인 필요) |
| `br_pis` | BR | PIS/PASEP | 가중치 `3 2 9 8 7 6 5 4 3 2` mod 11 |
| `br_titulo` | BR | 유권자증 | 이중 mod 11 + UF `01`·`02` 예외 |
| `br_cns` | BR | 건강 카드 | 첫 자리별 분기(1·2 / 7·8·9) 가중합 mod 11 |
| `mx_curp` | MX | CURP | 문자 순번 가중치 `18…2` 합 mod 10 + 주 코드 표 + 생년월일 |
| `mx_rfc` | MX | RFC | 특수 알파벳 가중치 `13…2` 합, `(11-s) mod 11` → 문자 |
| `mx_clabe` | MX | CLABE | 가중치 `3 7 1` 순환 mod 10 |
| `vn_citizen_id` | VN | 시민 신분번호 | 성 코드 표 + 세기·성별 자리 (체크섬 없음) |
| `vn_mst` | VN | 세금 코드(미채택) | 가중치 `31 29 23 19 17 13 7 5 3` mod 11 |
| `th_pin` | TH | 국민 ID(법인 등록번호 재사용) | 가중치 `13…2` mod 11, `(11-r) mod 10` |

python-stdnum 2.2 에 구현이 있는 것(`us.ssn`(광고용 번호 배제 포함)·`us.itin`·`us.rtn`(ABA)·`us.ein`, `kr.rrn`(체크 디지트+날짜), `de.idnr`·`de.stnr`, `fr.nir`·`fr.nif`, `it.codicefiscale`·`it.iva`, `es.dni`·`es.nie`·`es.ccc`·`es.cif`, `pl.pesel`·`pl.nip`·`pl.regon`, `gb.nhs`·`gb.utr`·`gb.vat`, `in_.aadhaar`·`in_.pan`·`in_.epic`·`in_.gstin`, `br.cpf`·`br.cnpj`, `mx.curp`·`mx.rfc`, `vn.mst`, `th.pin`·`th.moa`, `iban`, `luhn`, `verhoeff`)은 구현 시 테스트 벡터의 출처로 삼는다. 각 국가 문서의 예시 값은 이미 stdnum 또는 자체 계산으로 통과를 확인한 것이다(de_DE 문서 작성 당시에는 `stdnum.de.idnr` 을 참조하지 않았으나, 사후 확인 결과 문서 예시 `36574261809` 가 이 모듈로도 통과한다).

## 4. 국가 간 형식 충돌

locale 을 동시에 활성화하면 같은 형식의 번호를 여러 recognizer 가 잡는다. 엔진에는 locale 개념이 없으므로(계층 `layers` 안에서는 모든 recognizer 가 항상 활성), **구현 시 locale 별 recognizer 집합을 선택하는 기제**를 먼저 마련하는 것을 권장한다. 기존 `RecognizerConfig.layers` 가 계층별 집합 선택을 이미 하고 있으므로, 같은 구조의 `locales` 필드를 추가하는 것이 가장 작은 변경이다. 그 전까지는 아래 충돌을 등록 순서로 처리한다.

| 형식 | 잡는 항목 | 처리 |
|---|---|---|
| 숫자 9자리 | us_passport(기존), gb_passport, vn_old_id, br_rg(조건부), us_driver_license_numeric(조건부), **es_phonenumber·pl_phonenumber**(9자리 전화, 채택), it 휴대전화 9자리, 라우팅번호(계좌 조합 시) | 기존 `us_passport` 가 이미 모든 9자리를 잡으므로 gb·vn 은 보류 중 검출 공백 없음. 스페인·폴란드 휴대전화는 `us_passport` 와 동일 span·동일 점수라 등록 순서 결정 필요. locale 분리가 근본 해법 |
| 숫자 10자리 | gb_nhs_number, gb_utr, us_phonenumber, in_phonenumber, mx_phonenumber, fr_phonenumber, kr_landline(`02`), it 휴대전화 10자리, th·vn 휴대전화, br 유선(조건부), th_bank_account(숫자만, 조건부), vn_social_insurance(조건부), vn_tax_code(미채택) | 검증기가 있는 것(NHS 1/11, UTR 1/11)과 접두가 고정된 전화번호는 바로 등록, 나머지는 점수 체계 후. 전화번호끼리는 접두(`0[6-9]`, `[6-9]`, `0[35789]` …)로 부분 구분 |
| 숫자 11자리 | br_cpf, br_cnh, br_pis, de_tax_id, mx_nss, pl_pesel, kr_phonenumber(`010`), gb·br 휴대전화, vn 유선(`02`), in 유선(조건부) | 브라질 세 항목은 각 검증기가 서로 걸러 주며 등록 순서는 CPF 우선. PESEL 은 날짜 범위 + 검증기, 전화번호는 접두로 구분 |
| 숫자 12자리 | in_aadhaar, vn_citizen_id, vn_driver_license(조건부), fr_id_card 구형(조건부), br_voter_id, es_social_security_number, de 휴대전화 | Aadhaar 는 Verhoeff, 베트남은 성 코드 표, 브라질 유권자증은 UF 구간 + 검증기, 스페인 NAF 는 mod 97 로 구분 |
| 숫자 13자리 | fr_tax_number, th_national_id, th_company_id(미채택) | 각 검증기(mod 511, mod 11)로 구분. 태국 국민 ID 와 법인 번호는 첫 자리(`0`)로 구분 |
| `[A-Z][0-9]{7}` | in_passport, vn_passport, us_alien_registration_number(`A`), th_passport(1자 시리즈), us_driver_license(CA 형식) | 등록 순서 결정 필요 |
| `[A-Z][0-9]{8}` | us_passport(기존), **kr_passport(기존, `[mMsSrRoOdD]`)**, mx_passport, in/vn 여권의 MRZ 꼬리 표기, us_alien 구형 8자리 | 기존 두 recognizer 가 이미 겹치고 있음. 나머지는 순서 결정 |
| `[A-Z]{2}[0-9]{7}` | it_passport, it_id_card(구형), pl_passport, th_passport(2자 시리즈), us_dea_number(첫 문자 집합 제한) | 등록 순서 결정 필요. DEA 는 `dea` 검증기로 구분 |
| `[A-Z]{3}[0-9]{6}` | es_passport, pl_id_card | `pl_id_card` 검증기가 있어 우선 |
| `[A-Z]{2}[0-9]{6}[A-Z]` | gb_national_insurance_number, us_driver_license(Idaho 형식) | 모든 NINO 가 미국 운전면허 패턴에도 매치된다. NINO 접두 규칙이 더 좁으므로 NINO 우선 |
| `[A-Z][0-9]{9}` | de_health_insurance_number, mx_passport 10자리 표기, de_id_card 10자리 표기 | `de_kvnr`·`mrz_731` 검증기로 구분 |
| 유선전화 `0` + 8-12자리 (가변) | de/it/gb/in 유선 | 모두 점수 체계 후 등록. br(DDD + 8, 선행 0 없음)·pl(9자리, 선행 0 없음)도 조건부이며 위 10·9자리 행에 속한다. vn/th 유선은 길이 고정이라 바로 등록 |
| `[A-Z]{2,3}[ -]?[0-9]{3,5}` | br 구형 번호판, mx 번호판, pl 번호판(공백 구분), `ISO-9001`·`PLN 12345` 류 규격·통화 표기 | 모두 점수 체계 후 등록 |

context_words 도 국가를 넘나든다. 이탈리아어의 `ssn`(Servizio Sanitario Nazionale)은 `us_social_security_number` 의 context 이고, `pan` 은 인도 세금 번호이자 영어 일반 단어이다. context_words 는 recognizer 별로 독립이라 교차 오염은 없지만, locale 분리 없이는 이런 단어가 다른 나라 recognizer 의 점수를 올린다.

## 5. 공통 후보 항목 (국가 접두 없이 등록)

| 항목 | 근거 | 결정 |
|---|---|---|
| `iban` | 7개국이 같은 검증기를 씀 | 공통 recognizer 로 등록. Aho-Corasick 에 국가 코드 7개(`DE`, `GB`, `FR`, `IT`, `ES`, `PL`, `BR`)를 anchor 로 등록하고 verifier 가 국가별 길이·영숫자 규칙과 mod 97 을 검사하는 구조를 권장. regex 로 하면 7개 패턴 |
| `vin` | ISO 3779 국제 표준, 체크 디지트는 북미만 의무 | en_US 문서에서 조건부. 다른 12개국 문서는 VIN 을 다루지 않았으므로 공통 항목으로 등록하되 검증기는 북미 규칙만 적용 |
| `mrz_731` 검증기 | 11개국 여권·신분증이 공유 | 검증기만 공통. recognizer 는 국가별 |
| 여권 MRZ 전체 (`P<XXX…`) | 모든 국가 | 이 문서 범위 밖. MRZ 두 줄 전체를 잡는 공통 recognizer 는 별도 검토 |

## 6. 구현 순서 제안

| 단계 | 내용 | 대상 |
|---|---|---|
| 0 | 점수 체계 도입(2절). `score` 필드, context 가산 0.5, 기존 테스트 3건 통과 확인 | 엔진 |
| 0' | locale 별 recognizer 집합 선택 기제(4절) | 엔진·YAML |
| 1 | 공통 검증기 `iban`, `mrz_731`, `verhoeff`, `nanp` (`luhn` 래퍼 `npi` 는 us_npi 가 미채택이므로 제외) | validator.rs |
| 2 | 검증기가 있는 채택 항목: us SSN(+`ssn`)·라우팅번호(+`aba_routing`)·DEA(+`dea`), kr 주민등록번호(`rrn` 강화), de 세금 ID·사회보험·건강보험, fr NIR·SPI·RIB, it CF·CIN, es DNI·NIE·NAF·CCC, pl PESEL·신분증, gb NHS·UTR, in Aadhaar·EPIC(`luhn`), br CPF·CNH·PIS·유권자증·CNS, mx CURP·RFC·NSS(`luhn`)·CLABE, th 국민 ID, vn 시민 신분번호(구조 검증) | validator + YAML |
| 3 | 형식이 엄격해 검증기 없이(또는 선택적 구조 검증만으로) 기본 점수로 등록 가능한 채택 항목: us ITIN·MBI·A-Number 그룹 표기, in PAN·운전면허·번호판(+`in_state_code`), gb NINO·DVLA 운전면허, it 건강 카드, mx 선거인 키, vn 건강보험, kr 유선전화, th 은행 계좌(구분자 표기), 신분증·여권(체크 디지트 표기 포함), 번호판 중 구조 강한 것(kr, fr SIV, it, es 신형, gb, br 메르코수르, vn 5자리), 휴대전화(kr 기존, us 개선 regex, de·gb·in·br·vn·th·es·fr·it·mx·pl), 공통 `iban` | YAML |
| 4 | 점수 체계 후 낮은 `score` 로 등록하는 항목("score 사용 필요" 28건 중 미채택 2건을 뺀 최대 26건): 유선전화 6개국, 숫자만 운전면허·신분증, 구형 번호판, gb/vn 9자리 여권·신분증 등. 기존 `us_passport` 는 신규 등록이 아니라 낮은 `score` 로 전환 | YAML |
| 5 | byte-scan detector 가 유리한 것: us 운전면허(주별 표), kr 계좌(은행별 표), de·pl 번호판(지역 코드 표), th 번호판(태국 문자·도 이름), 숫자열 공용 스캐너(SSN·ITIN·라우팅) | handwritten/ |
| 6 | 형식 명세 확인 후 결정: 운전면허(de, fr, it, pl, vn, th), 건강 카드(es CIP-SNS, in ABHA), 각종 "확인 필요" 항목(7절) | 조사 |

## 7. 확인 필요 항목 종합

각 국가 문서가 "확인 필요"로 남긴 것 중 구현에 직접 영향을 주는 것만 모았다. 전체 목록은 각 문서에 있다.

| 국가 | 항목 |
|---|---|
| en_US | ITIN 그룹번호 구간(IRS 최신 공고), 운전면허 주별 생년월일 인코딩 승수·오프셋, Wisconsin 체크 디지트 |
| ko_KR | 운전면허 지역 코드에 세종 포함 여부, 운전면허 끝 2자리 검증 알고리즘, 은행별 계좌 형식 출처, 법인등록번호 체크섬 |
| de_DE | 사회보험번호 예외 일자(`32`-`63`), 세금 ID 3회 반복의 연속 금지, PassG 조문, 운전면허 구조 전체 |
| fr_FR | NIR 첫 자리 `7`·`8`(NIA), 신형 CNIe 문자 집합, 운전면허 형식 |
| it_IT | Tessera Sanitaria 접두 5자리 고정 여부·체크 디지트, 운전면허 형식, 휴대전화 접두 목록 |
| es_ES | NAF 선행 0 처리 변형, CIF 유형별 체크 규칙, CIP-SNS 구조 |
| pl_PL | 신분증 체크 디지트 규칙, 여권 자체 체크 디지트, 운전면허 자리 순서 |
| en_GB | VAT 9755 변형 도입 시점, DVLA 체크 문자 집합 |
| en_IN | ABHA 형식·체크섬, EPIC 번호 공개 범위, 주 코드 표 최신 목록 |
| pt_BR | CNH 규칙(공식 명세 없음), CNS 규칙, RG 주별 규칙, CNPJ 영숫자 전환 IN 번호 |
| es_MX | 2025년 LFPDPPP 신법 조문 번호, 통신법 대체 여부, 번호판 주별 형식(`ABC-12-34` 포함), CURP 성별 `X` |
| vi_VN | BHYT 카드 번호 구조의 결정 번호(1351/QĐ-BHXH), 성 코드 `97`·`98`, 2025년 신형 운전면허 = 시민 신분번호 여부 |
| th_TH | 국민 ID 첫 자리 유형 코드 의미, 핑크 카드 `0` 시작과 법인 번호 충돌, 여권 시리즈, 운전면허 형식 |

## 8. context_words 작성 규칙 종합

각 국가 문서에서 반복된 규칙이다.

- context 검색은 소문자 부분 문자열 검색이다. 3글자 이하 단어(`tin`, `rib`, `nie`, `pix`, `dea`, `cie` …)는 다른 단어 안에서 걸리므로 ` nie ` 처럼 공백을 포함해 등록하거나 제외한다. 스페인어·포르투갈어·이탈리아어처럼 짧은 약어가 많은 언어에서 특히 주의한다.
- 부분 문자열이므로 `주민등록번호` 는 `주민등록` 에, `계좌번호` 는 `계좌` 에 이미 포함된다. 긴 형태를 추가해도 효과가 없다.
- 일반 단어(fr_FR 의 `numéro`, ko_KR 의 `연결`·`요청`·`지원`·`안내`)는 가산 근거로 약하므로 점수 체계 도입 시 정리한다.
- 현지어와 영어를 모두 넣는다. 성조·악상 문자가 있는 언어는 무표기 형태(`can cuoc`, `ho chieu`, `telefono`)도 함께 넣는다.
- 낮은 `score` recognizer 는 context_words 가 유일한 통과 수단이므로 목록을 충실히 채운다.
