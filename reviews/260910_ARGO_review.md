1. sha cache 를 사용하는 지금, LARGE_BATCH_WARN_BYTES 의 체크는 여전히 필요한가?

2. chain bucket 이 3인데, 3개로 충분한가?

3. background llm 일 경우 cache 사용이 굳이 필요한가? background llm 쪽의 cache 사용은 삭제하자

4. 아래 부분 메시지 삭제가 필요해보임, 비슷하게 아무 조건없이 그냥 warn 으로 출력하는  성격의 메시지는 info 로 변경 또는 삭제할 것
  2026-09-10T01:55:04.899865Z  WARN tinicore::agent::guardrails: INPUT guardrails run against individual user messages — each message's text is checked in isolation, but cross-turn context is NOT passed to them. EVERY user message in history is scanned (unbounded — this is not a recent-window check), so a credential planted in an earlier turn IS caught; however, a prompt injection that references content across messages is still invisible to an input rule. Use the TOOL-INPUT and OUTPUT layers to catch what it makes the model DO. target="guardrails

5. 이제 guardrails/masking 둘 다 global 인데 argo-cli / tinicli 에서 AgentLoopConfig 설정을 검토해봐야한다. 여기는 아직도 per-run 으로 들어가고 있나?

6. if let Err(e) = tinicore::agent::guardrails::run_input_guardrails_with_text 여기서 이제 run_input_guardrails_with_text 가 per-run 을 global 로 받을 필요가 없지않나? 내부에 global 을 보는데? None 으로 해야한다.

7. build_layer_detector 가 fallback 으로 작동할시에는 warning 이라도 필요하지 않나?

8. try_from_filter 만 남기고 from_filter 는 삭제하자.
