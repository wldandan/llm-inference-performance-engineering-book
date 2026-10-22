"""3.2 的那 30 个 token 到底由什么组成。

第 1 章那次请求只发了一句话，服务端报的 `prompt_tokens` 却是 30。多出来的部分
来自 Chat Template：它在 messages 外面套了控制标记，有的模型还会在没有 system
消息时自动插一句默认系统提示。两者占的 token 数差别很大，而正文需要说清是哪一种。

这个脚本不猜，它把模板渲染出来，再按同一张词表切一遍，给出逐段的 token 数。

两条路，任选其一：

    # 一、服务已经起着（第 1.2 节那条命令），走它的 /tokenize
    python3 code/ch03/chat_template_probe.py --base-url http://127.0.0.1:8000/v1

    # 二、本机装了 transformers，直接读模型自己的 tokenizer_config.json
    python3 code/ch03/chat_template_probe.py --local

输出是一份 JSON，`--output` 写文件。要看的是三件事：

    rendered            模板渲染出来的完整文本，控制标记都在里面
    has_default_system  模板有没有在没给 system 时自己插一句
    segments            每一段各占几个 token，加起来等于 prompt_tokens

只依赖标准库；`--local` 那条路需要 transformers，没装会直接说清楚，不会半路报错。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_PROMPT = "请用三句话介绍 LLM 在线推理。"


class ProbeError(RuntimeError):
    pass


def _post(url: str, payload: dict[str, Any], api_key: str,
          timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProbeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except Exception as exc:
        raise ProbeError(f"{url} 请求失败：{exc}") from exc


def probe_via_server(base_url: str, model: str, prompt: str, api_key: str,
                     timeout: float) -> dict[str, Any]:
    """走 vLLM 的 /tokenize：带 messages 时它会先套模板再切词。"""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    url = f"{root}/tokenize"

    with_template = _post(url, {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "add_generation_prompt": True,
        "return_token_strs": True,
    }, api_key, timeout)
    bare = _post(url, {"model": model, "prompt": prompt,
                       "add_special_tokens": False,
                       "return_token_strs": True}, api_key, timeout)
    token_strs = with_template.get("token_strs")
    return {
        "source": "server",
        "endpoint": url,
        "prompt_tokens_with_template": with_template.get("count"),
        "prompt_tokens_bare": bare.get("count"),
        "token_strs": token_strs,
        "rendered": "".join(token_strs) if isinstance(token_strs, list) else None,
    }


def probe_via_transformers(model: str, prompt: str) -> dict[str, Any]:
    try:
        from transformers import AutoTokenizer  # noqa: PLC0415
    except ImportError as exc:
        raise ProbeError(
            "--local 需要 transformers：pip install transformers，"
            "或者去掉 --local 走已经起着的服务"
        ) from exc
    tok = AutoTokenizer.from_pretrained(model)
    rendered = tok.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False, add_generation_prompt=True)
    with_template = tok(rendered, add_special_tokens=False)["input_ids"]
    bare = tok(prompt, add_special_tokens=False)["input_ids"]
    return {
        "source": "transformers",
        "tokenizer_vocab_size": len(tok),
        "prompt_tokens_with_template": len(with_template),
        "prompt_tokens_bare": len(bare),
        "token_strs": tok.convert_ids_to_tokens(with_template),
        "rendered": rendered,
    }


DEFAULT_SYSTEM_MARKERS = ("You are Qwen", "You are a helpful assistant",
                          "You are ChatGLM", "你是")


def analyse(raw: dict[str, Any], prompt: str) -> dict[str, Any]:
    """把渲染结果拆成三段：模板脚手架、默认系统提示、用户这句话。"""
    total = raw.get("prompt_tokens_with_template")
    bare = raw.get("prompt_tokens_bare")
    rendered = raw.get("rendered") or ""
    has_default_system = any(m in rendered for m in DEFAULT_SYSTEM_MARKERS
                             if m not in prompt)
    overhead = None if (total is None or bare is None) else total - bare
    report = dict(raw)
    report.update({
        "prompt": prompt,
        "has_default_system": has_default_system,
        "template_overhead_tokens": overhead,
        "segments": {
            "用户这句话": bare,
            "模板加进去的（控制标记 + 可能的默认系统提示）": overhead,
        },
        "reading": _reading(total, bare, overhead, has_default_system),
    })
    return report


def _reading(total, bare, overhead, has_default_system) -> str:
    if total is None or bare is None:
        return "没拿到计数，先确认服务起着、模型名对得上"
    if has_default_system:
        return (f"模板在没有 system 消息时插了一句默认系统提示，所以 {total} 里有 "
                f"{overhead} 个不是你发的字。3.2 不能把这部分全归给控制标记")
    return (f"模板没有插默认系统提示，{total} 减去 {bare} 剩下的 {overhead} 个"
            f"就是控制标记本身")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--local", action="store_true",
                        help="不走服务，直接用 transformers 读模型的 tokenizer")
    parser.add_argument("--output", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raw = (probe_via_transformers(args.model, args.prompt) if args.local
               else probe_via_server(args.base_url, args.model, args.prompt,
                                     args.api_key, args.timeout))
    except ProbeError as exc:
        print(exc, file=sys.stderr)
        return 1
    report = analyse(raw, args.prompt)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
