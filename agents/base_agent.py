"""
agents/base_agent.py — CAMEL ChatAgent 工厂。
为认知子系统的每一层创建 ChatAgent 实例。

LLM 分层策略：
  快速层（Perception / OCC / WorldEngine / Reasoning）→ fast_call()  → qwen3-max（DashScope）
  核心层（Arbiter streaming）                         → get_streaming_client() → Sonnet 4.6（Anthropic）
"""

from __future__ import annotations
import os
from typing import Optional

import config  # 加载 .env

try:
    from camel.agents import ChatAgent
    from camel.messages import BaseMessage
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType, ModelType
    _CAMEL_AVAILABLE = True
except ImportError:
    _CAMEL_AVAILABLE = False

import anthropic

_BASE_URL     = os.environ.get("ANTHROPIC_BASE_URL")
_DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

# ── 多 Key 轮转池 ──────────────────────────────────────────────────────────────
# 从 .env 读取所有 ANTHROPIC_API_KEY / ANTHROPIC_API_KEY_2/3/4...
def _load_key_pool() -> list[str]:
    keys = []
    primary = os.environ.get("ANTHROPIC_API_KEY", "")
    if primary:
        keys.append(primary)
    for i in range(2, 10):
        k = os.environ.get(f"ANTHROPIC_API_KEY_{i}", "")
        if k:
            keys.append(k)
    return keys

_KEY_POOL: list[str] = _load_key_pool()
_key_index: int = 0  # 当前使用的 key 下标

# ── 输出语言控制 ──────────────────────────────────────────────────────────────
_OUTPUT_LANGUAGE: str = "zh"

_EN_INJECTION = (
    "\n\nCRITICAL: This character is a native English speaker. "
    "All \"content\" values in your JSON output MUST be written in natural English. "
    "Keep DES moment types unchanged. "
    "For compressed_speech: preserve the fragmentary, unfinished quality using em-dash (—). "
    "For unsymbolized: describe the wordless awareness in English. "
    "Do NOT mix Chinese and English in content fields."
)


def set_output_language(lang: str) -> None:
    """设置本次运行的 LLM 输出语言（'zh' 或 'en'）。在认知循环开始前调用一次。"""
    global _OUTPUT_LANGUAGE
    _OUTPUT_LANGUAGE = lang


def _get_client() -> anthropic.Anthropic:
    """返回当前 key 对应的 Anthropic 客户端。"""
    return anthropic.Anthropic(
        api_key=_KEY_POOL[_key_index],
        base_url=_BASE_URL,
        timeout=90.0,  # 单次请求最长 90 秒，防止挂死
    )


def _rotate_key(reason: str = "") -> bool:
    """
    切换到下一个 key。
    返回 True 表示切换成功，False 表示已轮转一圈无可用 key。
    """
    global _key_index
    next_index = (_key_index + 1) % len(_KEY_POOL)
    if next_index == 0 and _key_index != 0:
        return False  # 已经轮转一圈
    if next_index == _key_index:
        return False  # 只有一个 key
    _key_index = next_index
    print(f"[KeyRotation] 切换至 key #{_key_index + 1}（原因：{reason}）")
    return True


# 主客户端（供 arbiter streaming 直接使用，会在 camel_step 内部轮转）
_anthropic_client = _get_client()


def make_camel_agent(system_prompt: str, temperature: float = 0.7) -> Optional["ChatAgent"]:
    """创建一个 CAMEL ChatAgent。代理环境直接返回 None 走 Anthropic 直连。"""
    if not _CAMEL_AVAILABLE or _BASE_URL:
        return None
    try:
        model = ModelFactory.create(
            model_platform=ModelPlatformType.ANTHROPIC,
            model_type=ModelType.CLAUDE_OPUS_4_6,
            model_config_dict={"temperature": temperature, "max_tokens": 512},
        )
        return ChatAgent(
            system_message=system_prompt,
            model=model,
            message_window_size=20,
        )
    except Exception as e:
        print(f"[CAMEL] ChatAgent 创建失败，将使用 Anthropic 直连: {e}")
        return None


def camel_step(agent: Optional["ChatAgent"], prompt: str, system: str = "") -> str:
    """
    通过 CAMEL ChatAgent 执行一步推理，若失败回退到 Anthropic 直连（带 key 轮转重试）。
    system 参数在 agent=None 时作为 Anthropic 的 system prompt 使用，
    确保指令不因 agent 降级而丢失。
    """
    import time

    if agent is not None:
        try:
            user_msg = BaseMessage.make_user_message(
                role_name="System",
                meta_dict=None,
                content=prompt,
            )
            response = agent.step(user_msg)
            return response.msgs[0].content
        except Exception as e:
            print(f"[CAMEL] step 失败，回退 Anthropic: {e}")

    # 最多尝试 key 池大小次（每个 key 至多用一次）
    max_attempts = max(len(_KEY_POOL), 1)
    for attempt in range(max_attempts):
        try:
            client = _get_client()
            kwargs = dict(
                model=_DEFAULT_MODEL,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            if system:
                kwargs["system"] = system
            resp = client.messages.create(**kwargs)
            return resp.content[0].text.strip()
        except anthropic.AuthenticationError:
            # 401：当前 key 耗尽，尝试轮转
            if not _rotate_key("401 quota 耗尽"):
                raise  # 所有 key 都耗尽，真正抛出
        except Exception as e:
            if attempt < max_attempts - 1:
                time.sleep(2 ** min(attempt, 3))
            else:
                raise


def get_streaming_client() -> anthropic.Anthropic:
    """
    供 arbiter_layer_stream 使用的客户端，支持在 401 时手动轮转。
    调用方需要自行捕获 AuthenticationError 并调用 _rotate_key()。
    """
    return _get_client()


# ── 快速层 LLM（qwen3-max via DashScope）─────────────────────────────────────

_FAST_API_KEY  = os.environ.get("FAST_LLM_API_KEY", "")
_FAST_BASE_URL = os.environ.get("FAST_LLM_BASE_URL", "")
_FAST_MODEL    = os.environ.get("FAST_LLM_MODEL", "qwen3-max")

_fast_client = None

def _get_fast_client():
    global _fast_client
    if _fast_client is None:
        from openai import OpenAI
        _fast_client = OpenAI(api_key=_FAST_API_KEY, base_url=_FAST_BASE_URL)
    return _fast_client


def claude_call(prompt: str, system: str = "", max_tokens: int = 512) -> str:
    """
    直接使用 Claude Sonnet 进行推理（Reasoning / WorldEngine / Arbiter 层）。
    失败时 fallback 到 fast_call。
    """
    # 英文旁路：仅当显式设置 output_language="en" 时注入，不影响默认中文流程
    if _OUTPUT_LANGUAGE == "en":
        system = (system + _EN_INJECTION) if system else _EN_INJECTION.strip()

    import time
    max_attempts = max(len(_KEY_POOL), 1)
    for attempt in range(max_attempts):
        try:
            client = _get_client()
            kwargs: dict = dict(
                model=_DEFAULT_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            if system:
                kwargs["system"] = system
            resp = client.messages.create(**kwargs)
            return resp.content[0].text.strip()
        except anthropic.AuthenticationError:
            if not _rotate_key("401 quota 耗尽"):
                raise
        except Exception as e:
            if attempt < max_attempts - 1:
                time.sleep(2 ** min(attempt, 3))
            else:
                print(f"[ClaudeCall] 失败，fallback 到 fast_call: {e}")
                return fast_call(prompt, system=system, max_tokens=max_tokens)
    return fast_call(prompt, system=system, max_tokens=max_tokens)


def fast_call(prompt: str, system: str = "", max_tokens: int = 512) -> str:
    """
    快速层推理：使用 qwen3-max（DashScope OpenAI 兼容接口）。
    适用于 Perception / OCC / WorldEngine / Reasoning 等短文本任务。
    失败时 fallback 到 camel_step（Anthropic Sonnet）。
    """
    if not _FAST_API_KEY or not _FAST_BASE_URL:
        # 未配置快速层，直接走 Anthropic
        return camel_step(None, prompt, system=system)

    import time
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(3):
        try:
            client = _get_fast_client()
            resp = client.chat.completions.create(
                model=_FAST_MODEL,
                messages=messages,
                max_tokens=max_tokens,
                # qwen3 thinking mode 关闭（短任务不需要，节省 token）
                extra_body={"enable_thinking": False},
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                print(f"[FastLLM] 失败，fallback 到 Anthropic: {e}")
                return camel_step(None, prompt, system=system)
