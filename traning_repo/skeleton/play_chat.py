#!/usr/bin/env python3
"""面对面玩：你出拳，网关（背后是 DeepSeek，或本地兜底）出拳，当场判胜负。

前面几个脚本都是「模型 vs 本地机器人」，这个脚本把**对手换成你自己**：
它照样走真实的消息协议（每轮构造一行 ``{"time": ..., "history": [...]}`` 请求，
交给 :meth:`gateway.app.JsonGateway.handle_line`，拿回一行决策），
所以你看到的每一手都是网关流水线的真实输出，不是脚本自己编的。

用法::

    # 1) 不花钱，马上就能玩（没有 API Key 时会自动切到这个模式）
    python play_chat.py --offline

    # 2) 对着本地假上游玩（能看到网关怎么接住各种坏回复）
    python mock_llm_server.py --port 8801 &
    python play_chat.py --api-base-url http://127.0.0.1:8801 --api-key test

    # 3) 真实 DeepSeek（要花钱，但对手是真正的模型）
    export DEEPSEEK_API_KEY=sk-xxx
    python play_chat.py --rounds 10

输入支持 ``rock`` / ``scissor`` / ``paper``，也支持 ``石头`` / ``剪刀`` / ``布``
（大小写、复数、前后空格都认，走的就是 :func:`gateway.rules.normalize_option`）。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from typing import Any, Dict, List, Optional

from gateway.app import JsonGateway
from gateway.config import GatewayConfig
from gateway.rules import OPTIONS, judge, normalize_option, now_iso

#: 三个取值的中文说法，纯粹为了打印好看
OPTION_TEXT = {"rock": "石头", "scissor": "剪刀", "paper": "布"}

PROMPT = "你出拳（rock/scissor/paper 或 石头/剪刀/布；回车=随机；q=退出）："

QUIT_WORDS = {"q", "quit", "exit", "退出", "不玩了"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="和网关面对面玩石头剪刀布")
    parser.add_argument("--rounds", type=int, default=0, help="最多玩几轮，默认 0 = 一直玩到你自己退出")
    parser.add_argument("--offline", action="store_true", help="不调用 API，只用本地兜底出拳")
    parser.add_argument("--api-base-url", default=None, help="上游 API 地址")
    parser.add_argument("--api-key", default=None, help="API Key（默认读环境变量 DEEPSEEK_API_KEY）")
    parser.add_argument("--model", default=None, help="模型名")
    parser.add_argument("--quiet", action="store_true", help="不打印网关日志，只看对局")
    return parser


def ask_move(prompt: str) -> Optional[str]:
    """读一手出拳；返回三个选项之一、``None`` 表示这一手跳过、``"__quit__"`` 表示退出。"""
    try:
        raw = input(prompt)
    except (EOFError, KeyboardInterrupt):  # 管道读完 / Ctrl-C 都当成退出
        print()
        return "__quit__"

    text = raw.strip()
    if text.lower() in QUIT_WORDS:
        return "__quit__"
    if not text:
        return random.choice(OPTIONS)  # 懒得打字就随机给你一手
    return normalize_option(text)  # 未知取值返回 None，由调用方提示重输


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    config = GatewayConfig().with_overrides(
        api_base_url=args.api_base_url, api_key=args.api_key, model=args.model
    )
    if not args.offline and not config.resolved_api_key():
        # 没有 key 时别让用户一头撞在 401 上，直接降级成离线兜底
        print("（没有检测到 %s，自动切到离线兜底模式）" % config.api_key_env)
        args.offline = True
    if args.offline:
        config = config.with_overrides(offline=True)

    gateway = JsonGateway(config, log=(lambda _message: None) if args.quiet else None)
    mode = "离线兜底，本地规则出拳" if config.offline else "模型 %s" % config.model

    print("石头剪刀布：你 vs 网关（%s）" % mode)
    print("规则：石头赢剪刀，剪刀赢布，布赢石头。历史出拳会作为 history 传给网关。\n")

    #: 对手（= 你）的历史出拳：网关每轮拿到的 history 就是它
    history: List[str] = []
    wins = draws = losses = 0
    played = 0

    while True:
        if args.rounds and played >= args.rounds:
            print("\n（已经玩满 %d 轮）" % args.rounds)
            break

        move = ask_move(PROMPT)
        if move == "__quit__":
            break
        if move is None:
            print("  看不懂这个出拳，只能输入 rock/scissor/paper 或 石头/剪刀/布。\n")
            continue

        # 走真实协议：一行请求进，一行决策出
        request: Dict[str, Any] = {"time": now_iso(), "history": history[-10:]}
        decision, notes = gateway.handle_line(json.dumps(request, ensure_ascii=False))
        gateway_move = decision["option"]

        history.append(move)  # 你的历史，就是下一轮的 history
        outcome = judge(gateway_move, move)  # 1 = 网关赢，-1 = 你赢，0 = 平
        if outcome > 0:
            losses += 1
            verdict = "我赢了"
        elif outcome < 0:
            wins += 1
            verdict = "你赢了"
        else:
            draws += 1
            verdict = "平局"
        played += 1

        detail = ("    [%s]" % "; ".join(notes)) if notes else ""
        print(
            "第 %2d 轮  你=%s  我=%s  ->  %s%s"
            % (played, OPTION_TEXT[move], OPTION_TEXT[gateway_move], verdict, detail)
        )

    print("\n共 %d 轮：你赢 %d / 平 %d / 我赢 %d" % (played, wins, draws, losses))
    if played:
        print("比分（你 : 我）= %d : %d" % (wins, losses))

    client = getattr(gateway, "client", None)
    if client is not None and hasattr(client, "close"):
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
