# Prompt Injection 규칙 목록: {LOCALE} ({국가명} · {언어})

<!--
  이 파일은 locale 별 prompt injection 문서의 템플릿이다. 새 locale 문서를 만들 때 이 파일을 복사해
  docs/multilanguage_pi/YYYYMMDD-argo-pi-{LOCALE}.md 로 저장하고, {…} 자리를 채운 뒤 이 주석 블록과
  "작성 체크리스트" 절은 삭제한다. 완성된 예시는 docs/multilanguage_pi/20261015-argo-pi-ko_KR.md 이다.

  이미 정해진 원칙 (바꾸지 않는다):
  - 법령과 외부 위협 분류(OWASP, MITRE, NIST, CVE 등)는 쓰지 않는다. 근거는 규칙의 출처뿐이다.
  - 다루는 범위는 현재 내장 규칙 13개뿐이다. 2절 표는 정확히 13행이다.
  - 비영어 규칙은 출처가 없다 (ClawKeeper return_content_scan.py 는 영어 패턴만 가진다). 따라서 번역 규칙은
    모두 "출처 없음 → 신규 제안"이고, locale 선택 장치가 없으므로 상태는 "조건부"이다.
  - 영어 내장 규칙은 이 locale 에서도 그대로 동작한다. 번역 규칙은 영어 규칙을 대체하지 않고 추가된다.
  - 패턴 검증은 Python 이 아니라 rxprobe(엔진과 같은 regex 설정)로 한다.
  - 작성 기준·엔진 제약·layer·action·label 설명은 en_US 문서 0절을 참조하고 복사하지 않는다.

  제안 규칙 id 의 접두사는 locale 이 아니라 언어 코드이다 (ko_KR → `ko_`, de_DE → `de_`).
  같은 언어를 쓰는 locale 은 규칙을 공유한다. 엔진은 id 중복을 허용하지 않기 때문이다.
  - es_ES 와 es_MX: 먼저 쓰는 문서가 `es_` 규칙을 제안한다. 나중 문서는 같은 `es_` 규칙에 더할 지역 어휘와
    반례만 기록하고, 2절 표의 "처리" 열에 "es_ES 문서의 `es_…` 규칙을 공유, 추가 어휘: …" 라고 쓴다.
  - en_GB 와 en_IN: 영어 내장 규칙이 그대로 동작하므로 번역 규칙이 없다. 2절 표는 "같음" 또는
    "철자·관용 표현 차이 (예시)"로 채우고, 3절에는 영어 규칙이 놓치는 그 지역 영어 표현만 적는다.
    3·4절에 적을 것이 없으면 "해당 없음"이라고 쓴다. en_IN 에서 힌디어 등 현지 문자 문장을 다룰지는
    그 문서의 5절에서 결정 항목으로 올린다 (다룬다면 접두사는 `hi_` 처럼 그 언어 코드이다).
-->

이 문서는 ARGO 의 내장 prompt injection 규칙 13개를 {언어}로 옮길 때 무엇이 필요한지 기록한다. 작성 기준, 엔진 제약, layer·action·label 의 뜻은 `docs/multilanguage_pi/20261015-argo-pi-en_US.md` 0절을 따른다. 규칙별 상세 설명도 en_US 문서에 있다. 다만 en_US 0절과 달리, 이 문서는 패턴을 `␣` 로 줄여 싣고 Python 대신 rxprobe 로 검증한다.

- **기준 커밋**: ARGO `origin/main` `{커밋}` ({날짜})
- **검증 도구**: `docs/multilanguage_pi/rxprobe` (케이스 파일 `rxprobe/cases/{LOCALE}.txt`)

## 1. 요약

- **출처**: {언어} 패턴은 출처가 없다. ClawKeeper `return_content_scan.py` 와 argo-tizen baseline 에는 영어 패턴만 있다. 그래서 아래 제안 규칙은 모두 **신규 제안**이다.
- **상태**: 엔진에는 아직 locale 별로 규칙을 골라 싣는 장치가 없다(en_US 5.1절). 내장 규칙은 앞으로 locale 값에 따라 설정할 예정이므로, 한 사용자에게 실리는 규칙은 영어 규칙과 그 locale 언어의 규칙뿐이다. 제안 규칙은 그 장치가 생기기 전까지 **조건부**이다.
- **영어 규칙**: 영어 내장 규칙 13개는 {언어} 사용자에게도 그대로 동작한다. {언어} 사용자도 영어 jailbreak 문장을 그대로 붙여 넣으므로, 제안 규칙은 영어 규칙에 **추가**된다.
- **{언어}에서 주의할 엔진 제약**: {en_US 0절의 엔진 제약 중 이 언어에 해당하는 것만. 예: 비 ASCII 글자 옆의 `\b`, 비 ASCII 대소문자(`(?iu:…)` 또는 두 형태 나열), 띄어쓰기·어순·굴절, 문자당 바이트 수, 부정문, NFC/NFD}

## 2. 규칙별 처리

| en 규칙 | 분류 | 처리 | 제안 규칙 id | layers · action · label | 상태 |
|---|---|---|---|---|---|
| `ignore_prior` | 영어 구문 | {번역 제안 / 같음} | `{lang}_ignore_prior` | prompt_guard, tool_output · block · override | 조건부 |
| `ignore_previous_instructions` | 영어 구문 | {`{lang}_ignore_prior` 에 통합 등} | — | — | 기존 · 유지 |
| `act_as_override` | 영어 구문 | | | prompt_guard, tool_output · block · override | |
| `reveal_secrets` | 영어 구문 | | | prompt_guard, tool_output · block · override | |
| `reveal_system_prompt` | 영어 구문 | | | prompt_guard, tool_output · block · override | |
| `role_override` | 영어 구문 | | | prompt_guard, tool_output · block · override | |
| `invisible_payload` | 언어 무관 | 같음 {th_TH·en_IN 은 정상 텍스트의 ZWSP·ZWJ·ZWNJ 사용을 확인} | — | — | 기존 · 유지 |
| `trust_this_source` | 영어 구문 | | | tool_output · warn · override | |
| `imperative_credential_read` | 혼합 | {동사 부분만 번역} | | tool_output · block · embedded_directive | |
| `imperative_pipe_to_shell` | 언어 무관 | 같음 | — | — | 기존 · 유지 |
| `imperative_base64_run` | 혼합 | {같음 / 번역 제안, 이유} | | | |
| `comment_directive` | 혼합 | {지시 구문만 번역. 별도 규칙, 창 `[^>*]{0,800}` (ko_KR 5절 결정)} | | tool_output · block · comment_directive | |
| `base64_decoded_to_shell` | 언어 무관 | 같음 | — | — | 기존 · 유지 |

## 3. 제안 규칙

`␣` 는 en_US 문서와 같이 `(?:\s|\xC2\xA0|\xE3\x80\x80)` 한 개를 뜻한다. 코드 블록은 `␣` 로 줄여 쓴 형태이며, 원문 패턴은 rxprobe 케이스 파일에 있다. 표는 대표 사례만 싣는다. 케이스 파일에는 {N}건이 있고 모두 `rxprobe check` 를 통과한다. 비고에 **오탐**으로 적은 문장은 실제로 매칭되며, 감수하는 비용을 기록한 것이다.

### {lang}_{규칙}

- **노리는 동작**: {한 줄}
- **패턴**: {en 규칙과 다르게 만든 점이 있으면 한두 문장}

  ```
  {패턴}
  ```

  | 매칭 예시 | 거부 반례 | 비고 |
  |---|---|---|
  | {공격 문장} | {그 언어의 일상 문장} | {오탐이면 "**오탐**"이라고 쓰고 이유} |

## 4. 메모리

`rxprobe mem` 으로 잰 값이다. `total` 은 정방향·역방향 NFA 와 lazy DFA 최소 캐시의 합이며, 패턴 전체를 청크 하나로 컴파일한 값이다. 엔진은 실제로 최소 캐시의 3배(`CACHE_MARGIN_RATIO = 3.0`)를 할당하므로, 실행 중 메모리는 이 표보다 크다. 엔진은 턴마다 만들고 턴이 끝나면 버리므로, 이 값은 상주 메모리가 아니라 턴 동안의 사용량이다. en_US 문서의 `bench_prompt_guard_memory` 수치(약 22/47 KB)와는 측정 방법이 달라서 직접 비교할 수 없다. 규칙을 locale 값에 따라 싣는다는 전제이므로, 아래 값은 이 locale 사용자 한 명이 받는 규칙 기준이다. 기준 행 외의 값은 이 locale 의 패턴으로 다시 잰다.

| 집합 | 패턴 수 | total |
|---|---|---|
| en 사용자 입력 규칙 (기준) | 7 | 114 KB |
| en + {lang} 사용자 입력 규칙 | | |
| en 전체 regex 규칙 (기준) | 12 | 343 KB |
| en + {lang} 전체 regex 규칙 | | |

## 5. 결정 사항

ko_KR 5절의 결정(2026-10-15)을 따른다. 이 locale 에서 새로 생긴 결정만 아래 표에 적는다. 없으면 "ko_KR 5절과 같음"이라고 쓴다.

- 모든 번역 규칙의 layer 와 action 은 대응하는 en_US 규칙과 똑같이 둔다. 오탐이 확인되어도 지금은 감수하고 기록만 하며, 조정은 운영 데이터를 본 뒤에 한다.
- `comment_directive` 의 번역 구문은 별도 규칙으로 두고, 창은 `[^>*]{0,800}` 이다(주석 끝에서 멈춤).
- lookbehind 가 있어야 거를 수 있는 오탐(소유격이 앞에 오는 자기 요청 취소 등)은 감수하고, 케이스 파일과 문서에 오탐으로 기록한다.

| 항목 | 결정 | 이유 |
|---|---|---|
| {항목} | {결정} | {이유} |

## 작성 체크리스트 (완성 후 이 절은 삭제)

- [ ] 2절 표가 정확히 13행이고, 모든 행에 처리가 적혀 있다
- [ ] 법령·외부 위협 분류를 쓰지 않았다
- [ ] 제안 규칙의 패턴을 rxprobe 케이스 파일에 넣고 검사를 통과했다 (`cd rxprobe && cargo build --offline --release && ./target/release/rxprobe check cases/{LOCALE}.txt`)
- [ ] 문서 표의 예시·반례가 모두 케이스 파일에 같은 부호(`+`/`-`)로 들어 있다
- [ ] 거부 반례에 그 언어의 일상 문장(사용자 대화, README, 코드 주석, 공지·공공기관 페이지, TV 비서 사용)을 넣었다. 오탐으로 매칭되는 문장은 `+` 에 두고, 케이스 파일에는 바로 위에 `# FALSE POSITIVE` 주석을, 문서 비고에는 "**오탐**"을 적었다
- [ ] 짧은 대안이 더 긴 일상 단어 안에서 매칭되지 않는지 확인했다 (ko_KR 의 `위`↔`범위`, `너`↔`너무`, `읽`↔`읽기`)
- [ ] 부정문(`~하지 마세요` 에 해당하는 형태)이 매칭되지 않도록 동사를 명령·요청 형태까지 나열했다
- [ ] 비 ASCII 글자 옆에 `\b` 를 쓰지 않았다. 비 ASCII 대소문자는 `(?iu:…)` 또는 두 형태 나열로 처리했고, `(?iu:…)` 는 rxprobe 로 매칭을 확인했다
- [ ] 악센트·성조 문자가 있는 언어는 NFC/NFD 두 형태의 차이를 1절에 적었다 (엔진은 정규화하지 않는다)
- [ ] 공백을 `\s` 대신 `␣` 형태로 썼다. 띄어쓰기가 일정하지 않은 언어는 `␣*` 를 썼다
- [ ] `prompt_guard` 에 둘 규칙은 패턴이 정확히 1개이다. `tool_output` 에서 동작하는 규칙에는 label 을 적었다
- [ ] 모든 번역 규칙의 layer·action 을 대응하는 en_US 규칙과 같게 두었다. 일상 문장에서 나온 오탐은 조정하지 않고 기록만 했다
- [ ] `rxprobe mem` 으로 4절 표를 채웠다
- [ ] 서브에이전트 리뷰를 받고 반영했다
