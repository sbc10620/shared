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

### 2. agent_loop에 task-local 설정

`tini/tinicore/src/agent/loop_/llm_call.rs:239`의 `wire_capture::scope` 호출부를
`MAIN_TURN_MASKING.scope(true, ...)`로 감싼다.

```rust
// 변경 후
let outcome = crate::agent::pii_masking::MAIN_TURN_MASKING.scope(true, async {
    crate::llm::wire_capture::scope(
        WireCtx { ... },
        fallback.call_with_fallback_with_extra_headers(...)
    ).await
}).await;
```

- 메인 턴의 FallbackChain → `call_llm_streaming_with_extra_headers` 경로 전체가
  task-local 범위 안에 들어감.
- 메인 턴의 기존 마스킹 로직(`mask_messages_for_cloud`, `mask_llm_output`, `demask`)은 변경 없음.

**증거**: 기존 메인 턴 마스킹 테스트가 전부 통과해야 함 (회귀 없음).

### 3. LLM call 함수 5개에 마스킹 적용

다음 5개 함수의 **HTTP 송출 직전**에 마스킹을 적용한다:

| 함수 | 가시성 | 파일 |
|---|---|---|
| `call_provider` | `pub` | `llm/client.rs:458` |
| `call_llm` | `pub` | `llm/client.rs:752` |
| `call_llm_streaming` | `pub` | `llm/client.rs:2238` |
| `call_llm_with_extra_headers` | `pub(crate)` | `llm/client.rs:810` |
| `call_llm_streaming_with_extra_headers` | `pub(crate)` | `llm/client.rs:2430` |

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

**call_provider 특이사항**:
- `call_provider`는 `LlmChatRequest`(`Vec<LlmMessage>`)를 받음.
- 다른 4개 함수는 `&[ChatMessage]`를 받음.
- `LlmMessage`와 `ChatMessage`는 다른 타입이므로, `call_provider`의 마스킹은
  `LlmMessage` → text 추출 → 마스킹 → 교체 방식으로 별도 구현 필요.

**call_llm_streaming_with_extra_headers 특이사항**:
- 스트리밍 응답은 실시간으로 `events` 리스너에 전달됨.
- 실시간 토큰에 PII가 포함될 수 있으나, 현재도 미해결이므로 회귀 아님.
- 최종 `CallLlmResponse.content`에 대해서만 mask_llm_output → demask 적용.

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

- `call_provider`, `call_llm`, `call_llm_streaming`의 함수 시그니처는 변경하지 않음
  (파라미터 추가 없음 — task-local + global 조회로 자동 적용).
- 기존 호출자 코드 변경 불필요.
- `feature = "sensitive"` 가드 유지: 해당 feature가 없으면 마스킹 코드가 컴파일에서 제외됨.

## 범위 외

- 메인 턴의 `agent_loop` 마스킹 로직 변경 (`mask_messages_for_cloud`, `mask_llm_output`,
  `demask_assistant_messages`, `demask_request_args` 등).
- 스트리밍 응답의 실시간 PII 노출 문제 (현재도 미해결, 회귀 아님).
- `call_llm` / `call_llm_streaming`의 가시성을 `pub(crate)`로 강등 (외부 결정 사항).
- `ActiveLlmRouter`의 Product 채널이 dispatcher를 경유하도록 구조 변경.
- `LlmMessage` 타입에 대한 별도 PII detector 구현 (기존 `ChatMessage`용 detector 재용).
