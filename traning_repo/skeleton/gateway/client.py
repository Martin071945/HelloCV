"""上游 API 转发层：构造请求、发送、重试、取出答案。

这一层要解决的真实问题：

* **鉴权**：``Authorization: Bearer <key>``，key 只从配置/环境变量来，绝不写死；
* **请求格式**：OpenAI 兼容的 ``/chat/completions``，开 ``response_format={"type":"json_object"}``
  让上游保证返回合法 JSON，同时默认关掉思考模式（``thinking={"type":"disabled"}``）省时间；
* **重试**：网络错误、429、5xx、**空回复**都值得退避重试；而 401/403/400（key 错、模型名错、
  参数非法）重试没有意义，要立刻失败；
* **只取 content**：思考模型还会返回 ``reasoning_content``（思维链），它**不是**答案，必须丢掉。

你需要实现（共 3 个）::

    build_body(request)         -> dict                    # 组装 Chat Completions 请求体
    extract_content(response)   -> (content, 有无思维链, finish_reason)
    decide(request)             -> (content, 元信息)        # 带重试的发送主流程

对应测试：``tests/test_client.py``。
"""

from __future__ import annotations

import json  # noqa: F401 - 实现 build_body 时要用到
import random
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

import requests

from .config import GatewayConfig
from .prompts import SYSTEM_PROMPT, USER_PREFIX  # noqa: F401 - 实现 build_body 时要用到

__all__ = ["LlmError", "LlmAuthError", "LlmFatalError", "LlmClient"]

#: 这些 HTTP 状态码值得重试（服务端临时不可用 / 限流）
RETRY_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 522, 524})


class LlmError(RuntimeError):
    """调用上游失败（重试耗尽或响应结构异常）。"""


class LlmAuthError(LlmError):
    """API Key 缺失/无效（401/403）。"""


class LlmFatalError(LlmError):
    """重试也不会变好的错误（HTTP 400：模型名或参数不合法）。"""


def _snippet(response: Any, limit: int = 300) -> str:
    """截一段响应体放进错误信息里，方便定位（太长的日志没人看）。"""
    text = str(getattr(response, "text", "") or "").strip().replace("\n", " ")
    if not text:
        return "<空响应体>"
    return text[:limit] + ("…" if len(text) > limit else "")


def _header(response: Any, name: str) -> Optional[str]:
    """从响应的 headers 里取一个值（缺失或类型不对都返回 ``None``）。"""
    headers = getattr(response, "headers", None) or {}
    try:
        value = headers.get(name)
    except Exception:  # noqa: BLE001 - headers 可能是任何对象
        return None
    return value if isinstance(value, str) else None


class LlmClient:
    """OpenAI 兼容 Chat Completions 的最小客户端（线程安全）。"""

    def __init__(
        self,
        config: GatewayConfig,
        session: Optional[requests.Session] = None,
        sleep: Callable[[float], None] = time.sleep,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.config = config
        self.api_key = config.resolved_api_key()
        self._session = session or requests.Session()
        self._sleep = sleep
        self._log = log or (lambda _message: None)
        self._lock = threading.Lock()
        self._closed = False

    # ------------------------------------------------------------------ #
    # 已经写好的部分（不用改）
    # ------------------------------------------------------------------ #
    @property
    def endpoint(self) -> str:
        """拼出完整 URL：``<base>/chat/completions``（base 已经带了就不重复拼）。"""
        base = (self.config.api_base_url or "").rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"

    def build_headers(self) -> Dict[str, str]:
        """鉴权与内容类型。"""
        return {
            "Authorization": "Bearer %s" % self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def retry_delay(self, attempt: int, retry_after: Optional[str]) -> float:
        """指数退避 + 抖动；服务端给了 ``Retry-After`` 就听它的（不超过 backoff_max）。"""
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), self.config.backoff_max))
            except (TypeError, ValueError):
                pass
        delay = min(self.config.backoff_base * (2 ** (attempt - 1)), self.config.backoff_max)
        return delay + random.uniform(0.0, self.config.backoff_base)

    def close(self) -> None:
        self._closed = True
        try:
            self._session.close()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    # TODO 7：组装请求体
    # ------------------------------------------------------------------ #
    def build_body(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """构造 Chat Completions 请求体。

    提示：

    * ``messages`` 两条：``{"role": "system", "content": SYSTEM_PROMPT}`` 和
      ``{"role": "user", "content": USER_PREFIX + json.dumps(request, ensure_ascii=False, separators=(",", ":"))}``；
    * 还需要 ``model`` / ``stream=False`` / ``temperature`` / ``max_tokens``（都从 ``self.config`` 取）；
    * ``self.config.enable_json_format`` 为真时加
      ``"response_format": {"type": "json_object"}``；
    * 思考开关：``"thinking": {"type": "enabled" if self.config.enable_thinking else "disabled"}``。

    目标：``tests/test_client.py`` 的 ``test_body_*`` 与 ``test_prompt_contains_json_word_for_json_mode`` 通过。
        """
        user_text = USER_PREFIX + json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        body: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            # 思考开关：出拳这种任务开了思考只会更慢
            "thinking": {"type": "enabled" if self.config.enable_thinking else "disabled"},
        }
        if self.config.enable_json_format:
            body["response_format"] = {"type": "json_object"}
        return body

    # ------------------------------------------------------------------ #
    # TODO 8：发送（带重试）
    # ------------------------------------------------------------------ #
    def decide(self, request: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """请求一次出拳，返回 ``(content 文本, 元信息)``；重试耗尽抛 :class:`LlmError`。

    提示（骨架逻辑）：

    * 没有 key（``self.api_key`` 为空）直接抛 :class:`LlmAuthError`；
    * ``attempts = max(1, self.config.max_retries + 1)``，循环 ``attempt = 1..attempts``；
    * 每次 ``self._session.post(self.endpoint, data=payload, headers=..., timeout=(connect, read))``，
      其中 ``payload = json.dumps(body, ensure_ascii=False).encode("utf-8")``；
    * 状态码分支：
      - ``200`` -> ``content, has_reasoning, finish_reason = self.extract_content(response)``，
        返回 ``(content, {"attempt": ..., "http_status": 200, "latency_s": ..., "has_reasoning": ..., "finish_reason": ...})``；
      - ``401`` / ``403`` -> 抛 :class:`LlmAuthError`（不要重试）；
      - ``400`` -> 抛 :class:`LlmFatalError`（不要重试）；
      - 其它：状态码在 ``RETRY_STATUS`` 且还有重试机会 -> ``self._sleep(self.retry_delay(attempt, Retry-After))``
        后 ``continue``；否则抛 :class:`LlmError`；
    * ``LlmError``（比如空回复）和 ``requests.exceptions.RequestException``（网络错误）
      都当作可重试：还有机会就 sleep + 重试，否则把它抛出去 / 循环结束后抛 :class:`LlmError`；
    * 别忘了 ``except (LlmAuthError, LlmFatalError): raise`` 放在前面，避免它们被重试。

    目标：``tests/test_client.py`` 的 ``test_decide_*`` 通过。
        """
        if not self.api_key:
            raise LlmAuthError(
                "缺少 API Key：请设置环境变量 %s，或给 GatewayConfig.api_key 赋值"
                % self.config.api_key_env
            )

        body = self.build_body(request)
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = self.build_headers()
        timeout = (self.config.connect_timeout, self.config.request_timeout)
        attempts = max(1, self.config.max_retries + 1)

        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                with self._lock:  # requests.Session 不保证线程安全
                    response = self._session.post(
                        self.endpoint, data=payload, headers=headers, timeout=timeout
                    )
            except requests.exceptions.RequestException as exc:  # 网络层错误：值得重试
                if attempt >= attempts:
                    raise LlmError(
                        "请求上游失败（第 %d/%d 次）：%s" % (attempt, attempts, exc)
                    ) from exc
                self._log("网络错误（第 %d/%d 次）：%s" % (attempt, attempts, exc))
                self._sleep(self.retry_delay(attempt, None))
                continue

            status = int(getattr(response, "status_code", 0) or 0)
            retry_after = _header(response, "Retry-After")

            # 这些错误重试也不会变好：立刻失败
            if status in (401, 403):
                raise LlmAuthError("鉴权失败（HTTP %d）：%s" % (status, _snippet(response)))
            if status == 400:
                raise LlmFatalError(
                    "上游拒绝了请求（HTTP 400，多为模型名或参数不合法）：%s" % _snippet(response)
                )

            if status == 200:
                try:
                    content, has_reasoning, finish_reason = self.extract_content(response)
                except LlmError as exc:  # 空回复 / 只给了思维链：可重试
                    if attempt >= attempts:
                        raise LlmError(
                            "上游返回 200 但内容不可用（第 %d/%d 次）：%s" % (attempt, attempts, exc)
                        ) from exc
                    self._log("内容不可用（第 %d/%d 次）：%s" % (attempt, attempts, exc))
                    self._sleep(self.retry_delay(attempt, retry_after))
                    continue
                latency = time.monotonic() - started
                self._log(
                    "成功（第 %d/%d 次，%.2fs，finish_reason=%s，思维链=%s）"
                    % (attempt, attempts, latency, finish_reason, "有" if has_reasoning else "无")
                )
                return content, {
                    "attempt": attempt,
                    "http_status": 200,
                    "latency_s": round(latency, 3),
                    "has_reasoning": has_reasoning,
                    "finish_reason": finish_reason,
                }

            # 剩下的状态码：临时故障（429/5xx…）才退避重试
            if status in RETRY_STATUS and attempt < attempts:
                self._log("上游返回 HTTP %d（第 %d/%d 次），准备重试" % (status, attempt, attempts))
                self._sleep(self.retry_delay(attempt, retry_after))
                continue
            raise LlmError(
                "上游返回不可用的状态码 %d（第 %d/%d 次）：%s"
                % (status, attempt, attempts, _snippet(response))
            )

        raise LlmError("上游调用失败：重试 %d 次后仍然没有拿到内容" % attempts)

    # ------------------------------------------------------------------ #
    # TODO 9：取出答案
    # ------------------------------------------------------------------ #
    @staticmethod
    def extract_content(response: Any) -> Tuple[str, bool, str]:
        """从 200 响应里取出 ``content``，返回 ``(content, 是否带思维链, finish_reason)``。

    提示：

    * ``response.json()`` 失败（不是 JSON）-> 抛 :class:`LlmError`；
    * ``data.get("choices")`` 为空 -> 抛 :class:`LlmError`；
    * 取 ``choices[0]["message"]`` 的 ``content`` 与 ``reasoning_content``；
    * ``content`` 不是非空字符串时都要抛 :class:`LlmError`（让上层重试），并且错误信息要能区分原因：
      - 有 ``reasoning_content``（思维链不是答案！）-> 提示"只返回了 reasoning_content"；
      - ``finish_reason == "length"`` -> 提示 max_tokens 不够用；
      - 其它 -> 提示 content 为空；
    * ``has_reasoning`` = ``reasoning_content`` 是非空字符串。

    目标：``tests/test_client.py`` 的 ``test_extract_content_*`` 通过。
        """
        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001 - 不是 JSON 就没法继续
            raise LlmError("上游响应不是合法 JSON：%s" % exc) from exc

        if not isinstance(data, dict):
            raise LlmError("上游响应顶层不是 JSON 对象（%s）" % type(data).__name__)
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LlmError("上游响应里没有 choices（可能被限流或参数不对）")

        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message")
        if not isinstance(message, dict):
            message = {}
        content = message.get("content")
        reasoning = message.get("reasoning_content")
        has_reasoning = isinstance(reasoning, str) and bool(reasoning.strip())
        finish_reason = str(first.get("finish_reason") or "")

        if not isinstance(content, str) or not content.strip():
            # 三种失败要分清楚，否则现场根本不知道为什么没答案
            if has_reasoning:
                raise LlmError("上游只返回了 reasoning_content（思维链不是答案），content 为空")
            if finish_reason == "length":
                raise LlmError("content 为空且 finish_reason=length：max_tokens 不够用")
            raise LlmError("上游返回的 content 为空")

        return content, has_reasoning, finish_reason
