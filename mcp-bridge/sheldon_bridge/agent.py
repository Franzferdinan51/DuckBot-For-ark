"""The agentic loop — the brain of the Sheldon Bridge.

Receives a player message, calls the LLM with tier-appropriate tools,
executes tool calls, feeds results back, and repeats until the LLM
generates a final text response.

The agent never makes permission decisions — it delegates to the
ToolRegistry for access control and the RateLimiter for throttling.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

import litellm

from sheldon_bridge.auth import RateLimiter
from sheldon_bridge.providers.llm import LLMProvider, LLMResponse
from sheldon_bridge.session import Session
from sheldon_bridge.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 25
TOOL_EXECUTION_TIMEOUT = 30.0  # seconds per tool call


@dataclass
class AgentResult:
    """The result of an agentic loop run."""

    response_text: str
    tool_calls_made: int
    iterations: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost: float
    duration_ms: float
    error: str | None = None


class Agent:
    """Runs the agentic loop for a single player interaction.

    The agent is stateless — all state lives in the Session. The agent
    reads from the session, calls the LLM, executes tools, and writes
    results back to the session.
    """

    def __init__(
        self,
        llm: LLMProvider,
        registry: ToolRegistry,
        rate_limiter: RateLimiter,
        game_command_handler: Callable | None = None,
    ):
        self.llm = llm
        self.registry = registry
        self.rate_limiter = rate_limiter
        self._game_handler = game_command_handler

    async def run_streaming(
        self,
        session: Session,
        user_message: str,
        websocket_send,
    ) -> AgentResult:
        """Streaming variant — sends tokens to websocket as they arrive.

        Does NOT support tool calls (streaming + function calling is not universally
        supported by all LLM providers). Falls back to regular run() for any
        interaction that requires tool use.
        """
        from sheldon_bridge.cache import get_cache

        start_time = time.time()
        player_id = session.player.player_id
        tier = session.player.tier

        # Rate limit check
        allowed, reason = self.rate_limiter.check(player_id, tier, "requests")
        if not allowed:
            return AgentResult(
                response_text=f"You're sending messages too quickly. Please wait a moment. ({reason})",
                tool_calls_made=0, iterations=0,
                total_input_tokens=0, total_output_tokens=0,
                total_cost=0.0, duration_ms=(time.time() - start_time) * 1000,
            )

        session.add_user_message(user_message)
        messages = session.get_messages()

        # Compute cost estimate upfront
        input_tokens = self.llm.count_tokens(messages)
        max_context = self.llm.get_max_context()

        if input_tokens > max_context * 0.85:
            session.truncate_to_budget(max_context, reserve=8192)
            messages = session.get_messages()

        # Check semantic cache first
        cache = get_cache()
        context_key = f"{tier}:{session.player.tribe_id or session.player.player_id}"
        cached = await cache.lookup(user_message, context_key=context_key)
        if cached:
            # Stream cached response token by token
            words = cached.response.split(" ")
            partial = ""
            for word in words:
                partial += word + " "
                await websocket_send(json.dumps({"type": "stream_token", "content": word + " "}))
                await asyncio.sleep(0.02)  # natural typing pace
            session.add_assistant_message({"role": "assistant", "content": cached.response})
            session.track_usage(0, 0, 0)
            return AgentResult(
                response_text=cached.response,
                tool_calls_made=0, iterations=0,
                total_input_tokens=0, total_output_tokens=0,
                total_cost=0.0, duration_ms=(time.time() - start_time) * 1000,
            )

        # Stream the LLM response
        tools = self.registry.get_tools_for_tier(tier)
        tools_llm = self.registry.to_llm_format(tier) if tools else None

        # Check if streaming with tools is viable — if not, fall back to regular run
        if tools_llm:
            # Can't stream with tool calls universally, fall back
            return await self.run(session, user_message)

        total_input = 0
        total_output = 0
        total_cost = 0.0
        full_response = ""

        try:
            async for token in self.llm.complete_streaming(messages, tools=None):
                full_response += token
                await websocket_send(json.dumps({
                    "type": "stream_token",
                    "content": token,
                }))

        except Exception as e:
            logger.error(f"Streaming LLM call failed: {e}")
            session.track_usage(0, 0, 0)
            return AgentResult(
                response_text="I'm having trouble connecting to my brain right now. Try again in a moment.",
                tool_calls_made=0, iterations=1,
                total_input_tokens=0, total_output_tokens=0,
                total_cost=0.0, duration_ms=(time.time() - start_time) * 1000,
            )

        # Cache the complete response
        if full_response:
            await cache.store(user_message, full_response, context_key=context_key)

        # Track usage (estimate tokens from response length)
        output_tokens = len(full_response) // 4
        session.track_usage(input_tokens, output_tokens, 0.0)
        session.add_assistant_message({"role": "assistant", "content": full_response})

        return AgentResult(
            response_text=full_response,
            tool_calls_made=0,
            iterations=1,
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            total_cost=0.0,
            duration_ms=(time.time() - start_time) * 1000,
        )

    async def run(
        self,
        session: Session,
        user_message: str,
    ) -> AgentResult:
        """Run the agentic loop for a user message.

        Args:
            session: The player's conversation session.
            user_message: The raw message from the player.

        Returns:
            AgentResult with the final response and usage stats.
        """
        start_time = time.time()
        tier = session.player.tier
        player_id = session.player.player_id

        # Reset tool loop guardrail for fresh conversation turn
        from sheldon_bridge.agent_guardrail import clear_guardrail
        clear_guardrail(player_id)

        # Rate limit check
        allowed, reason = self.rate_limiter.check(player_id, tier, "requests")
        if not allowed:
            return AgentResult(
                response_text=f"You're sending messages too quickly. Please wait a moment. ({reason})",
                tool_calls_made=0,
                iterations=0,
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost=0.0,
                duration_ms=(time.time() - start_time) * 1000,
            )

        # Add user message to session
        session.add_user_message(user_message)

        # Update player position if provided (the mod sends it with each message)
        # Position is in the player_context, already set on the session

        # ─── Self-Improving: Cross-Session Memory Recall ──────────────────────
        # Before the loop, inject relevant memories so the AI knows from history
        steps_log: list[str] = []  # track steps for agent improver
        try:
            from sheldon_bridge.skills.improver import get_cross_session_memory
            memory = get_cross_session_memory()
            # Recall memories relevant to this player's tribe or recent topics
            recall_query = f"{session.player.display_name} {session.player.tribe_id or ''} {user_message[:50]}"
            memories = memory.recall(recall_query, limit=3)
            if memories:
                memory_lines = ["\n## Past Lessons (from other sessions)"]
                for mem in memories:
                    memory_lines.append(f"- {mem.content}")
                # Prepend as system message so LLM sees it
                session.add_system_prompt("\n".join(memory_lines))
        except Exception as e:
            logger.debug(f"Cross-session memory recall skipped: {e}")

        # Get tier-appropriate tools
        tools = self.registry.to_llm_format(tier)

        # Ensure conversation fits within context window
        max_context = self.llm.get_max_context()
        session.truncate_to_budget(max_context)

        total_input = 0
        total_output = 0
        total_cost = 0.0
        tool_calls_made = 0

        for iteration in range(MAX_ITERATIONS):
            try:
                # Call LLM
                llm_response = await self.llm.complete(
                    messages=session.get_messages(),
                    tools=tools if iteration < MAX_ITERATIONS - 1 else None,
                )

                total_input += llm_response.input_tokens
                total_output += llm_response.output_tokens
                total_cost += llm_response.cost

                # Record metrics for LLM usage
                from sheldon_bridge.metrics import get_metrics
                metrics = get_metrics()
                metrics.record_llm(llm_response.input_tokens, llm_response.output_tokens, llm_response.cost)

            except litellm.ContextWindowExceededError:
                logger.warning(f"Context window exceeded for {player_id}, truncating")
                session.truncate_to_budget(max_context, reserve=8192)
                continue

            except litellm.RateLimitError:
                wait_time = min(2**iteration, 30)
                logger.warning(f"LLM rate limited, waiting {wait_time}s")
                await asyncio.sleep(wait_time)
                continue

            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                from sheldon_bridge.metrics import get_metrics
                get_metrics().record_llm_error()
                session.track_usage(total_input, total_output, total_cost)
                return AgentResult(
                    response_text="I'm having trouble connecting to my brain right now. Try again in a moment.",
                    tool_calls_made=tool_calls_made,
                    iterations=iteration + 1,
                    total_input_tokens=total_input,
                    total_output_tokens=total_output,
                    total_cost=total_cost,
                    duration_ms=(time.time() - start_time) * 1000,
                    error=str(e),
                )

            # No tool calls — we have the final response
            if not llm_response.tool_calls:
                response_text = llm_response.content or ""
                session.add_assistant_message({
                    "role": "assistant",
                    "content": response_text,
                })
                session.track_usage(total_input, total_output, total_cost)

                # ─── Self-Improving: Review completed task ───────────────────────
                # If this was a multi-step task, ask the improver to analyze it
                if tool_calls_made >= 3:
                    try:
                        from sheldon_bridge.skills.improver import (
                            get_agent_improver,
                            get_cross_session_memory,
                        )
                        from sheldon_bridge.skills.registry import get_skill_registry
                        improver = get_agent_improver(get_skill_registry())
                        improver.review_completed_task(
                            task_description=user_message[:100],
                            steps=steps_log[-10:],  # last 10 steps
                            successful=True,
                            player_tier=tier,
                        )
                        # Store useful patterns in cross-session memory
                        if tool_calls_made >= 5:
                            memory = get_cross_session_memory()
                            memory.store(
                                key=f"multi_step:{tier}:{user_message[:30].lower()}",
                                content=(
                                    f"Task: '{user_message[:80]}' solved in {tool_calls_made} steps. "
                                    f"Steps: {' -> '.join(steps_log[-5:])}"
                                ),
                                tags=["multi-step", tier],
                            )
                    except Exception as e:
                        logger.debug(f"Agent improver review skipped: {e}")

                return AgentResult(
                    response_text=response_text,
                    tool_calls_made=tool_calls_made,
                    iterations=iteration + 1,
                    total_input_tokens=total_input,
                    total_output_tokens=total_output,
                    total_cost=total_cost,
                    duration_ms=(time.time() - start_time) * 1000,
                )

            # Process tool calls
            # Add the assistant message (with tool_calls) to the conversation
            assistant_msg = llm_response.raw.choices[0].message
            session.add_assistant_message(assistant_msg.model_dump())

            # Execute each tool call
            for tool_call in llm_response.tool_calls:
                tool_name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    session.add_tool_result(
                        tool_call.id,
                        tool_name,
                        json.dumps({"error": f"Invalid arguments: {e}"}),
                    )
                    tool_calls_made += 1
                    from sheldon_bridge.metrics import get_metrics
                    get_metrics().record_tool_call(tool_name, 0, error=True)
                    continue

                # DEFENSE IN DEPTH: Validate tool call against permissions
                allowed, reason = self.registry.validate_tool_call(tool_name, arguments, tier)
                if not allowed:
                    logger.warning(
                        f"Tool call rejected: {tool_name} for tier {tier} — {reason}"
                    )
                    session.add_tool_result(
                        tool_call.id,
                        tool_name,
                        json.dumps({"error": f"Permission denied: {reason}"}),
                    )
                    tool_calls_made += 1
                    from sheldon_bridge.metrics import get_metrics
                    get_metrics().record_tool_call(tool_name, 0, error=True)
                    continue

                # Rate limit check for tool calls
                rate_ok, rate_reason = self.rate_limiter.check(player_id, tier, "tool_calls")
                if not rate_ok:
                    session.add_tool_result(
                        tool_call.id,
                        tool_name,
                        json.dumps({"error": f"Rate limited: {rate_reason}"}),
                    )
                    tool_calls_made += 1
                    continue

                # ─── Tool Loop Guardrail ─────────────────────────────────────────
                from sheldon_bridge.agent_guardrail import get_guardrail, GuardrailDecision
                guardrail = get_guardrail(player_id)
                check = guardrail.check(tool_name, arguments)
                if check.decision == GuardrailDecision.HALT:
                    session.add_tool_result(
                        tool_call.id,
                        tool_name,
                        json.dumps({"error": f"Tool circuit breaker: {check.reason}"}),
                    )
                    tool_calls_made += 1
                    # Stop the loop — too many failures
                    session.track_usage(total_input, total_output, total_cost)
                    return AgentResult(
                        response_text=f"I've been trying the same thing repeatedly and it's not working. Let's try a different approach.",
                        tool_calls_made=tool_calls_made,
                        iterations=iteration + 1,
                        total_input_tokens=total_input,
                        total_output_tokens=total_output,
                        total_cost=total_cost,
                        duration_ms=(time.time() - start_time) * 1000,
                    )
                elif check.decision == GuardrailDecision.WARN:
                    logger.warning(f"[Guardrail] WARN on {tool_name}: {check.reason}")

                # Execute the tool
                try:
                    context = {
                        "player": session.player,
                        "game_handler": self._game_handler,
                    }
                    result = await asyncio.wait_for(
                        self.registry.execute(tool_name, arguments, context=context),
                        timeout=TOOL_EXECUTION_TIMEOUT,
                    )

                    # Serialize result
                    if isinstance(result, str):
                        result_str = result
                    else:
                        result_str = json.dumps(result, default=str)

                    session.add_tool_result(tool_call.id, tool_name, result_str)
                    from sheldon_bridge.metrics import get_metrics
                    get_metrics().record_tool_call(tool_name, 0, error=False)
                    steps_log.append(tool_name)  # track for agent improver
                    guardrail.record(tool_name, arguments, result_str, error=False)  # success — reset counters

                except asyncio.TimeoutError:
                    logger.error(f"Tool '{tool_name}' timed out after {TOOL_EXECUTION_TIMEOUT}s")
                    session.add_tool_result(
                        tool_call.id,
                        tool_name,
                        json.dumps({"error": "Tool execution timed out"}),
                    )
                    from sheldon_bridge.metrics import get_metrics
                    get_metrics().record_tool_call(tool_name, TOOL_EXECUTION_TIMEOUT * 1000, error=True)
                    guardrail.record(tool_name, arguments, "TIMEOUT", error=True)

                except Exception as e:
                    logger.error(f"Tool '{tool_name}' raised {type(e).__name__}: {e}")
                    session.add_tool_result(
                        tool_call.id,
                        tool_name,
                        json.dumps({"error": f"{type(e).__name__}: {e}"}),
                    )
                    from sheldon_bridge.metrics import get_metrics
                    get_metrics().record_tool_call(tool_name, 0, error=True)
                    guardrail.record(tool_name, arguments, str(e), error=True)

                tool_calls_made += 1

        # Reached max iterations
        session.track_usage(total_input, total_output, total_cost)
        return AgentResult(
            response_text="I've been thinking too hard about this one. Could you try a simpler request?",
            tool_calls_made=tool_calls_made,
            iterations=MAX_ITERATIONS,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cost=total_cost,
            duration_ms=(time.time() - start_time) * 1000,
        )
