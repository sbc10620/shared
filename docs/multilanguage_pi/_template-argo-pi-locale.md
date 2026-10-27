# Prompt Injection 규칙 목록: {LOCALE} ({국가명} · {언어})

<!--
  이 파일은 locale 별 prompt injection 문서의 템플릿이다. 새 locale 문서를 만들 때 이 파일을 복사해
  docs/multilanguage_pi/YYYYMMDD-argo-pi-{LOCALE}.md 로 저장하고, {…} 자리를 채운 뒤 이 주석 블록과
  "작성 체크리스트" 절은 삭제한다. 완성된 예시는 docs/multilanguage_pi/20261015-argo-pi-ko_KR.md 이다.
  언어와 무관한 common 규칙 4개는 docs/multilanguage_pi/20261015-argo-pi-common.md 가 다룬다.

  작성 기준, 문서 양식, 신규 규칙 제안 형식(id 접두사, 같은 언어를 쓰는 locale, en_GB·en_IN, layer·action)은
  docs/multilanguage_pi/20261015-argo-pi-guide.md 9·10절을 따른다. 특히 다음은 바꾸지 않는다.
  - 법령과 외부 위협 분류는 쓰지 않는다. 근거는 규칙의 출처뿐이다.
  - 2절 표는 common 규칙 4개를 뺀 9행이다.
  - 번역 규칙은 "출처 없음 → 신규 제안"이고, 상태는 "조건부"이다.
  - 번역 규칙의 layer·action 은 대응하는 en_US 규칙과 똑같이 둔다.
-->

이 문서는 ARGO 의 내장 prompt injection 규칙 중 영어 문장에 의존하는 9개를 {언어}로 옮긴 제안 규칙을 기록한다. 작성 기준, 엔진 제약, layer·action·label 의 뜻, 문서 양식은 `docs/multilanguage_pi/20261015-argo-pi-guide.md` 를 따른다. 영어 규칙의 상세는 `20261015-argo-pi-en_US.md` 에, 언어와 무관한 규칙 4개는 `20261015-argo-pi-common.md` 에 있다.

- **기준 커밋**: ARGO `origin/main` `{커밋}` ({날짜})
- **검증 케이스**: `docs/multilanguage_pi/rxprobe/cases/{LOCALE}.txt`

## 1. 요약

- **출처**: {언어} 패턴은 출처가 없다. ClawKeeper `return_content_scan.py` 와 argo-tizen baseline 에는 영어 패턴만 있다. 그래서 아래 제안 규칙은 모두 **신규 제안**이다.
- **상태**: 엔진에는 아직 locale 별로 규칙을 골라 싣는 장치가 없다(지침 11절). 내장 규칙은 앞으로 locale 값에 따라 골라 실을 예정이며, 그렇게 되면 한 사용자에게 실리는 규칙은 common·영어 규칙과 그 locale 언어의 규칙뿐이다. 제안 규칙은 그 장치가 생기기 전까지 **조건부**이다.
- **다른 규칙과의 관계**: common 규칙 4개와 영어 규칙 9개는 {언어} 사용자에게도 그대로 동작한다. {언어} 사용자도 영어 jailbreak 문장을 그대로 붙여 넣으므로, 제안 규칙은 영어 규칙에 **추가**된다.
- **{언어}에서 주의할 엔진 제약**: {지침 7·11절의 엔진 제약 중 이 언어에 해당하는 것만. 예: 비 ASCII 글자 옆의 `\b`, 비 ASCII 대소문자(`(?iu:…)` 또는 두 형태 나열), 띄어쓰기·어순·굴절, 문자당 바이트 수, 부정문, NFC/NFD, 악센트·부호를 뺀 입력(받는 방식과 받지 않는 형태, 그 이유)}

## 2. 규칙별 처리

| en 규칙 | 분류 | 처리 | 규칙 id | layers · action · label | 상태 |
|---|---|---|---|---|---|
| `ignore_prior` | 영어 구문 | {번역 제안 / 같음} | `{lang}_ignore_prior` | prompt_guard, tool_output · block · override | 조건부 |
| `ignore_previous_instructions` | 영어 구문 | {`{lang}_ignore_prior` 에 통합 등} | — | — | 기존 · 유지 |
| `act_as_override` | 영어 구문 | | | prompt_guard, tool_output · block · override | |
| `reveal_secrets` | 영어 구문 | | | prompt_guard, tool_output · block · override | |
| `reveal_system_prompt` | 영어 구문 | | | prompt_guard, tool_output · block · override | |
| `role_override` | 영어 구문 | | | prompt_guard, tool_output · block · override | |
| `trust_this_source` | 영어 구문 | | | tool_output · warn · override | |
| `imperative_credential_read` | 혼합 | {동사 부분만 번역} | | tool_output · block · embedded_directive | |
| `comment_directive` | 혼합 | {지시 구문만 번역. 별도 규칙, 창 `.{0,800}` 은 영어 규칙과 같음} | | tool_output · block · comment_directive | |

common 규칙 4개(`invisible_payload`, `imperative_pipe_to_shell`, `imperative_base64_run`, `base64_decoded_to_shell`)는 이 표에 넣지 않는다. 언어와 무관하거나 번역할 필요가 없어서 `docs/multilanguage_pi/20261015-argo-pi-common.md` 가 다루고, 이 locale 에서도 그대로 동작한다. {th_TH·en_IN 은 common 문서 2절의 확인 항목을 이 문서 1절에 기록한다.}

## 3. 규칙별 패턴

`␣` 는 지침 9절과 같이 `(?:\s|\xC2\xA0|\xE3\x80\x80)` 한 개를 뜻한다. 코드 블록은 `␣` 로 줄여 쓴 형태이며, 원문 패턴은 rxprobe 케이스 파일에 있다. {선택: 악센트 클래스 표기(`[éèêe]` 처럼 악센트 없는 글자를 함께 받는 클래스)나 추가 표기(th_TH 의 `‿`)를 쓰면 여기서 한 문장으로 알린다.} 표는 대표 사례만 싣는다. 케이스 파일에는 {N}건이 있고 모두 `rxprobe check` 를 통과한다. 비고에 **오탐**으로 적은 문장은 실제로 매칭되며, 감수하는 비용을 기록한 것이다.

### {lang}_{규칙}

- **노리는 동작**: {한 줄}
- **패턴**: {en 규칙과 다르게 만든 점이 있으면 한두 문장}

  ```
  {패턴}
  ```

  | 매칭 예시 | 거부 반례 | 비고 |
  |---|---|---|
  | {공격 문장} | {그 언어의 일상 문장} | {오탐이면 "**오탐**"이라고 쓰고 이유} |

- **메모**: {layer·action 의 이유, 검토한 대안 등. 적을 것이 없으면 이 항목을 뺀다}

## 4. 메모리

`rxprobe mem` 으로 잰 값이다. 측정 방법은 지침 9절 "메모리 측정"에 있다. 규칙을 locale 값에 따라 골라 싣는다는 전제이므로, 아래 값은 이 locale 사용자 한 명이 받는 규칙 기준이다.

| 집합 | 패턴 수 | total |
|---|---|---|
| common + en 사용자 입력 규칙 (기준) | 7 | 114 KB |
| common + en + {lang} 사용자 입력 규칙 | | |
| common + en 전체 regex 규칙 (기준) | 12 | 343 KB |
| common + en + {lang} 전체 regex 규칙 | | |
| (참고) common + en + {lang} 전체 regex 규칙, {언어} 주석 규칙 없음 | | |

## 5. 결정 사항

ko_KR 5절의 결정(2026-10-15)을 따른다. layer·action 은 en_US 규칙과 같고, 주석 구문은 영어 규칙과 같은 창을 쓰는 별도 규칙이며, lookbehind·lookahead 가 필요한 오탐은 감수한다. 이 locale 에서 새로 정한 것은 다음과 같다.

| 항목 | 결정 | 이유 |
|---|---|---|
| {항목} | {결정} | {이유} |
| 악센트 없는 입력 | {악센트·부호 언어만. 부호를 뺀 형태를 받는 방식과 받지 않는 형태} | {입력 습관, 비용 KB, 겹치는 일상 단어} |
| 넣지 않은 어휘 | {넣지 않은 어휘 목록} | 일상 문장과 겹친다. 이유는 3절 각 규칙과 6절에 있다 |

## 6. 알려진 빈틈

| 항목 | 규칙 | 상태 | 근거 |
|---|---|---|---|
| {놓치는 형태, 감수한 오탐 중 따로 적어 둘 것. 케이스 파일의 `# KNOWN GAP:` 줄은 모두 여기에 적는다} | {규칙} | {알려짐 / 감수, 이유} | {3절 표, 케이스 파일 KNOWN GAP, 지침 n절 등} |
| 800바이트 창이 비 ASCII 텍스트에서 짧아짐. {언어}는 {문자당 바이트}. {케이스 파일 공격 주석, 표본 공격 문단 중 잰 것}에서 바이트 수가 글자 수의 약 {n}배였다(창은 약 {n}글자) | `{lang}_comment_directive` | 알려짐. 영어 규칙과 같은 빈틈이다 | en_US 6절 |

## 작성 체크리스트 (완성 후 이 절은 삭제)

- [ ] 2절 표가 common 규칙 4개를 뺀 정확히 9행이고, 모든 행에 처리가 적혀 있다
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
- [ ] `rxprobe mem` 으로 4절 표를 채웠다. 사용자 입력 행은 prompt_guard 규칙 5개의 `P` 줄만 더했다(지침 9절)
- [ ] 규칙이 놓치는 공격은 케이스 파일에 `# KNOWN GAP:` 주석 아래 `-` 줄로 넣고, 6절에 같은 항목으로 적었다
- [ ] 6절의 800바이트 창 행에 잰 바이트/글자 비율을 적었다(케이스 파일 공격 주석, 표본 공격 문단 중 잰 것). 규칙을 공유하는 문서는 규칙을 가진 문서의 행을 가리킨다
- [ ] 일상 문장과 겹쳐서 넣지 않은 어휘를 5절 "넣지 않은 어휘" 행에 모았다
- [ ] 악센트·부호 언어는 부호를 뺀 입력을 받는지 확인하고, 받지 않는 형태와 이유를 1·5절에 적었다
- [ ] 서브에이전트 리뷰를 받고 반영했다
