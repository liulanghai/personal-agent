"""One shared runtime for web, SDK and future desktop clients."""
import asyncio
import json
import os
import httpx
from .store import uid, now
from .tools import DEFINITIONS
from .context import ContextBuilder


class Runtime:
    def __init__(self, store, tools, settings):
        self.store, self.tools, self.settings = store, tools, settings
        self.tasks = {}
        self.context = ContextBuilder(tools)

    def launch(self, run_id):
        task = asyncio.create_task(self.execute(run_id))
        self.tasks[run_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(run_id, None))

    async def call(self, run_id, name, args):
        call_id = uid("call")
        self.store.event(run_id, "tool_call.started", {"tool_call_id": call_id, "tool_name": name, "arguments": args})
        await asyncio.sleep(0)
        try:
            result = self.tools.execute(name, args, run_id)
            data = {"tool_call_id": call_id, "tool_name": name, "status": "succeeded", "result": result}
        except Exception as exc:
            result = {"error": str(exc)[:500]}
            data = {"tool_call_id": call_id, "tool_name": name, "status": "failed", "result": result}
        self.store.event(run_id, "tool_call.completed", data)
        return result

    async def text(self, run_id, content):
        for i in range(0, len(content), 32):
            self.store.event(run_id, "message.delta", {"delta": content[i:i + 32]})
            await asyncio.sleep(0.015)

    async def model(self, run, files):
        config = self.settings()
        if not config.get("api_key") or not config.get("model"):
            raise ValueError("请先在设置中配置模型名称和 API 密钥")
        history = self.store.rows("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY rowid", (run["conversation_id"],))
        messages, manifest = self.context.build(config, run, files, history)
        self.store.event(run["id"], "context.built", manifest)
        final = []
        async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
            for _ in range(min(int(os.getenv("AGENT_MAX_STEPS", "16")), 32)):
                calls = {}
                content = ""
                async with client.stream("POST", config["base_url"].rstrip("/") + "/chat/completions", headers={"Authorization": "Bearer " + config["api_key"]}, json={"model": config["model"], "messages": messages, "tools": DEFINITIONS, "stream": True}) as response:
                    if response.status_code >= 400:
                        # Do not persist provider response bodies: they may contain credentials.
                        raise ValueError("模型服务返回 HTTP " + str(response.status_code) + "，请检查设置、模型权限或额度")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        chunk = json.loads(payload)
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        if delta.get("content"):
                            text = delta["content"]
                            content += text
                            self.store.event(run["id"], "message.delta", {"delta": text})
                        for tc in delta.get("tool_calls", []):
                            current = calls.setdefault(tc["index"], {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            if tc.get("id"):
                                current["id"] = tc["id"]
                            for key in ("name", "arguments"):
                                current["function"][key] += tc.get("function", {}).get(key, "")
                if content:
                    final.append(content)
                if not calls:
                    if not content:
                        raise ValueError("模型没有返回可显示的内容")
                    return "\n\n".join(final)
                ordered = [calls[k] for k in sorted(calls)]
                messages.append({"role": "assistant", "content": content or None, "tool_calls": ordered})
                for call in ordered:
                    try:
                        arguments = json.loads(call["function"]["arguments"])
                        result = await self.call(run["id"], call["function"]["name"], arguments)
                    except (ValueError, TypeError):
                        result = {"error": "Invalid tool arguments: expected JSON object"}
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)})
            raise ValueError("已达到最大工具执行步数")

    async def execute(self, run_id):
        run = self.store.one("SELECT * FROM runs WHERE id=?", (run_id,))
        self.store.status(run_id, "running")
        self.store.event(run_id, "run.started", {})
        try:
            files = []
            for file_id in json.loads(run["file_ids"]):
                files.append(self.store.one("SELECT * FROM files WHERE id=?", (file_id,)))
            output = await self.model(run, files)
            self.store.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)", (uid("msg"), run["conversation_id"], "assistant", output, run_id, now()))
            self.store.status(run_id, "completed")
            self.store.event(run_id, "run.completed", {})
        except asyncio.CancelledError:
            self.store.status(run_id, "cancelled")
            self.store.event(run_id, "run.cancelled", {})
        except Exception as exc:
            error = str(exc)[:500] if isinstance(exc, ValueError) else "执行失败（" + type(exc).__name__ + "），请检查模型连接或本地文件"
            self.store.status(run_id, "failed", error)
            self.store.event(run_id, "run.failed", {"error": error})
