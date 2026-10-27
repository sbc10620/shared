# Prompt Injection 다국어 문서 작성 지침

이 문서는 ARGO 내장 prompt injection 규칙을 locale 별로 기록하는 문서 시리즈의 공통 지침이다. 규칙을 평가하는 기준, 엔진과 설정의 동작, 문서 양식, 새 규칙을 제안하는 방법, 여러 locale 로 넓힐 때의 제약을 다룬다. 각 locale 문서는 이 내용을 복사하지 않고 참조한다.

- **기준 커밋**: ARGO `origin/main` `4000f90a6b` (2026-10-13). 로컬 checkout 은 이보다 오래된 detached HEAD 이므로 기준으로 쓰지 않았다.
- **대상 코드**:
  - 규칙 데이터: `tinicore/src/guardrails/prompt_injection/config/rules.yaml`
  - 규칙 해석·출처 설명: `tinicore/src/guardrails/prompt_injection/mod.rs`
  - 손으로 작성한 검출기: `tinicore/src/guardrails/prompt_injection/handwritten/base64_shell_detector.rs`
  - 사용자 입력 검사 엔진: `tinicore/src/agent/prompt_guard.rs`
  - ARGO 배선: `tinicli/src/guardrails/prompt_guard.rs`, `tinicli/src/guardrails/prompt_injection.rs`

## 1. 문서 구성

| 문서 | 내용 |
|---|---|
| `20261015-argo-pi-guide.md` (이 문서) | 공통 지침 |
| `20261015-argo-pi-common.md` | 언어와 무관하거나 번역할 필요가 없는 내장 규칙 4개 |
| `20261015-argo-pi-en_US.md` | 영어 문장에 의존하는 내장 규칙 9개 |
| `YYYYMMDD-argo-pi-{LOCALE}.md` | 영어 규칙 9개를 그 언어로 옮긴 제안 규칙. 첫 예시는 `20261015-argo-pi-ko_KR.md`. 영어권 locale(en_GB, en_IN)은 번역 규칙 없이 지역 표현만 기록한다 |
| `_template-argo-pi-locale.md` | locale 문서 템플릿 |
| `rxprobe/` | 패턴을 엔진과 같은 설정으로 검사하고 메모리를 재는 도구. 케이스 파일은 `rxprobe/cases/` |

## 2. 평가 기준

각 규칙은 다음 네 가지 기준으로 평가한다.

1. 출처가 있는 규칙인가? 현재 내장 규칙은 모두 ClawKeeper 또는 argo-tizen baseline 에서 옮긴 것이다(en_US 1절). locale 문서에서는 그 언어의 패턴이 출처에 있는지, 없어서 새로 제안하는 규칙인지를 밝힌다.
2. 그 문장이 무엇을 시도하며, 모델이 그대로 따르면 어떤 피해가 생기는가?
3. 결정론적 방법(regex 또는 손으로 작성한 검출기)으로 검출할 수 있는가?
4. 일상 문장에서 측정한 오탐 결과가 있는가? 그 결과는 어떤 layer·action 선택으로 이어졌는가?

PII 문서와 달리 이 문서 시리즈는 법령을 기준으로 쓰지 않는다. prompt injection 을 직접 다루는 법령이 없기 때문이다. 외부 위협 분류(OWASP, MITRE, NIST, CVE 등)도 근거로 쓰지 않는다. 규칙의 근거는 출처(1번 기준)뿐이다. PII 문서의 점수 체계(score), context_words, 체크섬 검증기도 이 규칙 집합에서는 쓰지 않는다. 대신 4번 기준이 그 역할을 맡는다.

## 3. 검사 지점 (layers)

규칙 파일 하나를 두 소비자가 읽는다. 둘을 나누는 기준은 **검사하는 텍스트를 누가 썼는가**이다.

| layer | 검사 대상 | 작성자 | 규칙을 두는 기준 | tinicore 진입점 | ARGO 설정 키 |
|---|---|---|---|---|---|
| `prompt_guard` | 사용자가 보낸 메시지 (첫 LLM 호출 전) | 사용자 | **누가 말하든** injection 인 문장만 둔다 (jailbreak, system prompt 유출 요구) | `CoreConfig.prompt_guard` ← `builtin_user_input_prompt_injection_rules()` | `[prompt_guard] mode` |
| `tool_output` | 도구가 돌려준 결과 (모델이 읽기 전) | 제3자 콘텐츠 (웹 페이지, 파일, API 응답) | 에이전트에게 **무언가를 시키는** 문장도 둔다. 사용자가 같은 말을 쓰면 정상 요청이므로 이런 규칙은 `tool_output` 전용이다 | `GuardrailsConfig.prompt_injection.tool_output` → `install_guardrails_from_config` | `[tool_output_guard] mode`, `labels` |

- 현재 내장 규칙은 13개이다. `prompt_guard` 에서는 7개(Block 6, Warn 1)가, `tool_output` 에서는 13개 전부가 동작한다. 개수는 `mod.rs` 테스트 `rule_file_is_a_valid_engine_config_with_the_documented_layer_split` 이, Block 6·Warn 1 의 구성과 순서는 `builtin_user_input_rules_are_the_prompt_guard_layer_six_block_one_warn` 이 고정한다.
- ARGO 에서는 두 layer 모두 기본값이 off 이다. `mode = "on"` 을 써야 켜지고, `off`·`on` 이외의 값은 부팅을 멈춘다. ARGO 의 `config.toml` 은 호스트 규칙을 추가하는 키를 제공하지 않으므로(`rules: Vec::new()`), ARGO 에서 동작하는 규칙은 내장 규칙뿐이다.
- 내장 규칙 집합은 `guardrails` feature 빌드에만 포함된다. 사용자 입력 검사 엔진(`agent::prompt_guard`) 자체는 모든 빌드에 컴파일된다. feature 가 없는 빌드에서 `[prompt_guard] mode = "on"` 을 쓰면 경고만 나오고 규칙 없이 동작한다.

## 4. 동작 (action) 과 평가 순서

| action | 사용자 입력 layer 에서의 동작 | 도구 결과 layer 에서의 동작 |
|---|---|---|
| `block` | 턴을 거부하고 메시지를 저장하지 않는다. 거부 문구는 경로마다 다르다. ARGO REPL·TUI 의 저장 전 검사(`gate()`)는 현지화한 `prompt-injection-blocked` 문구에 규칙 id 를 붙여 보여 준다. daemon(`/api/v1/chat`, `gateway/handler.rs`)과 `agent_loop` 안의 거부는 영어 고정 문구 `BLOCK_REFUSAL`("I can't help with that request.")을 돌려주고 규칙 id 를 싣지 않는다 | tripwire 를 발동해 도구 결과를 모델에 넘기지 않는다 |
| `warn` | 턴을 계속 진행하고, 경고 목록에 규칙 id 를 남긴다 | 로그만 남기고 결과를 통과시킨다 |
| `sanitize` | 매칭 구간을 `replacement` 로 바꾼다. 내장 규칙 중에는 이 동작을 쓰는 규칙이 없다 | 허용되지 않는다 (설치 시 거부) |

- 사용자 입력 layer 에서는 규칙 파일의 순서가 곧 평가 순서이다. 여러 규칙이 동시에 매칭되면 **파일 순서상 첫 번째 Block 규칙**이 거부 사유로 보고되고, `prompt_guard.match` 이벤트가 발생한다.
- 도구 결과 layer 에서는 매칭된 Block 규칙의 라벨 전체를 `sensitive.labels` 메타데이터로 보고한다. Warn 매칭은 `guardrails::audit` 로그 줄(규칙 id, 건수, 길이)로만 남는다.
- 두 layer 모두 로그와 이벤트에는 규칙 id 와 action(또는 라벨)만 남긴다. 매칭된 문장이나 메시지 본문은 기록하지 않는다.

## 5. 라벨 (label)

라벨은 `tool_output` layer 에서만 쓰인다. 도구 결과 layer 에서 매칭을 보고하는 분류이자, 운영자가 `[tool_output_guard] labels` 로 차단 대상을 좁힐 때 쓰는 단위이다. 라벨 5개는 `tinicore-traits/src/sensitive.rs` 의 `PromptInjectionLabel` 에 정의되어 있다.

| label | 뜻 | 해당 내장 규칙 |
|---|---|---|
| `override` | 모델의 기존 지시를 바꾸려는 문장 | `ignore_prior`, `ignore_previous_instructions`, `act_as_override`, `reveal_secrets`, `reveal_system_prompt`, `role_override`, `trust_this_source` |
| `embedded_directive` | 에이전트에게 명령 실행을 시키는 문장 | `imperative_credential_read`, `imperative_pipe_to_shell`, `imperative_base64_run` |
| `comment_directive` | HTML·`/*` 주석이나 `maintainer-note` 안에 숨긴 지시 | `comment_directive` |
| `invisible_chars` | 보이지 않는 문자(zero-width, bidi override, soft hyphen) | `invisible_payload` |
| `base64_decoded_to_shell` | 해독하면 셸 명령이 되는 base64 문자열 | `base64_decoded_to_shell` |

`labels` 에 Warn 규칙만 가진 라벨(`invisible_chars`, `base64_decoded_to_shell`)을 쓰면 경고와 함께 무시된다. 차단할 라벨이 하나도 남지 않으면 guardrail 은 비활성 상태가 되어 검사 자체를 하지 않는다.

## 6. 검출 방식

| 방식 | 구현 위치 | 동작 | 현재 사용하는 규칙 |
|---|---|---|---|
| **regex** | `guardrails::engine::PatternEngine` (PII 와 같은 엔진) | 패턴을 30개 단위 청크로 나눠 `regex_automata::hybrid::dfa`(lazy DFA)로 컴파일하고 청크마다 한 번 스캔한다. 엔진은 턴마다 만들고 턴이 끝나면 버린다 | 12개 |
| **handwritten** | `MatchEngine` 직접 구현, `EngineExtensions::handwritten` 으로 주입 | 코드로 후보를 찾고 검사한다 | `base64_decoded_to_shell` 1개 |

PII 쪽의 Aho-Corasick 검출기는 이 규칙 집합에서 쓰지 않는다.

## 7. 엔진 제약 (regex 작성 시 유의)

엔진은 ASCII 모드로 동작한다. 원본(ClawKeeper 의 Python `re`, 그리고 이전에 쓰던 `regex::Regex`)은 Unicode 모드이므로, 같은 패턴이라도 결과가 달라질 수 있다. 아래 목록의 출처는 `agent/prompt_guard.rs` 모듈 문서이다. 공백의 메모리 수치는 `rules.yaml` 머리말에서 가져왔고, 그 밖의 항목은 rxprobe 로 확인했다.

- `\s` 는 ASCII 공백만 뜻한다. 그래서 내장 규칙은 모든 `\s` 를 `(?:\s|\xC2\xA0|\xE3\x80\x80)` 로 넓혔다. 이 표현은 ASCII 공백에 U+00A0(no-break space)와 U+3000(CJK 입력기가 넣는 전각 공백)의 UTF-8 바이트를 더한 것이다. `(?u:\s)` 를 쓰면 모든 Unicode 공백을 받지만, 사용자 입력 엔진이 약 47 KB 커진다. 두 문자만 더하면 약 22 KB 이다(`bench_prompt_guard_memory`, 턴 안에서 측정). 따라서 U+2000–U+200A, U+202F 같은 다른 Unicode 공백은 여전히 문장을 끊는다.
- 패턴 전체에 `(?u)` 를 붙이면 `\b` 때문에 빌드되지 않는다. 비 ASCII 대소문자나 문자 클래스가 필요하면 부분 플래그 `(?u:…)`·`(?iu:…)` 를 쓴다. 이 부분 플래그는 ASCII `\b` 와 섞어도 빌드되고, `(?iu:игнор)` 가 `ИГНОР` 를, `(?iu:é)` 가 `É` 를 받는 것을 rxprobe 로 확인했다.
- `(?i)` 는 ASCII 글자만 대소문자를 무시한다. `(?i)ИГНОР` 는 `игнор` 를 놓치고, `ſ` 는 `s` 로 접히지 않는다.
- `.` 은 한 글자가 아니라 한 바이트이다. `a.{0,3}b` 는 `a가b`(한글 1자 = 3바이트)는 받고 `a가나다b` 는 놓친다.
- `\b` 는 ASCII 경계이다. 한글(또는 다른 비 ASCII 글자)은 공백과 같이 "단어가 아닌 글자"로 취급된다. 그래서 `\bignore` 는 `제발ignore` 안에서 매칭되고, `\b무시` 는 ASCII 단어 글자(영문·숫자·`_`) 바로 뒤에서만 매칭된다. 공백 뒤나 텍스트 맨 앞의 `무시` 와는 **매칭되지 않는다.** 악센트 라틴 문자는 단어 안쪽에 경계를 만든다(`précédent` 안에서 `\bcédent` 가 매칭된다).
- 비 ASCII 리터럴(`이전\s*지시`)은 그대로 컴파일된다. 그러나 비 ASCII 문자 클래스(`[가-힣]`, `\p{Hangul}`)는 `(?u:…)` 로 감싸지 않으면 컴파일되지 않고, `(?u)\b` 는 아예 컴파일되지 않는다.
- 매칭은 시작 위치마다 **가장 긴** 매치이다. lazy 수량자 `.{0,800}?` 도 greedy 처럼 동작한다.
- 빈 문자열만 매칭할 수 있는 패턴(`^$`, `x*`)은 절대 발동하지 않는다.
- lookahead, lookbehind, 역참조는 쓸 수 없다. 앞에 오는 말로 매칭을 제외하는 조건(예: "앞에 `my`·`제` 가 없을 때만")은 표현할 수 없다.
- 엔진은 텍스트를 NFC 로 정규화하지 않는다. NFD 로 분해된 문자(자모로 쓴 한글, 결합 문자로 쓴 악센트)는 조합형 리터럴과 매칭되지 않는다.
- `{0,N}` 같은 반복 횟수 제한은 엔진 안에서 위치마다 상태 하나로 펼쳐진다. 그래서 메모리가 N 에 거의 비례한다(`.{0,800}` 창 하나가 규칙 단독 약 180 KB).

## 8. 언어 종속성 분류

이 문서 시리즈에서 locale 마다 달라지는 것은 **공격 문장의 언어**이다. 그래서 내장 규칙을 다음 세 가지로 분류한다.

| 분류 | 뜻 | 다루는 문서 |
|---|---|---|
| **영어 구문** | 패턴의 핵심이 영어 단어 배열이다 | en_US. 각 locale 문서는 같은 공격을 그 언어로 쓴 규칙을 제안한다 |
| **혼합** | 영어 동사·구문과 언어 무관 토큰(경로, 주석 기호)이 섞여 있다 | en_US. 각 locale 문서는 영어 부분만 번역한다. 단 `imperative_base64_run` 은 번역이 필요 없어서 common 이다 |
| **언어 무관** | 유니코드 코드 포인트, 셸 문법, base64 처럼 언어와 무관하다 | common |

번역할 때 참고할 점은 다음과 같다.

- 어순이 다른 언어(한국어 등)는 대상어가 동사보다 먼저 온다(`이전 지시를 무시해`). 소유격(`my`·`제`)이 패턴 바깥 앞쪽에 오면 lookbehind 없이 거를 수 없다.
- `DAN` 같은 고유 명칭은 다른 언어 문장에서도 그대로 쓰인다. 현지어로는 "제한 없는 모드로 동작하라"에 해당하는 표현을 조사한다.
- `imperative_credential_read` 의 경로 목록과 `comment_directive` 의 주석 시작 기호는 번역하지 않고 영어 규칙과 같게 둔다. 동사·지시 구문만 번역한다.

common 은 문서상의 구분이다. `rules.yaml` 에는 이 구분이 없다. 규칙을 locale 값에 따라 싣게 되더라도, common 규칙과 영어 규칙은 모든 locale 에 실린다. 어느 나라 사용자든 영어 jailbreak 문장을 그대로 붙여 넣기 때문이다. locale 별로 달라지는 것은 각 locale 문서가 제안하는 번역 규칙뿐이다.

## 9. 문서 양식

common 을 제외한 모든 locale 문서(en_US 포함)는 같은 절 구성을 쓴다. 템플릿은 `_template-argo-pi-locale.md` 이다.

| 절 | 내용 |
|---|---|
| 머리말 | 기준 커밋, 검증 케이스 파일. 선택으로 관련 문서(같은 locale 의 PII 문서 등) |
| 1. 요약 | 출처, 상태, 다른 규칙(common·영어)과의 관계, 그 언어에서 주의할 엔진 제약 |
| 2. 규칙별 처리 | 영어 구문·혼합 규칙 9개의 표. common 규칙 4개는 넣지 않는다 |
| 3. 규칙별 패턴 | 규칙마다 노리는 동작, 패턴, 예시 표, 메모. 메모는 layer·action 의 이유나 검토한 대안처럼 적을 것이 있을 때만 쓴다 |
| 4. 메모리 | `rxprobe mem` 측정값. 측정 방법은 아래 "메모리 측정" |
| 5. 결정 사항 | 이 locale 에서 정한 것과 그 이유. 미채택 항목도 여기에 적는다 |
| 6. 알려진 빈틈 | 놓치는 형태와 감수한 오탐 중 따로 적어 둘 것. 표의 열은 항목·규칙·상태·근거이다 |

### 패턴과 예시 표의 표기

- 패턴은 `␣` 로 줄여 쓴다. `␣` 는 `(?:\s|\xC2\xA0|\xE3\x80\x80)` 한 개를 뜻한다. 원문 패턴은 en_US·common 규칙은 `rules.yaml`, 제안 규칙은 rxprobe 케이스 파일에 있다.
- 예시 텍스트 안의 특수 공백은 `␣` 로 쓰지 않고 `+ U+00A0 +` 처럼 코드 포인트로 쓴다.
- 표 안의 `|` 는 `\|` 로 이스케이프한다.
- 예시 표는 세 열이다.

  | 열 | 뜻 | 케이스 파일 표기 |
  |---|---|---|
  | 매칭 예시 | 규칙이 **잡아야 하는** 공격 문장 | `+` |
  | 거부 반례 | 규칙이 **잡으면 안 되는** 일상 문장. 여기서 "거부"는 패턴이 매칭을 거부한다는 뜻이다. guardrail 이 차단한다는 뜻이 아니며, 이 문장은 guardrail 을 통과해야 한다 | `-` |
  | 비고 | 판정 이유. 실제로 매칭되지만 감수하는 일상 문장은 매칭 예시 열에 두고 "**오탐**"이라고 쓴다 | 오탐은 `+` 로 두고 바로 위에 `# FALSE POSITIVE` 주석 |

- 예시 표는 대표 사례만 싣는다. 표의 모든 예시는 케이스 파일에 같은 부호로 들어 있어야 한다. handwritten 규칙(`base64_decoded_to_shell`)은 rxprobe 로 검사할 수 없으므로 예외이다.

### 메모리 측정

- `rxprobe mem <케이스 파일>…` 로 잰다. `total` 은 정방향·역방향 NFA 와 lazy DFA 최소 캐시의 합이며, 주어진 패턴 전체를 청크 하나로 컴파일한 값이다.
- 엔진은 실제로 최소 캐시의 3배(`CACHE_MARGIN_RATIO = 3.0`, `recognizer.rs`)를 할당하므로, 실행 중 메모리는 이 값보다 크다.
- 엔진은 턴마다 만들고 턴이 끝나면 버리므로, 이 값은 상주 메모리가 아니라 턴 동안의 사용량이다.
- 7절의 `bench_prompt_guard_memory` 수치(약 22/47 KB)와는 측정 방법이 달라서 직접 비교할 수 없다.
- 기준값은 `cases/common.*.txt` 와 `cases/en_US.*.txt` 를 함께 잰 값이다(en_US 4절). locale 문서는 여기에 그 locale 의 케이스 파일을 더해서 잰다.

### 검증

- 패턴은 `rxprobe` 로 검증한다. rxprobe 는 ARGO 와 같은 crate 버전(`regex-automata 0.4.14`, `regex-syntax 0.8.10`)과 같은 설정(`unicode(false)`, `utf8(false)`, `MatchKind::All`, 역방향 DFA 로 시작 위치 찾기, 시작 위치마다 가장 긴 매치, 빈 매치 버림)을 쓴다. tinicore 를 직접 돌리는 것은 아니다.
- 빌드와 실행: `cd rxprobe && cargo build --offline --release && ./target/release/rxprobe check cases/*.txt`.
- en_US 의 예시는 처음에 Python `re`(bytes 패턴)로 확인했고, 그 뒤 rxprobe 로 다시 확인해 같은 판정을 얻었다. 예시 중 저장소 테스트(`mod.rs` 의 `every_rule_matches_its_intended_attack` 등, `detector.rs` 의 `ordinary_tool_output_baseline`)가 실제 엔진으로 고정한 문장은 비고에 테스트 이름을 적는다.

## 10. 규칙 상태와 신규 규칙 제안 형식

규칙별 처리 표의 "상태" 열은 다음 값 중 하나를 쓴다.

- **기존 · 유지**: 이미 `rules.yaml` 에 있고 그대로 둔다.
- **신규 제안**: 그 언어의 공격 문장을 잡는 새 규칙이다. 일상 문장 반례로 오탐을 확인했다.
- **조건부**: 11절의 제약(locale 선택 장치 등)이 해결되어야 들일 수 있다.
- **미채택**: 결정 사항 절에 이유를 적는다.

번역 규칙은 출처가 없으므로 1절 요약에서는 "신규 제안"이라고 쓰고, 2절 표의 상태 열에는 들이는 조건을 나타내는 "조건부"를 쓴다.

신규 규칙을 제안할 때는 다음을 지킨다.

- id 접두사는 locale 이 아니라 **언어 코드**이다(`ko_ignore_prior`, `de_ignore_prior`). 대응하는 영어 규칙이 없으면 공격 형태를 영어 snake_case 로 쓴다.
- 같은 언어를 쓰는 locale 은 규칙을 공유한다. 엔진이 같은 id 를 두 번 받지 않기 때문이다.
  - es_ES 와 es_MX: 먼저 쓰는 문서가 `es_` 규칙을 제안한다. 나중 문서는 같은 규칙에 더할 지역 어휘와 반례만 기록하고, 2절 표의 "처리" 열에 "es_ES 문서의 `es_…` 규칙을 공유, 추가 어휘: …" 라고 쓴다. 지역 어휘는 공유 패턴에 직접 더하고, 먼저 쓴 문서의 코드 블록도 함께 갱신한다. 케이스는 공유 케이스 파일(`es_ES.txt`)에 `# es_MX` 블록으로 넣는다. 같은 패턴을 두 케이스 파일에 두면 어긋날 수 있기 때문이다. 나중 문서의 3절에는 패턴을 다시 싣지 않고, 더한 어휘의 예시 표만 싣는다.
  - en_GB 와 en_IN: 영어 내장 규칙이 그대로 동작하므로 번역 규칙이 없다. 2절 표는 "같음" 또는 "철자·관용 표현 차이 (예시)"로 채운다. 3절에는 그 지역 문장을 영어 규칙이 어떻게 판정하는지 보여 주는 예시(매칭·거부·오탐)를 싣는다. 영어 규칙이 놓치는 그 지역 표현은 케이스 파일에 넣지 않고 6절에 적는다. 3·4절에 적을 것이 없으면 "해당 없음"이라고 쓴다. en_IN 에서 힌디어 등 현지 문자 문장을 다룰지는 그 문서의 5절 결정 항목으로 올린다(다룬다면 접두사는 `hi_` 처럼 그 언어 코드이다).
- `rules.yaml` 과 `parse_rules` 가 요구하는 키를 모두 채운다. 모든 규칙에 `action` 이 필요하고, `tool_output` 에서 동작하는 규칙에는 `label` 도 필요하며, 매핑 키와 `entity_type` 은 같아야 한다. `prompt_guard` 규칙은 패턴이 정확히 1개여야 한다.
- **layer·action 은 대응하는 영어 규칙과 똑같이 둔다.** 그 언어의 일상 문장에서 오탐이 측정되어도 우선 기록만 하고, layer 를 `tool_output` 으로 좁히거나 action 을 `warn` 으로 낮추는 조정은 운영 데이터를 본 뒤에 한다(2026-10-15 결정, ko_KR 5절).
- `comment_directive` 의 번역 구문은 영어 규칙에 합치지 않고 별도 규칙으로 둔다. 주석 시작 기호와 창(`.{0,800}`)은 영어 규칙과 같게 둔다.
- lookbehind 가 있어야 거를 수 있는 오탐(소유격이 앞에 오는 자기 요청 취소 등)은 감수하고 오탐으로 기록한다.
- 짧은 대안이 더 긴 일상 단어 안에서 매칭되지 않는지, 부정문(`~하지 마세요` 에 해당하는 형태)이 매칭되지 않는지 반례로 확인한다.

## 11. 여러 locale 로 넓힐 때의 제약

| 제약 | 내용 | 영향을 받는 locale |
|---|---|---|
| **규칙 수 경계** | `mod.rs` "Growth boundary": 규칙 파일은 13개에 머물고 있으며, core 는 작고 구조적인 상수만 가진다. 그보다 크게 늘어나거나 위협 관찰에 따라 갱신해야 하면 데이터를 Product layer 로 옮기라는 신호로 본다. 여러 언어의 번역 규칙을 더하면 이 경계를 넘는다 | 전체 |
| **locale 선택 장치** | `RecognizerConfig` 에는 locale 필드가 없고, `prompt_injection` 모듈에도 locale 처리가 없다. 지금 구조에 번역 규칙을 더하면 모든 사용자에게 모든 언어의 규칙이 실린다. 내장 규칙은 앞으로 locale 값에 따라 골라 실을 예정이며, 그 장치가 생기기 전까지 번역 규칙은 조건부이다 | 전체 |
| **메모리** | locale 별로 골라 싣게 되면 한 사용자에게 실리는 규칙은 common + 영어 + 그 locale 언어의 규칙이다. regex 는 30개 단위 DFA 청크로 컴파일되므로, PII 쪽 "common + 국가 1개 = 30패턴(청크 1개) 이하" 예산과 같은 방식의 예산을 두는 것이 좋다. ko_KR 은 20패턴이고, 전체 regex 는 343 → 800 KB 이다(ko_KR 4절) | 전체 |
| **`(?i)` 는 ASCII 만 접는다** | `É`/`é`, `Ł`/`ł`, `Ü`/`ü` 를 같은 글자로 보지 않는다. `(?iu:…)` 를 쓰거나 대소문자 두 형태를 나열한다 | de_DE, fr_FR, es_ES, es_MX, it_IT, pl_PL, pt_BR, vi_VN |
| **`\b` 는 ASCII 경계** | 비 ASCII 글자로 시작하거나 끝나는 단어에는 `\b` 를 쓰지 않는다(7절) | ko_KR, th_TH, vi_VN, fr_FR, pl_PL, de_DE 등 비 ASCII 글자를 쓰는 모든 locale |
| **띄어쓰기** | 타이어는 단어 사이에 공백이 없으므로 `␣+` 로 단어를 이을 수 없다. 한국어도 조사가 붙어 띄어쓰기가 일정하지 않다 | th_TH, ko_KR |
| **`.` 은 1바이트** | 길이 창(`.{0,800}`)은 비 ASCII 텍스트에서 짧아진다(en_US 6절의 `comment_directive` 빈틈) | 비 ASCII 문자를 쓰는 모든 locale |
| **NFC/NFD** | 악센트·성조 문자가 분해형으로 오면 조합형 리터럴과 매칭되지 않는다 | vi_VN, 악센트 라틴 문자 locale, ko_KR |
| **영어 문장의 재사용** | 비영어권 사용자도 영어 jailbreak 문장을 그대로 붙여 넣는다. 번역 규칙은 영어 규칙을 **대체**하지 않고 **추가**한다 | 전체 |
| **우회 가능성** | regex 규칙은 바꿔 말하기, 글자 쪼개기, 다른 언어 섞기로 쉽게 우회된다. 손을 들이지 않은 복사·붙여넣기 공격을 거르는 얕은 그물이며 보안 경계가 아니다. 사용자 입력 검사에는 번역 규칙을 넣지 않고 도구 결과 검사에는 warn 으로 먼저 넣는 안이 검토되었고, 운영 데이터를 본 뒤의 후보로 남아 있다(2026-10-15) | 전체 |

## 12. 남은 일

| 작업 | 상태 |
|---|---|
| 나머지 locale 문서 작성 | 완료. ko_KR, de_DE, fr_FR, es_ES, es_MX, it_IT, pt_BR, pl_PL, vi_VN, th_TH, en_GB, en_IN |
| 규칙 수 경계와 locale 선택 장치의 설계. 번역 규칙을 core 에 둘지, Product layer(ARGO `config.toml` 의 호스트 규칙 키 등)로 옮길지 | 미결정 |
