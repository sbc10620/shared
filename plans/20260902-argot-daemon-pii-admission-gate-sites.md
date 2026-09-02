# PII admission gate — 정확한 삽입 지점 두 곳

[`20260902-argot-daemon-pii-guardrails.md`](20260902-argot-daemon-pii-guardrails.md) 의
**4단계** 를 코드 수준으로 구체화한 문서. "admission gate 를 어디에 넣느냐"에 대한 답이다.

대상 저장소: `argo-tizen` @ `main` (`d536a81d`). 아래 줄번호는 전부 그 시점 기준이며,
인용된 코드는 실제 파일에서 읽은 것이다.

---

## 왜 두 곳인가

`argot-daemon` 에서 사용자 텍스트가 DB 에 들어가는 경로는 **둘**이고, 서로 만나지 않는다.

```
① 이 기기의 모든 턴                        ② 원격 피어(A2A)의 요청
   gRPC / 텔레그램 / cron / 서브에이전트        A2A mesh
   / resume                                      │
        │                                        │
   GatewayKernel::dispatch                   ArgotA2aRunner::run()
        │                                        │   ← run_turn 을 거치지 않음
   run_turn → prepare()                          │
        │                                        │
   conversations::ensure → save_message      persist_request_best_effort → save_message
```

`tinicore::agent::guardrails::run_input_guardrails_with_text` 의 doc 이 이 게이트의 계약을
정의한다:

> This is the **host-side admission gate**. Hosts call it *before* `save_message` and *before*
> pushing the user message into history. When it returns `Err`, the host must **skip the persist
> and history push entirely** — the credential never reaches the DB and never appears in a later
> turn's replay.

한 곳만 막으면 다른 쪽은 이 계약을 못 지킨다.

> ⚠️ **`transport/grpc/admission.rs` 와 혼동 금지.** 이름이 같지만 그쪽은 **동시 실행 개수
> 세마포어**(`DEFAULT_GRPC_CHAT_DISPATCH_LIMIT: usize = 16`)다. 내용 검사와 무관하고, PII 검사를
> 넣으면 안 된다 — `kernel.dispatch` 이전이라 메시지가 아직 `ChatMessage` 로 파싱되기도 전이고,
> gRPC 전용이라 텔레그램/cron/A2A 는 애초에 안 지나간다.

---

## (가) `crates/argot-daemon/src/turn/mod.rs`

`async fn prepare()`(`:435`) 안. 기존 `prompt_guard` 블록이 `:548` 에서 닫히고 `:550` 에서
`conversations::ensure`(DB 쓰기의 시작)가 온다. **그 사이**다.

### 현재 코드

```rust
 514|        if let Some(guard) = &self.pre_persist_guard {
 515|            match prompt_guard::evaluate(guard, &raw_user_msg.text()) {
 516|                GuardOutcome::Allow { warned } => { … }
 521|                GuardOutcome::Block { rule_id, warned } => {
     |                    …
 526|                    send_prompt_guard_refusal(out, block_id).await;
 527|                    return Ok(None);
     |                }
 529|                GuardOutcome::Sanitize { … } => {
 545|                    raw_user_msg = ChatMessage::user(sanitized, now);
     |                }
 547|            }
 548|        }
 549|
 550|        if let Err(e) = conversations::ensure(storage.database.as_ref(), &session_id, "").await {
```

### 삽입

```rust
         }                                              // :548  prompt_guard 블록 끝

+        // PII admission gate — the same pre-persist contract the prompt guard
+        // above already honours: refusing here keeps the value out of the DB,
+        // so it never reappears in a later turn's replay.
+        //
+        // `raw_user_msg`, not the original input: the Sanitize arm may have
+        // rewritten it, and what gets checked must be what gets stored.
+        if crate::safety::input_guardrails_for_run().is_some()
+            && tinicore::agent::guardrails::run_input_guardrails_with_text(
+                &raw_user_msg.text(),
+                crate::safety::input_guardrails_for_run().as_ref(),
+            )
+            .await
+            .is_err()
+        {
+            fire_pii_event(self.ctx.as_ref(), "block").await;
+            send_prompt_guard_refusal(out, block_id).await;
+            return Ok(None);
+        }

         if let Err(e) = conversations::ensure(…).await {   // :550  DB 쓰기 시작
```

**`raw_user_msg` 를 검사하는 것이 핵심이다.** `GuardOutcome::Sanitize`(`:545`)가 이미
`raw_user_msg` 를 덮어썼을 수 있다. 원본을 검사하면 "검사한 것 ≠ 저장되는 것" 이 된다.

거부 응답은 기존 `send_prompt_guard_refusal`(`:1667`)을 그대로 쓴다. 이 함수가 내보내는 문구
`PROMPT_GUARD_REFUSAL`(`:111`) 의 주석이 그 이유를 이미 적어놨다:

> Same wording as tinicore's in-loop guard refusal, so both guard layers speak with one voice and
> **neither leaks which layer matched**.

PII 층도 같은 문구를 쓰는 게 맞다 — 문구가 갈리면 그 자체가 "무엇이 걸렸는지" 를 알려준다.

> **결정 필요 — 이벤트 이름.** 기존 `fire_prompt_guard_event`(`:1654`)는 이름을 하드코딩해
> `prompt_guard.match` 를 쏜다. PII 는 별개 층이므로 `pii.match` 로 구분하는 편이 운영자에게
> 유용하다. 위 스케치의 `fire_pii_event` 가 그것이고, 기존 함수를 이벤트 이름 파라미터를 받도록
> 일반화하는 방법도 있다. 페이로드는 기존과 동일하게 **규칙 id 와 action 만, 메시지 내용은 절대
> 싣지 않는다.**

---

## (나) `crates/argot-daemon/src/transport/a2a/executor.rs`

`ArgotA2aRunner::run()`(`:104`). **`run_turn` 을 거치지 않는 유일한 경로**라 (가)가 덮지 못한다.

### 현재 코드 — 순서가 곧 문제다

```rust
104|    async fn run(&self, requester: &str, task: &Task) -> Result<String, ServedExecutionError> {
105|        persist_request_best_effort(&self.ctx, requester, task).await;   // ← DB 쓰기가 첫 줄
106|        let mut config = (self.config_factory)(task).map_err(ServedExecutionError::Failed)?;
   |        …
126|        let result = serve_delegated_task(…, config, …).await;           // ← in-loop 검사는 여기
```

계획 5단계로 `config.guardrails` 를 채워도 **검사는 `:126` 에서야 돈다.** 그때는 이미 원격
피어의 메시지가 DB 에 들어간 뒤다.

| | ① turn/mod.rs | ② A2A |
|---|---|---|
| 사전-영속 게이트 | ✅ | ❌ 없으면 공백 |
| in-loop 검사 (per-run 체인) | ✅ | ✅ |
| **차단 시 DB** | 안 남음 | **이미 남음** |

**그리고 이쪽이 더 위험하다.** executor 스스로 이 입력을 `TrustTier::Untrusted`(`:118`) 로
넘긴다 — 가장 안 믿는 입력이 가장 약한 방어를 받는 꼴이다.

### 삽입

```rust
     async fn run(&self, requester: &str, task: &Task) -> Result<String, ServedExecutionError> {
+        // PII admission gate. MUST precede `persist_request_best_effort` — a
+        // refused peer request must not reach the DB. This is a remote peer's
+        // text, served at `TrustTier::Untrusted`; the local rail's gate in
+        // `turn/mod.rs` does not cover this path, which bypasses `run_turn`.
+        if crate::safety::input_guardrails_for_run().is_some()
+            && tinicore::agent::guardrails::run_input_guardrails_with_text(
+                &served_request_prompt(task),
+                crate::safety::input_guardrails_for_run().as_ref(),
+            )
+            .await
+            .is_err()
+        {
+            // Deliberately opaque to the peer: the refusal reason IS the
+            // detection result, so echoing it back is a probing oracle.
+            return Err(ServedExecutionError::Failed(
+                "request refused by policy".to_string(),
+            ));
+        }

         persist_request_best_effort(&self.ctx, requester, task).await;   // :105
```

### 함께 필요한 리팩터 — `served_request_prompt`

게이트가 검사할 텍스트는 `persist_request_best_effort` 가 **실제로 저장하는** 텍스트와 같아야
한다. 그 추출 로직이 지금 그 함수 안에 인라인돼 있다(`:249-255`):

```rust
    let prompt = task
        .history
        .iter()
        .rev()
        .map(message_text)
        .find(|text| !text.trim().is_empty())
        .unwrap_or_default();
```

이걸 게이트 쪽에 복붙하면 두 벌이 되고, 나중에 한쪽만 바뀌면 **검사한 것과 저장한 것이 갈린다**
— 이 게이트가 막으려던 바로 그 구멍이다. argo-tizen `CLAUDE.md` 도 *"Do not create parallel
primitives"* 라고 못박는다. 그래서 함수로 뽑고 양쪽이 부른다:

```rust
+/// The text `persist_request_best_effort` will write — the single source both
+/// the admission gate and the persist read, so the two cannot drift apart
+/// about what was checked versus what was stored.
+fn served_request_prompt(task: &Task) -> String {
+    task.history
+        .iter()
+        .rev()
+        .map(message_text)
+        .find(|text| !text.trim().is_empty())
+        .unwrap_or_default()
+}
```

`persist_request_best_effort` 의 인라인 블록은 `let prompt = served_request_prompt(task);` 로
교체한다. `message_text` 는 이미 import 돼 있다(`:11`).

> `run()` 은 `async fn` 이므로 양쪽 다 `.await` 가 그대로 붙는다. (가) 의 `prepare()` 도 마찬가지.

---

## 두 게이트가 공유하는 것

- **호출 대상**: `tinicore::agent::guardrails::run_input_guardrails_with_text(text, per_run)`
  — `pub`, 항상 컴파일됨(`agent/guardrails` 는 feature gate 가 없다).
- **`per_run` 인자**: `crate::safety::input_guardrails_for_run()`.
  계획 ④의 결론대로 우리는 tinicore 의 전역 `install_guardrails` 를 쓰지 않으므로,
  **`None` 을 넘기면 아무것도 검사하지 않는다.** 반드시 넘겨야 한다.
- **cfg 없음**: `input_guardrails_for_run()` 은 `safety/mod.rs` 의 shim 이라
  `guardrails` feature 가 꺼진 빌드에서는 `None` 을 반환한다. 두 호출 지점 어디에도
  `#[cfg(...)]` 를 쓰지 않는다 — upstream tinicli 가 cfg 쌍을 shim 한 곳에 가둔 이유가 바로
  "나중에 추가되는 호출 지점이 그 쌍을 재유도하거나 빠뜨리지 않게" 하기 위함이다.
- **반환**: `Result<(), GuardrailTripwireError>`. 에러 값 자체는 로그에도 남기지 않는다
  (매칭 내용이 곧 PII 다).

체인이 비어 있으면 `run_input_guardrails_with_text` 는 zero-cost `Ok` 라, 위 스케치의
`is_some()` 선검사는 없어도 정확성에는 영향이 없다. `Option` 을 두 번 만드는 비용을 아끼려면
지역 변수로 한 번만 받는 편이 낫다 — 구현 시 정리한다.

---

## 테스트

두 게이트가 지키는 성질은 **"차단되면 DB 에 없다"** 이고, 그건 곧 **호출 순서**다. 순서를
직접 단언한다.

1. **(가)** — PII 가 든 메시지로 턴을 돌려 거부되는지 + `load_messages` 에 그 메시지가 없는지.
2. **(나)** (`--features a2a,guardrails`) — PII 가 든 `Task` 로 `ArgotA2aRunner::run()` 호출 →
   `Err` **그리고** 세션 스토어에 없는지.
3. **음성 테스트** — 각 게이트를 `save_message` **뒤로** 옮기면 해당 테스트가 실제로 깨지는지.
   안 깨지면 그 테스트는 순서를 안 지키고 있는 것이므로 테스트를 고친다.
4. **드리프트 테스트** — `served_request_prompt` 가 게이트와 persist 양쪽에서 불리는지
   (호출 개수 단언). 한쪽이 다시 인라인되면 깨져야 한다.

`argot-e2e` 는 데몬을 `Command::new(&self.argot_bin)` 으로 서브프로세스로 띄우므로
(`world.rs:314`), 프로세스 전역 `OnceLock` 오염 없이 `mode` 를 바꿔가며 시나리오를 돌릴 수 있다.

---

## 확정 전 확인할 것

- **이벤트 이름** — `pii.match` 로 분리할지, 기존 `prompt_guard.match` 에 합칠지 (위 (가) 참조).
- **`block_id` 스코프** — (가) 삽입 지점에서 `block_id`(`:445` 파라미터)가 여전히 살아 있는지
  컴파일로 확인. `:526` 에서 쓰이므로 문제없어 보이나 소유권 이동 여부는 봐야 한다.
- **A2A 거부의 관측성** — 피어에게는 불투명하게 돌려주되, 로컬 로그/이벤트에는 남길지.
  남긴다면 (가)와 같은 페이로드 규칙(규칙 id + action 만).
