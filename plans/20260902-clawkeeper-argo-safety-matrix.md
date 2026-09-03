# ClawKeeper × ARGO Safety 기법 대조 분석

작성일 2026-09-02 · 코드 직접 확인 기반 · **rev.3** (서브에이전트 3인 리뷰 + 후속 코드 확인 반영)

---

## 0. 분석 방법

**원칙**: README·`docs/`·모듈 주석을 근거로 삼지 않고 구현 코드(함수 본문, 상수 테이블,
호출 지점)를 직접 읽어 판정했다. 주석을 인용한 경우 "주석 근거"임을 명시한다.

**조사 대상 커밋 (고정, 검증됨)**

| 저장소 | 경로 | 커밋 |
|---|---|---|
| ARGO | `~/Works/ARGO-ClawKeeper` (worktree, `dev/byungchul.so/clawkeeper`) | `2205b7c3ff` |
| ClawKeeper | `~/Works/ClawKeeper` (`SafeAI-Lab-X/ClawKeeper`) | `69db077` |
| hermes-agent | `~/Works/hermes-agent` (`NousResearch/hermes-agent`) | `180291162f` |
| argo-tizen | `~/Works/argo-tizen` (`dev/byungchul.so/guardrails-pii`) | `bd1adcb9` |

**검증 등급**: `[실행경로확인]` 호출 체인 끝까지 추적 · `[코드확인]` 구현만 읽음 ·
`[실측]` 실제 실행 · `[미검증]` 확인 못 함(추측으로 채우지 않음)

**용어**: ARGO 측 컴포넌트도 ClawKeeper처럼 **이름**으로 부른다. 파일 경로는 근거로만 병기한다.

| 이 문서의 이름 | 실제 위치 |
|---|---|
| `arg_shape` (G1) | `agent/guardrails_tool_input/mod.rs` |
| `command_safety` (G2) | `agent/guardrails_tool_input/command_safety.rs` |
| `secret_path` (G3) | `agent/guardrails_tool_input/secret_path.rs` |
| `path_boundary` (G4) | `agent/guardrails_tool_input/path_boundary.rs` |
| `path_validator` | `security/path_validator.rs` |
| `confine` | `security/confine.rs` |
| `ssrf` | `security/ssrf.rs` |
| `url_validator` | `security/url_validator.rs` |
| `network_policy` | `security/network_policy.rs` |
| `url_scan` | `agent/guardrails_exfil/url_scan.rs` |
| `secret_needles` | `agent/guardrails_exfil/secret_needles.rs` |
| `scrubber` | `tools/scrubber.rs` |
| `audit_text` | `dispatchable_policy/audit.rs` |
| `prompt_guard` | `agent/prompt_guard.rs` |
| `pii_filter` | `guardrails/` (엔진) + `PiiSpanDetector` |
| `sensitive_masking` | `agent/pii_masking.rs` (`EgressMask`) |
| `denied_pattern` | `agent/guardrails_builtin.rs` (`DeniedPatternGuardrail`) |
| `classifier` | `agent/guardrails_classifier.rs` |
| `untrusted_envelope` | `tools/tool_orchestrator/execution.rs` `post_execute` |

> **주의**: 같은 이름의 저장소가 둘 있다. `rad-security/clawkeeper`(Bash, OpenClaw 호스트
> 스캐너)는 hermes-agent와 무관하다. 이 문서는 `SafeAI-Lab-X/ClawKeeper`(Python)만 다룬다.

---

## 1. ClawKeeper가 hermes-agent에 적용하는 safety 기법

### 1.1 부착 지점 — 코드로 확인한 3개 훅

`clawkeeper_core/adapters/hermes.py`의 `install(judge, agent)`가 연결하는 지점. hermes-agent
HEAD(`180291162f`)에 해당 심볼이 실재하는지 전부 대조했다. **[실행경로확인]**

| # | ClawKeeper가 부르는 것 | hermes 실재 위치 | 차단력 |
|---|---|---|---|
| ①-a | `terminal_tool.set_approval_callback(approval_cb)` | `tools/terminal_tool.py:301` | **차단 가능** (hermes가 먼저 위험으로 flag한 명령만 도달) |
| ①-b | `computer_use.tool.set_approval_callback(approval_cb)` | `tools/computer_use/tool.py:69` | **⚠ 오작동 — 전부 거부** (§1.5(2)) |
| ② | `manager._hooks.setdefault("pre_tool_call", []).append(...)` | `hermes_cli/plugins.py:7030`, 훅 이름 `:164` | **차단 가능 (모든 툴 호출)** |
| ③ | `agent.tool_start_callback` / `tool_complete_callback` | `run_agent.py:467`, 인자 `:521-522` | **관찰 전용** (`hermes.py:379-381`) |

②의 차단 경로는 끝까지 추적했다: `_ensure_plugins_discovered()` → `get_plugin_manager()`가
`_delivery_manager()`가 dispatch하는 것과 동일 객체 → `invoke_hook`이 kwargs를 시그니처
필터링 → `_resolve_block_from_details`가 block 메시지 반환 → `model_tools.py:1451-1466`에서
`tool_error(...)`로 변환하고 **실행하지 않음**. `pre_tool_call`은
`_HOOK_TIMEOUT_FAIL_CLOSED_HOOKS`에도 포함(`plugins.py:443`).

### 1.2 설치되는 것: 가드 6종 + Judge

ClawKeeper의 방어 컴포넌트는 두 종류다.

- **가드 8종** — `clawkeeper_core/guards/` 아래. `run_guard_chain`을 타는 것들
- **`Judge`** — `clawkeeper_core/judge.py`. 가드 디렉터리 **밖**이고 체인을 타지 않는다.
  승인 콜백 안에서 `judge.evaluate(...)`로 직접 호출됨(`hermes.py:172`)

hermes에 설치되는 것은 **가드 8종 중 6종 + Judge = 7개**다. 아래 §1.3이 그 7개를 다룬다.
(`watcher_url`을 명시적으로 넘기면 Watcher가 8번째로 붙지만 기본은 아님)

```python
# clawkeeper_core/adapters/hermes.py:93-117
def _default_pre_guards():
    return [guard_execution, guard_before_tool_call, url_safety_guard, script_body_scan_guard]
def _default_post_guards():
    return [return_content_scan_guard, credential_redact_guard]
```

**미설치 2종** — `hermes.py:30-42`의 import 목록에 아예 없다. **[코드확인]**

| 가드 | 하는 일 | 왜 빠졌나 |
|---|---|---|
| `input_validator` | JSON Schema 부분집합 검증(`type`/`required`/`minLength`/`pattern` 등). 기본 스키마는 `bash`·`read_file`·`write_file` **3개뿐**(`:78`). `fail-open` + `unknownToolPolicy: "pass"`라 스키마 없는 툴은 통과 | 걸 자리(`pre_tool_call`)는 있는데 안 씀 |
| `budget` | LLM 토큰 롤링 윈도 추적(기본 input 1M / output 200K / total 1.2M, `warnRatio` 0.8). 상태를 `$OPENCLAW_WORKSPACE/clawkeeper/budget.json`에 영속 | 어댑터가 LLM 호출 지점에 아무것도 안 검. hermes에 `pre_llm_call`/`post_llm_call` 훅이 있는데 미사용 |

둘 다 **PI 탐지와 무관**하므로, 빠졌다고 PI 커버리지가 줄지는 않는다.
(`input_validator`는 PI 관련 참조 0건 — `pattern` 키워드는 `re.search` 불일치 시 거부하는
**allowlist** 문법이라 거부 패턴으로 쓸 수 없고, 기본 스키마에 `pattern`이 하나도 없다.)

### 1.3 기법별 상세

#### (a) `exec_gate` — 위험 명령 정규식 차단

`guards/exec_gate.py:97`. `DANGEROUS_COMMAND_PATTERNS` **49개**(실측)를 추출된 명령 문자열에
`search()`. 추출 규칙(`:80-94`)은 툴 이름이 `bash|shell|exec|command|terminal`에 매치하면
`command`/`cmd`/`script`/`input`/`code`/`bash`/`shell` **필드만** 이어붙인다. 룰 로드 실패 시
**fail-closed**(`:18`).

> **⚠ 실측된 오탐.** 인덱스 22가 `_r(r"ver(?:sion)?|systeminfo|whoami")`
> (`security_rules.py:156`) — 단어 경계가 없어 "ver"를 포함한 모든 문자열에 걸린다. **[실측]**
>
> ```
> cat server.log    -> MATCH ver(?:sion)?|systeminfo|whoami
> git log --oneline -> clean
> ls -la            -> clean
> ```
>
> 경로 ①은 hermes가 먼저 flag한 명령만 도달하므로 여기 안 오지만, **경로 ②는 모든 툴
> 호출에 실행**되므로 결과적으로 하드 차단된다.

#### (b) `path_guard` — 보호 경로 차단

`guards/path_guard.py:19-27`. 기본 룰 7개: `~/.ssh/**`, `~/.aws/**`, `~/.gnupg/**`(CRITICAL),
`~/.env`, `/etc/passwd`(HIGH), `/etc/shadow`, `/etc/sudoers`(CRITICAL).
**`extract_paths_from_params`로 툴 종류와 무관하게** 파라미터에서 경로 후보를 뽑아 검사한다
— 이 범용성이 ARGO 대응물과의 핵심 차이다(§3). **fail-closed**(`:186-188`).

#### (c) `url_safety` — SSRF + 호모글리프

`guards/url_safety.py`. **[코드확인]**

- **SSRF**: `_BLOCKED_V4_NETS`(10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, 100.64/10, 0/8,
  224/4, 240/4, 255.255.255.255/32) + `_BLOCKED_V6_NETS`(::1, fc00::/7, fe80::/10, ::) +
  `_BLOCKED_HOSTNAMES`(`metadata.google.internal`, `metadata.goog`, `instance-data`).
  **리터럴 IP만 파싱 — DNS 해석 없음**(`:134-144`)
- **호모글리프**: `_HOMOGLYPH_MAP`(`:67-78`) — **키릴 21자 + 그리스 18자 = 39자**

#### (d) `script_body_scan` — 동적 경로 조립 탐지

`guards/script_body_scan.py:111`. 민감 디렉터리 마커 **19개 항목(중복 1, 고유 18)** 과
파일-오퍼레이션 마커 **25개**가 같은 `command` 안에서 **500자 이내**(`_PROXIMITY`)에 함께
나타나면 차단. `Path.home()/'.aws'/'credentials'` 같은 런타임 조립을 잡는다.

#### (e) `return_content_scan` — 툴 결과의 프롬프트 인젝션 스캔

탐지 함수 `scan_content`는 `:122`, 가드 진입점은 **`:181`**. **자체 패턴을 쓴다** —
`PROMPT_INJECTION_PATTERNS`(60개)는 이 가드가 아니라 `scanner.py` 로그 스캐너 전용임을
grep으로 확인. **[실행경로확인]**

| 범주 | 내용 |
|---|---|
| `override` (4패턴) | `ignore/disregard/forget/override + prior/previous…instructions`, `from now on you are`, `reveal your system prompt`, `maintainer-note`/`sanctioned` |
| `embedded_directive` (3패턴) | `run/execute/also cat` + 민감경로, `curl\|wget … \| bash`, `base64 -d … \| sh` |
| `comment_directive` (1패턴) | `<!--`/`/*`/`# maintainer-note` 안의 `also run/dump/cat` |
| `invisible_chars` (15 코드포인트) | ZWSP `U+200B`, ZWNJ, ZWJ, word joiner, BOM, bidi `U+202A-202E`, isolate `U+2066-2069`, soft hyphen |
| `base64_decoded_to_shell` | 24자 이상 base64를 **실제 디코드**해 `cat `, `/etc/`, `/.ssh/`, `AKIA`, `id_rsa` 등 확인 |

심각도(`:206-212`): `override`/`comment_directive`/`base64_decoded_to_shell`/
**`embedded_directive` 3패턴 전부**(민감경로 조건 없음) → `critical`. 비가시 문자 단독 → `medium`.

#### (f) `credential_redact` — 패턴 기반 시크릿 마스킹

9개 패턴(`github_pat`, `openai_key`, `aws_access_key_id`, `stripe_key`, `bearer_header`, `jwt`,
`ssh_private_key`, `generic_secret_kv`, `aws_secret_key`). `[REDACTED]` 치환.
**의도적으로 차단하지 않음**(`:147`).

#### (g) `Judge` — 트래젝토리/정책 게이트

`judge.py:125`. 콘텐츠 스캐너가 아니라 **대화 흐름 판정기**. 분기 6개:
`missing_input`→stop(`:139`) / 사용자 중단요청→stop / 상류 에러→stop /
툴 호출 수 초과→ask_user / 명령툴+확인정책→ask_user / 위험도 임계→stop.

```python
# judge.py:21-27
DEFAULT_POLICY = {
    "maxRiskBeforeStop": "critical",
    "requireUserConfirmationFor": ["exec", "bash", "shell", "network", "write"],
    "autoContinueAllowed": False,
    "maxToolStepsWithoutUserTurn": 3,
    "treatCommandExecutionAsHighRisk": True,
}
```

> **⚠ 기본값이 만드는 결과. [실행경로확인]** 어댑터가 `{"role":"tool","toolName":"bash"}`를
> 덧붙여 Judge에 넘기고(`hermes.py:168-179`), `_normalize_message`가 `toolName`을 보존하며
> 덧붙인 메시지가 마지막이라 `active_messages`에 항상 포함된다 → `has_command_tool = True`,
> `autoContinueAllowed = False` → 판정은 항상 `ask_user`. 매핑표가 `"ask_user" → "deny"`
> (`hermes.py:50-54`)이므로 **승인 콜백에 도달한 명령은 전부 거부**된다.

### 1.4 체인 실행 규칙

`adapters/base.py:70`. 가드 예외 → **fail-open**(`:80-90`). pre는 `stop_on_block=True`,
post는 `False`. `exec_gate`/`path_guard`만 *룰 로드 실패*에 한해 스스로 fail-closed.

### 1.5 ⚠ 이 통합의 실제 차단력 — 두 가지 문제

**(1) post 가드는 hermes에서 아무것도 막지 못한다. [실행경로확인]**

`on_tool_complete`는 `make_event(...)`로 **로컬 dict**를 만들어 체인에 넘긴다.
`credential_redact_guard`는 그 dict를 치환하지만 hermes가 LLM에 넘기는 실제 `result`와 무관하고,
`return_content_scan_guard`가 `block: True`를 반환해도 `_blocking`은 `hermes.py:401`에서
폐기되고 기록만 된다.

> **원인은 hermes의 한계가 아니라 어댑터 설계다.** hermes의 `VALID_HOOKS`(`plugins.py:164-`)에
> **`transform_tool_result`가 있다.** `model_tools.py:1604-1631`이 그 훅의 문자열 반환값으로
> `result`를 **교체**하며, 주석이 "before the result is appended back into conversation
> context"라고 명시한다 — ARGO의 TOOL-OUTPUT 체인과 같은 성격의 게이트다.
> ClawKeeper는 이 훅을 쓰지 않고 관찰 전용 콜백에 PI 스캐너를 붙였다.
> `transform_terminal_output`도 마찬가지로 미사용.

**(2) `computer_use` 승인 콜백은 규약 불일치로 모든 동작을 거부시킨다. [실행경로확인]**

```python
# hermes-agent/tools/computer_use/tool.py:619
verdict = cb(action, args, summary)          # 위치 인자 3개
# :620-622  except Exception: verdict = "deny"
# :638      return json.dumps({"error": "denied by user", ...})   # 미인식 verdict 폴백

# ClawKeeper/clawkeeper_core/adapters/hermes.py:151
def approval_cb(command: str, description: str = "") -> str:   # 위치 인자 최대 2개
```

① 3인자 호출 → `TypeError` → `except`에서 `"deny"` ② 설령 인자가 맞아도 ClawKeeper는
`"once"`를 반환하는데 hermes는 `"approve_once"`를 기대 → 미인식 폴백으로 거부.
⇒ **ClawKeeper 설치 시 `computer_use`(GUI 자동화) 동작이 전부 거부된다.**

### 1.6 사용자 입력 경로는 통째로 없다

`install()`이 등록하는 4개(`:187`, `:188`, `:308`, `:429-430`)는 **전부 툴 호출 경로**다.
어댑터 전체에 `user_message`/`on_message`/`user_input` 처리가 0건. Judge가 대화 이력을 보긴
하지만 사용자 메시지에 하는 일은 정규식 2개(`_USER_STOP_RE`, `_USER_CONTINUE_RE`, `judge.py:33-34`)
매칭 — **의도 판별이지 인젝션 탐지가 아니다.** hermes에 `pre_llm_call` 훅이 있으나 미사용.

---

## 2. ARGO safety 기능 인벤토리

### 2.1 값 탐지 → 마스킹 축

| 이름 | 위치 (LOC) | 하는 일 |
|---|---|---|
| `pii_filter` | `guardrails/{recognizer,detector,filter}.rs` + `handwritten/` (≈4.3k) | `regex-automata` lazy DFA + `aho-corasick`. **인식기 49종** — 카드·주민번호·여권·계좌·전화 + GitHub ×7, AWS ×2, Stripe ×2, Slack ×5, GCP/Google ×5, Square ×2, Facebook ×2 등 |
| `SensitiveDetector` 트레잇 | `tinicore-traits/src/sensitive.rs` | 워크스페이스 `impl` **30개 중 실제 탐지 구현은 `PiiSpanDetector` 하나**(`guardrails/detector.rs:475`). 29개는 테스트 더블이며 그중 `extractor/mock.rs:165`는 `cfg(test)` 게이트 없이 프로덕션에 포함 |
| `DetectorChain` | `sensitive/chain.rs` (792) | 마스킹은 `detect_all`, **차단은 `detect_any_of`**(`sensitive/guardrail.rs:143`). `detect_any`도 있으나 차단엔 미사용 |
| redaction vault | `sensitive/redaction.rs` (1846) | 마스킹↔복원 라운드트립 |
| `sensitive_masking` | `agent/pii_masking.rs` (3852) | LLM 송신 직전 마스킹 (`EgressMask`) |

### 2.2 콘텐츠 스캔 축

| 이름 | 위치 (LOC) | 하는 일 |
|---|---|---|
| `audit_text` | `dispatchable_policy/audit.rs:1016` (2313) | **룰 23개** / 6범주: PromptInjection 4, DataExfiltration 4, CredentialAccess 8, InvisiblePayload 2(태그 `U+E0001-E007F` **+ BiDi override**), Obfuscation 3, Privilege 2. `Severity` 5단계 |
| `prompt_guard` | `agent/prompt_guard.rs` (694) | **인바운드 사용자 메시지** PI 탐지. 호스트 공급 룰, `Warn`/`Block`/`Sanitize{replacement}` |
| `static_scan` | `security/static_scan.rs` (278) | 스킬 번들 소스 시그니처 스캔 (설치 시점) |
| `denied_pattern` | `agent/guardrails_builtin.rs` (667) | `RegexSet`. **4개 가드레일 트레잇 모두 구현**(`:124/134/144/198`) |
| `classifier` | `agent/guardrails_classifier.rs` (1086) | LLM 분류기를 TOOL-INPUT 가드레일로. `Accept`→pass / `AskUser*`→Escalate / `Block`→Block |

> **`audit_text`의 이력**: `97f73caa5c`(2026-06-01, sanghnkim-max, PR #1030)에서 파일·23룰·호출부
> 2곳이 한꺼번에 들어왔고, 이후 룰 테이블은 **한 번도 바뀌지 않았다**(`git log -S "const RULES"`
> 가 최초 커밋만 반환). 원 커밋 메시지가 "one pre-dispatch gate, one pre-registration audit"라고
> 스코프를 명시 — **설계상 등록 전 감사 전용**이며, 툴 결과에 안 도는 것은 버그가 아니라 범위 밖이다.

### 2.3 툴 호출 게이트 축

| 이름 | 위치 (LOC) | 하는 일 |
|---|---|---|
| `arg_shape` (G1) | `guardrails_tool_input/mod.rs` (2554) | 카탈로그 밖 툴명·필수 인자 누락 |
| `command_safety` (G2) | 〃 (1859) | **argv 파싱 화이트리스트**. `UNCONDITIONALLY_SAFE:56`, `FIND_UNSAFE:64`, `GIT_UNSAFE_GLOBAL:88`, `REJECTED_SHELL_CHARS:145`. Safe/Dangerous/**Unknown** 3상태 |
| `secret_path` (G3) | 〃 (573) | **모든 툴 인자**에서 민감 경로. `.ssh`(단 `known_hosts`, `known_hosts.old`, `config`, `authorized_keys` 예외), `.aws/credentials`, `.kube/config`, `.docker/config.json`, `.gnupg` |
| `path_boundary` (G4) | 〃 (407) | 쓰기 대상 허용 루트 이탈 |
| `path_validator` | `security/path_validator.rs` (1063) | 심볼릭 링크 해석 + **하드코딩 블록리스트**(`BLOCKED_SUBSTRINGS:43`): `/etc/shadow`, `/.ssh/`, `/.gnupg/`, `/.aws/credentials`, `/.netrc`, `/.docker/config.json`, `/.kube/config` 등. **예외 없음** |
| `confine` | `security/confine.rs` (667) | 앵커 이탈 경로 거부 |

### 2.4 네트워크 축

| 이름 | 위치 (LOC) | 하는 일 |
|---|---|---|
| `ssrf` | `security/ssrf.rs` (691) | `reject_ssrf_target`(`:48`) + `reject_ssrf_resolved`(`:188`, **`tokio::net::lookup_host`로 DNS 해석 후 재검사**). CGNAT·benchmark + **IPv4-mapped/compat IPv6 재분류**(`:134`) |
| `url_validator` | `security/url_validator.rs:65` (328) | `validate_outbound_url`. 모듈 주석: "LLM이 준 URL을 다루는 모든 빌트인은 이걸 통과해야 함" |
| `network_policy` | `security/network_policy.rs` (1089) | `validate_domain`(도메인 allowlist) + `is_private_or_local`(사설망 판정). **둘의 활성화 상태가 다르다**(§4) |
| `url_scan` | `guardrails_exfil/url_scan.rs` (1377) | `UrlContext::AutoFetched` 기반 **제로클릭 마크다운 이미지 유출** 탐지 |
| `secret_needles` | `guardrails_exfil/secret_needles.rs` (271) | env 시크릿 **값** 유출 경보 |

### 2.5 시크릿 관리 축

| 이름 | 위치 (LOC) | 하는 일 |
|---|---|---|
| `scrubber` | `tools/scrubber.rs` (956) | 툴 출력 3패스(`:42`→`:213`→`:417`): env 시크릿 **값** 치환 → base64 축약 → 크기 상한. `collect_env_secrets`(`:470`)는 `len>=8 && (KEY\|SECRET\|TOKEN\|PASSWORD)` |
| `output_scrubber` | `security/output_scrubber.rs` (279) | 심층 방어 스크럽 |
| `credential_proxy` | `security/credential_proxy.rs` (1000) | 실행 직전 시크릿 주입 **[코드확인]** |
| `secret_scope`/`tracker`/`ref`/`vault` | `security/` (합 1752) | 툴별 접근 범위, 접근 횟수 이상 탐지, 참조 전달, 파일 볼트 |

### 2.6 실행 격리 축

| 이름 | 위치 (LOC) | 하는 일 |
|---|---|---|
| `SkillSandbox` | `security/sandbox.rs` (1512) | 스킬 실행 통합 진입점 |
| `ExecSandbox` | `tinicore-traits/src/exec_sandbox.rs` | OS 격리 계약 |
| `integrity` | `security/integrity.rs` | 인증 스킬 SHA-256 변조 탐지 |
| `untrusted_envelope` | `execution.rs` `post_execute`(`:3539`), 판정 `:3568` | 미등록/외부 툴 결과를 "신뢰 불가"로 태깅. **fail-closed** — `tool_def.is_none_or(|d| d.trust_tier == TrustTier::Untrusted)` |

### 2.7 위 표에 없는 관련 모듈

`agent/guardrails.rs`(2077, **가드레일 셋 등록·조회 러너**), `session/db/security_flags.rs`(1223),
`agent/guardrail_scan_cache.rs`(684), `guardrails/hook.rs`(430, 레거시 미설치),
`tinicore-traits/src/audit.rs`(151), `security/audit_sink.rs`(147), `guardrails/validator.rs`(61,
Luhn·주민번호 체크섬), `types/security.rs`(39), `context_policy/`, `harness/guard.rs`,
`agent/policy.rs`, `protocols/governance/`. **[코드확인]**

---

## 3. 1:1 매칭표

등급: **완전대응** / **부분대응** / **ClawKeeper에만 있음** / **ARGO에만 있음**

| ClawKeeper 기법 | ARGO 대응물 | 등급 | 차이 |
|---|---|---|---|
| `exec_gate` | `command_safety` (G2) | **부분대응** | 패러다임 반대. ARGO는 argv 파싱 화이트리스트로 Safe/Dangerous/**Unknown** 3상태. 단 **`Unknown`의 처분은 `EscalateAction`에 달려 `Allow`에선 통과**(`command_safety.rs:72,663`). ClawKeeper는 블랙리스트 2상태 + `ver` 오탐 실측 |
| `path_guard` | `path_validator` + `secret_path` (G3) + `path_boundary` (G4) + `confine` | **부분대응** | **적용 대상이 다르다.** ClawKeeper는 툴 종류 무관하게 파라미터에서 경로를 추출. ARGO에서 그 역할은 `secret_path`인데 **기본 OFF**이고, 기본 ON인 `path_validator`는 **파일 계열 빌트인 12개가 자기 `path` 인자를 넘길 때만** 동작한다 — `bash`는 이 경로를 안 탄다(확인: `bash.rs`에 `validate_and_reauthorize` 0건). ⇒ **기본 상태에서 `bash("cat ~/.ssh/id_rsa")`를 보는 것이 없다** |
| `url_safety` (SSRF) | `ssrf` + `url_validator` | **완전대응** | ARGO 우위: **DNS 해석 후 재검사**, IPv4-mapped/compat IPv6 재분류, benchmark 대역 |
| `url_safety` (호모글리프) | 없음 | **ClawKeeper에만 있음** | 워크스페이스 전체에 도메인/URL 호모글리프·confusable·IDN·혼용스크립트 판정 없음. `skills/mod.rs:676`은 스킬 **이름**의 제로폭 문자 처리로 대상이 다름 |
| `script_body_scan` | 사실상 없음 | **ClawKeeper에만 있음** | 가장 가까운 `static_scan`은 시점(스킬 설치)·대상(소스 파일)이 다름. 런타임 툴 인자의 동적 경로 조립 근접도 판정 없음 |
| `return_content_scan` | `audit_text` (룰만) | **부분대응** | 범주가 거의 겹침. 단 `audit_text`는 **매니페스트 등록 시점 전용**(설계상), ClawKeeper는 hermes에서 로깅 전용 — **양쪽 다 실효 차단 없음** |
| `credential_redact` | `pii_filter` + `audit_text`(CredentialAccess) + `scrubber` + `secret_needles` | **부분대응** | ARGO가 대체로 넓으나 **3개 갭**: ① `jwt` 전무 ② `aws_secret_key`(40자 시크릿) — ARGO는 access key **ID**만 ③ `generic_secret_kv` — ARGO의 `password`/`password_strict`는 pass/PWD 계열만 앵커해 `token=`·`secret=`·`client_secret=` 미커버 |
| `input_validator` | `arg_shape` (G1) | **완전대응** | ClawKeeper는 hermes에 **설치조차 안 됨** |
| `budget` | 없음 | **ClawKeeper에만 있음** | hermes 미설치. Core는 `$OPENCLAW_WORKSPACE` 같은 경로 규약·env 직접 읽기가 레이어 규칙 위반이라 이식 불가. 애초에 보안 가드가 아니라 비용 통제 |
| `Judge` | `classifier` + 승인 흐름 | **부분대응** | Judge는 **규칙 기반**(툴 호출 수 임계, 명령툴 감지). ARGO는 LLM 분류기 + `Escalate`. **"턴 내 툴 호출 N회 초과" 같은 루프 임계 규칙은 ARGO에 없음** |
| Watcher (선택) | `classifier` | **부분대응** | 둘 다 LLM 판정. ARGO는 툴별 `ToolSignal` 필요, ClawKeeper는 별도 데몬 |
| — | `prompt_guard` | **ARGO에만 있음** | 사용자 메시지 PI 게이트. ClawKeeper는 사용자 입력 경로 자체가 없음(§1.6) |
| — | redaction vault | **ARGO에만 있음** | 마스킹→LLM→복원 라운드트립. ClawKeeper는 `[REDACTED]` 단방향 |
| — | 한국/미국 PII 인식기 | **ARGO에만 있음** | 주민번호·운전면허·여권·계좌 + Luhn/체크섬. ClawKeeper는 PII 패턴 전무(시크릿만) |
| — | `untrusted_envelope` | **ARGO에만 있음** | 차단 대신 **태깅**. fail-closed |
| — | `url_scan` | **ARGO에만 있음** | 제로클릭 마크다운 이미지 유출 채널 |
| — | `CapabilityBroker`, 시크릿 스코프/추적/볼트, 실행 샌드박스, `integrity`, `network_policy` | **ARGO에만 있음** | |

---

## 4. ARGO 대응 기능의 활성화 상태

**(a) 코드 존재 / (b) 기본 빌드 컴파일 / (c) 런타임 실행** 3단계. 기준은
**env 없음 + 설정 파일 없음 + 기본 cargo feature**.

### 4.1 활성화 지점 — 어디서 켜지나

| 이름 | a | b | c | **활성화 지점 (조건)** | 최종 |
|---|---|---|---|---|---|
| `scrubber` | ✅ | ✅ | ✅ | `execution.rs:3866` `scrubber::finalize_result_safety` — `post_execute` 안에서 **감싸는 `if`·`#[cfg]` 없이** 호출. 모듈 선언 `tools/mod.rs:70`도 게이트 없음 | **ON** |
| `untrusted_envelope` | ✅ | ✅ | ✅ | `execution.rs:3568` — `post_execute`에서 항상. `tool_def` 없으면 Untrusted(fail-closed) | **ON** |
| `ssrf` | ✅ | ✅ | ✅ | `web_render.rs:192`(리터럴), `:217`(DNS 재검사) / `tinicli/src/adapters/web_render_ssrf.rs:34-36` / `tiniffi/src/http.rs:179` — 전부 무조건 | **ON** |
| `url_validator` | ✅ | ✅ | ✅ | `http.rs:261,1431,1601`(`http_fetch`/`http_post`), `brave_search.rs:421,1303`, `desktop_web.rs:835,1181`, `document_read.rs:242` | **ON** |
| `path_validator` | ✅ | ✅ | ✅ | 공용 헬퍼 `tools/builtins/mod.rs:225` `validate_and_reauthorize` → **빌트인 12개**(`file`, `file_open`, `glob`, `document_{read,edit,render,recalc,validate}`, `docx_edit`, `ocr`, `powershell`)가 진입 시 호출. 블록리스트는 하드코딩 상수 | **ON** (파일 툴 한정 — `bash` 미포함) |
| `network_policy` · `is_private_or_local` | ✅ | ✅ | ✅ | `url_validator.rs:87` | **ON** |
| `network_policy` · `validate_domain` | ✅ | ✅ | ❌ | `bash.rs:392`는 `execute_sandboxed` 안이고 `bash.rs:131`의 `if !use_system`에서만 도달. `use_system`은 `ctx.config.shell_mode` 유래이며 `config/core_config.rs:153-157`이 **`#[default] System`**("데스크톱/서버 기본") | **OFF** (데스크톱 기본) |
| `audit_text` | ✅ | ✅ | ⚠ | `tools/registry/store.rs:418`, `dispatchable_policy/discovery.rs:731` — **프로덕션 호출부는 이 둘뿐**. 툴 결과·LLM 출력엔 미적용 | **부분 ON** (등록 시점만) |
| `pii_filter` | ✅ | ❌ | — | **feature `guardrails`가 필요한데 어느 default에도 없음** — `tinicore/Cargo.toml:19`(`:22-27`에 "deliberately NOT in this list" 명시), `tinicli/Cargo.toml:27`, `argo-cli/Cargo.toml:34` | **OFF** (컴파일 제외) |
| `sensitive_masking` | ✅ | ✅ | ❌ | 설치는 `tinicli/src/cli_entry.rs:389` `install_pii(PiiMode::parse(cfg.pii_mode), …)` — **`#[cfg(feature="guardrails")]` 안**. 게다가 `pii_mode` 미설정 시 `Off`(`tinicli/src/guardrails/pii.rs:124` `Some("off") \| None => Self::Off`). `run_onboarding.rs`가 `pii_mode`를 쓰지 않으므로 기본 생성 설정에도 없음 | **OFF** (이중 게이트) |
| `arg_shape`·`command_safety`·`secret_path`·`path_boundary` (G1~G4) | ✅ | ✅ | ❌ | `agent/guardrails.rs:1066` — env **`ARGO_GUARDRAIL_TOOL_PACK`** 에 JSON이 있을 때만 `with_tool_input_pack` 호출. 레포에 이 env를 세팅하는 기본값 없음 | **OFF** |
| `url_scan`·`secret_needles` (exfil) | ✅ | ✅ | ❌ | `agent/guardrails.rs:1088` — env **`ARGO_GUARDRAIL_EXFIL`** JSON 필요 | **OFF** |
| `denied_pattern` | ✅ | ✅ | ❌ | `agent/guardrails.rs:1041-1055` — env **`ARGO_GUARDRAIL_DENY_{INPUT,OUTPUT,TOOL_INPUT,TOOL_OUTPUT}`** 필요. 빈 패턴이면 `DeniedPatternGuardrail::new`가 `Ok(None)` → 등록 안 함 | **OFF** |
| TOOL-OUTPUT 체인 | ✅ | ✅ | ❌ | 배선은 `execution.rs:3221` `run_tool_output_guardrails`에 존재하나 `if !set.tool_output.is_empty()` 조건. 위 세 팩이 모두 OFF라 비어 있음 | **OFF** |
| `prompt_guard` | ✅ | ✅ | ❌ | 호출은 `agent/loop_.rs:1895`(정의 `:674`), 스킵 조건 `:681` `ctx.config.prompt_guard.is_empty()`. **`CliConfig`에 `prompt_guard` 필드 자체가 없어 `config.toml`로도 도달 불가.** 워크스페이스 유일 설정자는 `tinicore/tests/prompt_guard_e2e.rs:221` | **OFF** |
| `classifier` | ✅ | ✅ | ❌ | 호스트가 툴별 `ToolSignal`을 공급해야 분류. 미공급 툴은 분류 안 함 | **OFF** |

### 4.2 가드레일 셋 설치 경로 (3개, 모두 호스트 공급 의존)

| 경로 | 위치 | 입력 |
|---|---|---|
| `install_guardrails_from_env("ARGO")` | `tinicli/src/cli_entry.rs:158` | env `ARGO_GUARDRAIL_*` |
| `install_guardrails_from_env(...)` | `argo-pc/rust-backend/src/bridge.rs:12094` | env |
| `install_guardrails(set)` 직접 | `tiniffi/src/lib.rs:28712` | 호스트 공급 **JSON** `guardrails.{denyInput,denyOutput,denyToolInput,denyToolOutput,toolPack,exfil}` (`:28555-28712`) |

**세 경로 모두 기본값을 공급하지 않는다.** `install_guardrails`는 `OnceLock`이라 **한 번만 성공**한다.

### 4.3 argo-tizen(`argot-daemon`)은 다르다

vendored `tini/tinicore`는 ARGO tinicore와 **바이트 단위로 동일**하다 — `src/**/*.rs` 1178개
`diff -rq` 0줄, `Cargo.toml`·`tests/`까지 일치. `project/scripts/sync-tini.sh`가 모듈을 통째로
복사하며 "`tini/`엔 argot 고유 파일이 없다"고 명시한다. **차이는 코드가 아니라 제품 배선이다.**

| 이름 | ARGO (`tinicli`/`argo-cli`) | argo-tizen (`argot-daemon`) |
|---|---|---|
| feature `guardrails`,`sensitive` | ❌ default에 없음 | ✅ `crates/argot-daemon/Cargo.toml:30`에 명시 |
| `pii_filter` + `sensitive_masking` | `pii_mode` 기본 `Off` → **OFF** | `[safety.pii] mode` — **`PiiMode::Full`이 `#[default]`**(`crates/argot-config/src/lib.rs:501-512`) → **ON** |
| `prompt_guard` | 설정 필드 자체가 없음 → **OFF** | `[safety.prompt_guard] mode` 존재(`argot-config/src/lib.rs:441`), 기본 `Off`. **베이스라인 룰 5개를 제품이 공급**: `agent_config.rs:87` `CORE_PROMPT_GUARD_BASELINE_RULES` 3개(`ignore_previous_instructions`, `reveal_system_prompt`, `role_override`) + `:102` `RAW_PROMPT_GUARD_RULES` 2개(`<argot-context>`/`<turn-context>` 신뢰태그 위조). **DB 영속화 전** 적용 |
| 설치되는 체인 | env 기반 | `crates/argot-daemon/src/guardrails/pii.rs:84` `GuardrailSet::new().with_input(chain)` — **input 체인만** |
| TOOL-OUTPUT 체인 | **OFF** | **OFF** (동일) — `with_tool_input_pack`/`with_exfil_pack`/`audit_text` 호출 없음 |

⇒ **`tinicore` 수정은 sync로 argo-tizen에 자동 전파되지만 배선은 전파되지 않는다.**
제품별 배선 커밋이 각각 필요하다.

### 4.4 요약

- **기본 ON**: `scrubber`, `untrusted_envelope`, `ssrf`, `url_validator`, `path_validator`(파일 툴 한정),
  `network_policy`의 사설IP 판정, `audit_text`(등록 시점 한정)
- **기본 OFF**: `pii_filter`·`sensitive_masking`(ARGO만 — tizen은 ON), G1~G4, exfil 팩,
  `denied_pattern`, TOOL-OUTPUT 체인 전체, `prompt_guard`, `classifier`,
  `network_policy`의 도메인 allowlist

Core 레이어 규칙상 Core는 제품 identity를 하드코딩할 수 없고 정책은 호스트가 공급해야 하므로,
"메커니즘은 다 있는데 기본값이 비어 아무것도 안 도는" 상태가 기본이 된다.

> **다만 "Core는 룰을 안 박는다"는 CLAUDE.md에 없다.** CLAUDE.md § Protecting the Core layer가
> 금지하는 것은 ① `argo-*` 의존 ② **하드코딩된 제품 identity**(브랜드/페르소나/`.argo/…` 경로/
> `argo:*` 스코프/제품 URL) ③ `if product == "argo"` 분기 — 세 가지다. "no rule"은
> `prompt_guard.rs:29`와 `guardrails_builtin.rs:4`가 **각자 좁혀 해석한 모듈 설계 결정**이고,
> `guardrails_tool_input/mod.rs:15`는 CLAUDE.md 그대로 "no tool name, no path, no host"라고만 쓴다.
> ⇒ `audit_text`의 `const RULES` 23개는 **CLAUDE.md 위반이 아니다**(제품 무관 범용 공격 패턴).

---

## 5. 결론 요약표

| ClawKeeper 모듈 | ARGO 대응 | 대응물 현재 상태 | **ARGO 도입 필요 여부** |
|---|---|---|---|
| `return_content_scan` | `audit_text` (룰 보유) | 등록 시점만 | **배선 필요 (1순위) · 룰 이식 불필요** — `audit_text`를 `ToolOutputGuardrail`로 감싸 `execution.rs:3221` 체인에 등록. 새 정규식 0개 |
| `script_body_scan` | 사실상 없음 | — | **신규 구현 (2순위)** — 동적 경로 조립은 `path_validator`의 리터럴 검증을 우회 |
| `url_safety` 호모글리프 | 없음 | — | **신규 구현 (3순위)** — `url_validator` 옆이 제자리 |
| `path_guard` | `path_validator`(ON, 파일 툴만) + `secret_path`(OFF) | 부분 ON | **이식 불필요 · G3 배선 필요** — 기본 상태에서 셸 경유 민감파일 접근을 보는 것이 없음 |
| `credential_redact` | `pii_filter` + `audit_text` + `scrubber` | `scrubber`만 ON | **인식기 2종 추가**(`jwt`, `aws_secret_key`) **+ `password` 계열 키 이름 확장**. 정규식은 `audit_text`에서 가져올 것 |
| `Judge`의 툴 루프 임계 | 없음 | — | **조건부 도입** — 다중 턴 drift 방어. ClawKeeper 기본값(`maxToolStepsWithoutUserTurn: 3`)은 실사용에 과도하게 낮음 |
| `exec_gate` | `command_safety` | OFF | **이식 불필요 · 배선 필요** — 이식하면 오히려 약해짐(`ver` 오탐). 켜더라도 `EscalateAction`을 `Allow`로 두면 `Unknown` 통과 |
| `url_safety` SSRF | `ssrf` + `url_validator` | **ON** | **불필요** — ARGO가 더 강함 |
| `input_validator` | `arg_shape` | OFF | **이식 불필요 · 배선 필요** |
| `budget` | 없음 | — | **불필요** — 보안 가드 아님 + Core 레이어 규칙 위반 |
| Watcher | `classifier` | OFF | **이식 불필요 · 배선 필요** |

### 5.1 가장 중요한 발견

**이식보다 배선이 우선이다.** ARGO는 ClawKeeper 방어의 대부분을 이미 코드로 갖고 있고 여러 곳에서
더 강하지만(argv 화이트리스트, DNS 해석 SSRF, 가역 마스킹, 인식기 49종) 상당수가 기본 OFF다.
ClawKeeper 쪽도 hermes에서 가장 가치 있는 두 가드가 로깅 전용이고(§1.5-1),
`computer_use`는 아예 오작동하며(§1.5-2), 사용자 입력 경로는 통째로 없다(§1.6).

실제 보안 효과 순서:

1. **`audit_text`를 TOOL-OUTPUT 체인에 등록** — 룰 0개 작성, 투입 대비 효과 최대.
   단 이는 원 설계 스코프(pre-registration audit)를 **의도적으로 넓히는 변경**이므로,
   매니페스트용 룰이 `git log` 출력·HTML·JSON을 만났을 때의 오탐 측정이 필수
2. **기본 정책 배포 결정** — 이 결정 없이는 3·4를 만들어도 기본값에서 안 돈다.
   argo-tizen이 `PiiMode::Full`로 선례를 만들었다
3. `script_body_scan` 신규 구현
4. 호모글리프 판정 신규 구현 + PII 인식기 2종 추가

---

## 부록 A. 검증 재현용 명령어

```bash
# 커밋 고정
for d in ARGO-ClawKeeper ClawKeeper hermes-agent argo-tizen; do
  printf "%-16s " "$d"; git -C ~/Works/$d log --oneline -1; done

# ClawKeeper가 설치하는 가드 (input_validator/budget 부재)
sed -n '/^def _default_pre_guards/,/^def install/p' ~/Works/ClawKeeper/clawkeeper_core/adapters/hermes.py
ls ~/Works/ClawKeeper/clawkeeper_core/guards/*.py     # 8개
ls ~/Works/ClawKeeper/clawkeeper_core/judge.py        # guards/ 밖

# exec_gate 오탐 실측
cd ~/Works/ClawKeeper && python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('sr','clawkeeper_core/security_rules.py')
sr = importlib.util.module_from_spec(spec); sys.modules['sr']=sr; spec.loader.exec_module(sr)
for cmd in ['cat server.log','git log --oneline','ls -la']:
    hits=[p.pattern for p in sr.DANGEROUS_COMMAND_PATTERNS if p.search(cmd)]
    print(f'{cmd:22} -> {hits[0][:40] if hits else \"clean\"}')"

# computer_use 규약 불일치 / 미사용 훅
sed -n '605,640p' ~/Works/hermes-agent/tools/computer_use/tool.py
sed -n '163,170p' ~/Works/hermes-agent/hermes_cli/plugins.py      # transform_tool_result
sed -n '1596,1635p' ~/Works/hermes-agent/model_tools.py           # 결과 교체

# ARGO 활성화 지점
cd ~/Works/ARGO-ClawKeeper
grep -n "finalize_result_safety" tinicore/src/tools/tool_orchestrator/execution.rs   # 3866
grep -n "run_tool_output_guardrails" tinicore/src/tools/tool_orchestrator/execution.rs # 3221
grep -rn "validate_and_reauthorize" tinicore/src/tools/builtins/*.rs | cut -d: -f1 | sort -u
grep -n "validate_and_reauthorize" tinicore/src/tools/builtins/bash.rs || echo "bash 미사용"
sed -n '150,160p' tinicore/src/config/core_config.rs              # ShellMode::System 기본
grep -n -A 10 '^default = \[' tinicore/Cargo.toml                 # guardrails 부재
grep -n "prompt_guard.is_empty" tinicore/src/agent/loop_.rs
grep -rn "audit_text(" tinicore/src --include="*.rs" | grep -v dispatchable_policy/audit.rs

# audit_text 이력
git log --diff-filter=A --format="%h %ad %an %s" --date=short -- tinicore/src/dispatchable_policy/audit.rs
git log --oneline -S "const RULES" -- tinicore/src/dispatchable_policy/audit.rs

# argo-tizen 대조
diff -rq ~/Works/ARGO-ClawKeeper/tinicore/src ~/Works/argo-tizen/tini/tinicore/src && echo "동일"
grep -n "guardrails" ~/Works/argo-tizen/crates/argot-daemon/Cargo.toml
sed -n '499,513p' ~/Works/argo-tizen/crates/argot-config/src/lib.rs   # PiiMode::Full 기본
sed -n '87,111p' ~/Works/argo-tizen/crates/argot-daemon/src/agent_config.rs  # PromptGuard 룰
```

## 부록 B. 개정 이력

### rev.2 — 서브에이전트 3인 코드 대조 리뷰

| 항목 | rev.1 | rev.2 | 근거 |
|---|---|---|---|
| 승인 콜백 thread-local 유실 | "차단 경로 사라짐" | **철회** | `thread_context.py:64`가 워커에 콜백 전파. `computer_use`는 모듈 전역 |
| `computer_use` 차단력 | "차단 가능" | **오작동 — 전부 거부** | `tool.py:619` 3인자 vs `approval_cb` 2인자 |
| `network_policy` | ON | **도메인 allowlist는 OFF** | `core_config.rs:153-157` `#[default] System` |
| `credential_redact` 갭 | `jwt` 1종 | **3종** | `aws_secret_key`, `generic_secret_kv` 추가 |
| 설치 경로 | 2곳 | **3곳** | `tiniffi/src/lib.rs:28712`는 호스트 JSON |

수치 정정: 호모글리프 그리스 16→18, `script_body_scan` 마커 18/24→19(고유18)/25,
가드 진입점 `:122`→`:181`, Judge 분기 5→6, PII 엔진 LOC 5.9k→≈4.3k, `secret_*` 1203→1752,
`SensitiveDetector` impl 10→30, `prompt_guard` 호출부 `:674`→`:1895`,
`InvisiblePayload`에 BiDi override 추가, 차단 경로는 `detect_any_of`.

**기각한 지적**: "`indirect prompt injection` 주석 부재" → `execution.rs:3209`에 하이픈
표기로 실재. 리뷰어가 띄어쓰기 형태로만 검색.

### rev.3 — 후속 코드 확인

| # | 변경 | 근거 |
|---|---|---|
| 1 | §3 ARGO 대응물을 **파일 경로 → 컴포넌트 이름**으로 (`command_safety`, `secret_path`, `path_validator`, `ssrf` 등). §0에 이름↔경로 대응표 신설 | 요청 반영 |
| 2 | §4에 **활성화 지점** 열 신설 — 각 기능이 어느 파일·어느 조건에서 켜지는지 명시 | 요청 반영 |
| 3 | §1.2 "가드 8개 중 6개"와 §1.3 7개 항목의 불일치 해소 — **Judge는 `guards/` 밖**임을 명시하고 "가드 6종 + Judge" 구성으로 서술. 미설치 2종의 내용도 추가 | `ls clawkeeper_core/guards/` = 8개, `judge.py`는 최상위 |
| 4 | `path_guard` 등급 **완전대응 → 부분대응** | `bash.rs`에 `validate_and_reauthorize` 0건 — 셸 경유 경로는 기본 상태에서 아무도 안 봄 |
| 5 | §1.5(1)에 **`transform_tool_result` 훅 존재** 추가 — hermes의 한계가 아니라 어댑터 미사용 | `plugins.py:167`, `model_tools.py:1604-1631` |
| 6 | §1.6 **사용자 입력 경로 부재** 신설 | `install()` 등록 4개 전부 툴 경로, Judge는 정규식 2개만 |
| 7 | §4.3 **argo-tizen 절** 신설 — vendored tinicore 바이트 동일, PII 기본 `Full`, PromptGuard 베이스라인 룰 5개 | `diff -rq` 0줄, `argot-config/src/lib.rs:501-512`, `agent_config.rs:87,102` |
| 8 | §4.4에 **"Core는 룰을 안 박는다"가 CLAUDE.md에 없음** 명시 | CLAUDE.md § Protecting the Core layer는 제품 identity만 금지. "no rule"은 모듈별 자체 해석 |
| 9 | §2.2에 `audit_text` **이력·설계 스코프** 추가 | `97f73caa5c`(2026-06-01), 룰 무변경, "one pre-registration audit" |
