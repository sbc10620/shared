# 백그라운드 LLM 호출 경로 PII 마스킹 통합

## 목적

메인 턴 이외의 모든 백그라운드 LLM 호출(memory 추출, compaction, dispatcher 등)이
클라우드로 PII를 마스킹 없이 전송하는 문제를 해결한다. 메인 턴의 기존 마스킹
동작(`agent_loop` 소유의 `TurnMaskingState` 기반)은 변경하지 않는다.

## 배경: 현재 마스킹 적용 범위

```
메인 턴 (마스킹 O):
  agent_loop → FallbackChain → call_llm_streaming_with_extra_headers (pub(crate))
  agent_loop이 TurnMaskingState(vault, demask scope, tool_args)를 루프 전체에 걸쳐 관리

백그라운드 (마스킹 X):
  call_provider (pub) → send_and_parse → HTTP
  call_llm (pub) → call_llm_with_extra_headers (pub(crate)) → HTTP
  call_llm_streaming (pub) → call_llm_streaming_with_extra_headers (pub(crate)) → HTTP
  dispatcher dispatch() → call_llm_with_extra_headers (pub(crate)) → HTTP
  compaction (context_helpers.rs) → call_llm_with_extra_headers (pub(crate)) → HTTP
```

메인 턴은 `pub` 함수 3개를 거치지 않고 `pub(crate)` 함수로 직행한다.
반면 백그라운드는 `pub` 및 `pub(crate)` 함수 모두를 사용한다.

## 성공 기준

### 1. task-local `MAIN_TURN_MASKING` 정의

`tini/tinicore/src/agent/pii_masking.rs`에 새 task-local을 정의한다.

```rust
tokio::task_local! {
    /// 메인 턴(agent_loop) 내부에서 실행 중임을 표시.
    /// true이면 LLM call 함수들이 마스킹을 스킵한다 (agent_loop가 별도 처리).
    static MAIN_TURN_MASKING: bool;
}
```

- `MAIN_TURN_MASKING.scope(true, fut)`로 감싼 future 내부에서만 `true`를 반환.
- 범위 밖(백그라운드, 외부 직접 호출)에서는 `try_with`가 `Err` → `false`로 간주.
- `wire_capture::scope`와 동일한 인라인 실행 제약: `tokio::spawn`으로 전파되지 않음.
- static 가시성은 `pub(crate)`로 제한 (외부에서 `true`로 설정하여 마스킹 우회 방지).

**증거**: task-local이 설정된 컨텍스트에서 `true`, 설정되지 않은 컨텍스트에서 `false`를 반환하는 단위 테스트.

### 2. agent_loop에 task-local 설정 (early return 이전)

`tini/tinicore/src/agent/loop_/llm_call.rs`의 `call_llm` 함수 **진입부** (라인 159 부근)에서
`MAIN_TURN_MASKING.scope(true, ...)`로 함수 전체를 감싼다.

**주의 — `wire_capture::scope` (라인 239)에 설정하면 안 됨**: `call_llm_via_dispatcher`가
라인 214에서 early return하므로, `wire_capture::scope` 이전에 분기하는 경로가
task-local 범위 밖이 된다. 따라서 `call_llm` 함수 진입부에서 설정해야 한다.

```rust
// llm_call.rs — call_llm 함수 진입부
pub(super) async fn call_llm(...) -> Result<CallLlmResponse, TinicoreError> {
    // task-local을 함수 진입부에서 설정 — early return (call_llm_via_dispatcher) 포함
    // 모든 메인 턴 경로(FallbackChain, dispatcher)를 커버
    crate::agent::pii_masking::MAIN_TURN_MASKING.scope(true, async {
        // ... 기존 call_llm 본문 전체 ...
        // (use_dispatcher_for_agent_chat 분기 포함)
        // (wire_capture::scope 호출 포함)
    }).await
}
```

- 메인 턴의 모든 경로(FallbackChain, `call_llm_via_dispatcher` → `dispatch_stream`)가
  task-local 범위 안에 들어감.
- 메인 턴의 기존 마스킹 로직(`mask_messages_for_cloud`, `mask_llm_output`, `demask`)은 변경 없음.

**증거**: 기존 메인 턴 마스킹 테스트가 전부 통과해야 함 (회귀 없음).
`use_dispatcher_for_agent_chat` 켜진 환경에서도 task-local이 `true`인지 확인하는 테스트.

### 3. LLM call 함수 3개에 마스킹 적용

다음 3개 함수의 **HTTP 송출 직전**에 마스킹을 적용한다:

| 함수 | 가시성 | 파일 |
|---|---|---|
| `call_provider` | `pub` | `llm/client.rs:458` |
| `call_llm_with_extra_headers` | `pub(crate)` | `llm/client.rs:810` |
| `call_llm_streaming_with_extra_headers` | `pub(crate)` | `llm/client.rs:2430` |

**`pub` wrapper 2개(`call_llm`, `call_llm_streaming`)는 마스킹을 적용하지 않는다.**
이 두 함수는 각각 `call_llm_with_extra_headers`, `call_llm_streaming_with_extra_headers`를
호출하는 얇은 wrapper이므로, wrapper와 내부 함수 양쪽에 마스킹을 적용하면
이중 마스킹(vault 충돌)이 발생한다. 내부 함수에서만 마스킹을 적용한다.

각 함수의 마스킹 로직 (공통):

```
1. global_sensitive_masking() 조회 → None이면 기존 동작 (byte-identical)
2. MAIN_TURN_MASKING 조회 → true면 기존 동작 (agent_loop가 처리)
3. 마스킹 적용:
   a. 로컬 PiiVault 생성
   b. 입력 messages 가역 마스킹 (vault에 원본↔플레이스홀더 매핑 저장)
   c. HTTP 전송 (마스킹된 messages)
   d. 응답에 대해 mask_llm_output (일방향 — 모델이 새로 생성한 PII)
   e. 응답에 대해 demask (가역 — vault에서 플레이스홀더 → 원본 복원)
   f. 마스킹된 응답 반환
```

**주의 — mask_llm_output → demask 순서**:
- mask_llm_output을 demask 전에 실행해야 함.
- mask_llm_output은 vault에 없는 새 PII만 플레이스홀더로 변환.
- vault에 있는 플레이스홀더는 이미 마스킹된 상태이므로 mask_llm_output이 변경하지 않음.
- demask는 vault의 매핑으로 플레이스홀더를 원본으로 복원.

**call_provider 특이사항 — `LlmMessage` 타입 마스킹**:
- `call_provider`는 `LlmChatRequest`(`Vec<LlmMessage>`)를 받음.
- 다른 2개 함수는 `&[ChatMessage]`를 받음.
- `LlmMessage`는 `LlmContent` enum을 가지며, variant는 `Text(Cow<str>)`, `ToolCall(ToolCallRequest)`, `ToolResult` 등.
- 기존 `mask_messages_for_cloud` / `mask_llm_output`은 `ChatMessage` 기반이며,
  `LlmMessage`용 마스킹 함수나 `From<LlmMessage> for ChatMessage` 변환이 코드베이스에 없음.
- **마스킹 대상**: `LlmContent::Text` variant의 text만 추출하여 마스킹하고,
  다른 variant (`ToolCall`, `ToolResult`)는 PII를 포함하지 않으므로 그대로 둔다.
- 마스킹된 text로 새 `LlmMessage`를 재구성하여 `LlmChatRequest`에 교체.

**call_llm_streaming_with_extra_headers 특이사항**:
- 스트리밍 응답은 실시간으로 `events` 리스너에 전달됨.
- 실시간 토큰에 PII가 포함될 수 있으나, 현재도 미해결이므로 회귀 아님.
- 최종 `CallLlmResponse.content`에 대해서만 mask_llm_output → demask 적용.

**응답의 tool_calls / reasoning_content 마스킹**:
- `CallLlmResponse.tool_calls`의 `arguments`와 `LlmChatResponse.tool_calls`에 PII가 포함될 수 있으나,
  **백그라운드 경로는 tool을 전달하지 않으므로** (`tools: &[]` 또는 `Default::default()`) tool_call이 발생하지 않는다.
- `reasoning_content` / `reasoning_trace`도 백그라운드에서 활성화되지 않는다.
- 향후 백그라운드에서 tool 또는 reasoning을 사용하는 경우, 이 필드들의 마스킹이 필요하다 (out-of-scope).

**증거**:
- 백그라운드 경로에서 PII가 마스킹되어 송출되는지 확인하는 테스트.
- 메인 턴에서는 마스킹이 스킵되는지 확인하는 테스트.
- 마스킹 미설치 시 기존 동작과 byte-identical인지 확인하는 테스트.

### 4. dispatcher 기존 redact_messages_for_cloud 제거

`tini/tinicore/src/llm/dispatcher/default.rs:3892`의 `redact_messages_for_cloud`는
일방향 마스킹으로, `call_llm_with_extra_headers` 내부 마스킹과 중복된다.

- `redact_messages_for_cloud` 호출을 제거하거나 비활성화.
- `set_background_dispatch_masking` 게이트 관련 코드도 정리.
- dispatcher의 `dispatch()` → `call_llm_with_extra_headers` 경로가
  `call_llm_with_extra_headers` 내부 마스킹으로 커버됨.

**증거**: dispatcher 경로에서 `redact_messages_for_cloud`가 더 이상 호출되지 않는지 확인.
`call_llm_with_extra_headers` 내부 마스킹이 동일한 PII를 마스킹하는지 확인.

## 제약

### 보안 (신뢰 경계)

- **클라우드 송출 경계**: 모든 클라우드 LLM 호출은 PII가 마스킹된 상태로 송출되어야 함.
  메인 턴은 `agent_loop`가, 백그라운드는 LLM call 함수 내부가 담당.
- **task-local 신뢰**: `MAIN_TURN_MASKING`은 `agent_loop` 내부에서만 `true`로 설정됨.
  외부에서 임의로 `true`로 설정하여 마스킹을 우회할 수 없어야 함.
  static 가시성을 `pub(crate)`로 제한하여 외부 크레이트에서 `scope(true, ...)` 호출 차단.

### 성능

- 마스킹 미설치 시 (`global_sensitive_masking() == None`): task-local 조회 1회 + `None` 분기 → 기존 동작과 byte-identical.
- 메인 턴: task-local 조회 1회 + `true` 분기 → 기존 동작과 byte-identical.
- 백그라운드 마스킹 시: detector chain 실행 비용 발생 (기존 메인 턴 마스킹과 동일한 비용).

### 호환성

- `call_provider`, `call_llm_with_extra_headers`, `call_llm_streaming_with_extra_headers`의
  함수 시그니처는 변경하지 않음 (파라미터 추가 없음 — task-local + global 조회로 자동 적용).
- `call_llm`, `call_llm_streaming` (pub wrapper)은 변경하지 않음 (내부 함수가 마스킹 처리).
- 기존 호출자 코드 변경 불필요.
- `feature = "sensitive"` 가드 유지: 해당 feature가 없으면 마스킹 코드가 컴파일에서 제외됨.

## 범위 외

- 메인 턴의 `agent_loop` 마스킹 로직 변경 (`mask_messages_for_cloud`, `mask_llm_output`,
  `demask_assistant_messages`, `demask_request_args` 등).
- 스트리밍 응답의 실시간 PII 노출 문제 (현재도 미해결, 회귀 아님).
- `call_llm` / `call_llm_streaming`의 가시성을 `pub(crate)`로 강등 (외부 결정 사항).
- `ActiveLlmRouter`의 Product 채널이 dispatcher를 경유하도록 구조 변경.
- `LlmMessage` 타입에 대한 별도 PII detector 구현 (기존 `ChatMessage`용 detector 재용).
- 백그라운드 경로에서 tool 사용 시 `tool_calls.arguments` 및 `reasoning_content` 마스킹
  (현재 백그라운드는 tool/reasoning 미사용).
