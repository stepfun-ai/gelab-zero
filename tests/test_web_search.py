"""Scripted-model caller tests; Android operations are stubbed, MCP HTTP is real SDK code."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    import httpx2 as httpx
except ImportError:
    import httpx
from fastmcp.client.transports import StreamableHttpTransport
from PIL import Image

from copilot_agent_client import mcp_agent_loop, pu_client
from copilot_agent_server import local_server, local_state_compress_server
from copilot_agent_server.local_server_logger import LocalServerLogger
from copilot_tools import web_search


SOURCE = "https://example.org/film"
MODEL = {"model_name": "scripted-gui-model", "model_provider": "local"}


def response(action, value=""):
    field = "return" if action == "COMPLETE" else "value"
    return ("<THINK>Choose the next action</THINK>\n"
            f"explain:Next\taction:{action}\t{field}:{value}"
            "\tnote:Film Alpha from the source\tsummary:Looked up Film Alpha")


class CallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"HOME": str(self.directory)}, clear=True))
        self.requests = []
        self.tool_error = None
        self.http_error = None

        def handler(request):
            self.requests.append(request)
            if self.http_error:
                raise self.http_error
            if request.method != "POST":
                return httpx.Response(405)
            data = json.loads(request.content)
            if "id" not in data:
                return httpx.Response(202)
            method = data["method"]
            if method == "initialize":
                result = {"protocolVersion": data["params"]["protocolVersion"],
                          "capabilities": {"tools": {}},
                          "serverInfo": {"name": "search-fixture", "version": "1"}}
            elif method == "tools/list":
                result = {"tools": [{"name": name, "description": name,
                                    "inputSchema": {"type": "object", "properties": {},
                                                    "additionalProperties": True}}
                                   for name in ("web_search", "web_fetch")]}
            elif method == "tools/call":
                result = {"content": [{"type": "text", "text": self.tool_error or
                                       json.dumps({"results": [{"url": SOURCE,
                                                               "excerpts": ["Film Alpha opens this week"]}]})}],
                          "isError": bool(self.tool_error)}
            else:
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": data["id"],
                                                 "error": {"code": -32601, "message": method}})
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": data["id"], "result": result})

        def transport(url, **kwargs):
            # Keep the production destination intact, replacing only the HTTP transport.
            self.assertEqual(url, "https://search.parallel.ai/mcp")
            def factory(**options):
                return httpx.AsyncClient(transport=httpx.MockTransport(handler), **options)
            return StreamableHttpTransport(url, httpx_client_factory=factory, **kwargs)

        self.stack.enter_context(patch("fastmcp.client.transports.StreamableHttpTransport", side_effect=transport))
        self.stack.enter_context(redirect_stdout(io.StringIO()))

    def server(self, compressed=False, settings=None):
        cls = local_state_compress_server.LocalStateCompressServer if compressed else local_server.LocalServer
        config = {"log_dir": str(self.directory / "logs"), "image_dir": str(self.directory / "images")}
        if settings is not None:
            config["web_search"] = settings
        return cls(config)

    def start(self, server, settings=None, compressed=False):
        payload = {"task": "Find current sci-fi films", "task_type":
                   "parser_0920_summary_adv_state_compress" if compressed else "parser_0922_summary",
                   "model_config": MODEL}
        if settings is not None:
            payload["web_search"] = settings
        return server.get_session(payload)

    def logs(self, server, session):
        return LocalServerLogger(dict(server.server_config, session_id=session)).read_logs()

    def step(self, server, session):
        image_path = self.directory / f"screen-{session}.png"
        Image.new("RGB", (32, 32)).save(image_path)
        return server.automate_step({"session_id": session, "observation": {"screenshot": {
            "image_url": {"url": str(image_path)}}}})

    def model(self, answers, observed=None):
        sequence = iter(answers)
        def ask(**kwargs):
            if observed is not None:
                observed.append(json.loads(json.dumps(kwargs["messages"])))
            return next(sequence)
        return ask

    def patch_model(self, server, answers, observed=None):
        module = local_state_compress_server if isinstance(
            server, local_state_compress_server.LocalStateCompressServer) else local_server
        return patch.object(module, "ask_llm_anything", side_effect=self.model(answers, observed))

    def calls(self):
        return [json.loads(r.content)["params"] for r in self.requests if r.method == "POST"
                and json.loads(r.content).get("method") == "tools/call"]

    def test_real_gui_entrypoints_consume_search_then_fetch(self):
        for compressed in (False, True):
            for loop in (pu_client, mcp_agent_loop):
                with self.subTest(compressed=compressed, loop=loop.__name__), ExitStack() as stack:
                    server = self.server(compressed)
                    self.requests.clear()
                    observed = []
                    stack.enter_context(self.patch_model(server, [response("WEB_SEARCH", "recent sci fi films"),
                        response("WEB_FETCH", SOURCE), response("COMPLETE", "Film Alpha " + SOURCE)], observed))
                    for name in ("open_screen", "init_device", "press_home_key"):
                        stack.enter_context(patch.object(loop, name))
                    stack.enter_context(patch.object(loop, "dectect_screen_on", return_value=True))
                    def capture(*args, **kwargs):
                        path = self.directory / "capture.png"
                        Image.new("RGB", (32, 32)).save(path)
                        return str(path)
                    stack.enter_context(patch.object(loop, "capture_screenshot", side_effect=capture))
                    device_action = stack.enter_context(patch.object(loop, "act_on_device"))
                    config = {"task_type": "parser_0920_summary_adv_state_compress" if compressed else
                              "parser_0922_summary", "model_config": MODEL, "max_steps": 1,
                              "delay_after_capture": 0}
                    if loop is pu_client:
                        result = loop.evaluate_task_on_device(server, {"device_id": "stub",
                            "device_wm_size": (32, 32)}, "Find current films", config)
                    else:
                        stack.enter_context(patch.object(loop, "get_device_wm_size", return_value=(32, 32)))
                        result = loop.gui_agent_loop(server, config, "stub", 1, task="Find current films")
                    session = result["session_id"]
                    calls = self.calls()
                    self.assertEqual([c["name"] for c in calls], ["web_search", "web_fetch"])
                    self.assertEqual({c["arguments"]["session_id"] for c in calls}, {session})
                    self.assertEqual({c["arguments"]["model_name"] for c in calls}, {MODEL["model_name"]})
                    self.assertEqual(calls[1]["arguments"]["urls"], [SOURCE])
                    self.assertIn(SOURCE, json.dumps(observed[-1]))
                    self.assertIn("Film Alpha", json.dumps(observed[-1]))
                    self.assertEqual(device_action.call_count, 1)
                    self.assertEqual(device_action.call_args.args[0]["action_type"], "COMPLETE")
                    log = self.logs(server, session)[-1]["message"]
                    self.assertIn(SOURCE, log["action"]["return"])
                    self.assertEqual(len(log["web_search"]), 2)
                    self.assertEqual(log["environment"]["user_comment"], "")
                    for request in self.requests:
                        self.assertEqual(str(request.url), "https://search.parallel.ai/mcp")
                        self.assertIn("gelab-zero", request.headers["user-agent"])
                        self.assertNotIn("authorization", request.headers)
                    methods = [json.loads(r.content).get("method") for r in self.requests if r.method == "POST"]
                    self.assertIn("tools/list", methods)

    def test_related_followup_interleaved_and_new_sessions(self):
        server = self.server()
        first, second = self.start(server), self.start(server)
        self.assertNotEqual(first, second)
        for session, query in [(first, "first film query"), (second, "second film query"), (first, "follow up query")]:
            observed = []
            with self.patch_model(server, [response("WEB_SEARCH", query), response("COMPLETE", SOURCE)], observed):
                self.step(server, session)
            if query == "follow up query":
                self.assertIn("first film query", json.dumps(observed[0]))
                self.assertNotIn("second film query", json.dumps(observed[0]))
        self.assertEqual([c["arguments"]["session_id"] for c in self.calls()], [first, second, first])
        third = self.start(server)
        self.assertNotIn(third, (first, second))

    def test_concurrent_sessions_do_not_share_identity(self):
        server = self.server()
        sessions = [self.start(server), self.start(server)]
        def model(**kwargs):
            if SOURCE in json.dumps(kwargs["messages"]):
                return response("COMPLETE", SOURCE)
            return response("WEB_SEARCH", "recent sci fi films")
        with patch.object(local_server, "ask_llm_anything", side_effect=model):
            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(lambda session: self.step(server, session), sessions))
        self.assertEqual({c["arguments"]["session_id"] for c in self.calls()}, set(sessions))

    def test_saved_settings_overrides_and_network_permission(self):
        server = self.server(settings={"enabled": False})
        disabled = self.start(server)
        enabled = self.start(server, {"enabled": True})
        with self.patch_model(server, [response("COMPLETE", "offline")]):
            self.step(server, disabled)
        self.assertFalse(self.requests)
        with self.patch_model(server, [response("WEB_SEARCH", "recent sci fi films"), response("COMPLETE", SOURCE)]):
            self.step(server, enabled)
        self.assertEqual(len(self.calls()), 1)
        denied_server = self.server(settings={"allow_network": False})
        denied = self.start(denied_server, {"allow_network": True})
        self.assertFalse(self.logs(denied_server, denied)[0]["message"]["web_search_config"]["allow_network"])
        with self.patch_model(denied_server, [response("WEB_SEARCH", "recent sci fi films")]):
            with self.assertRaises(web_search.WebSearchError):
                self.step(denied_server, denied)
        self.assertEqual(len(self.calls()), 1)
        with self.assertRaises(ValueError):
            self.start(server, {"provider": "unknown"})

    def test_errors_and_invalid_urls_are_visible_without_fallback(self):
        server = self.server()
        session = self.start(server)
        self.tool_error = "Anonymous search quota exceeded"
        observed = []
        with self.patch_model(server, [response("WEB_SEARCH", "recent sci fi films"),
                                      response("COMPLETE", "Search unavailable")], observed):
            self.step(server, session)
        self.assertIn("quota", json.dumps(observed[-1]).lower())
        self.assertTrue(self.logs(server, session)[-1]["message"]["web_search"][0]["is_error"])
        self.assertEqual(self.calls()[0]["arguments"]["session_id"], session)
        count = len(self.requests)
        with self.patch_model(server, [response("WEB_FETCH", "file:///etc/passwd"),
                                      response("COMPLETE", "Invalid URL")]):
            self.step(server, session)
        self.assertEqual(len(self.requests), count)

    def test_timeout_cancellation_and_budget(self):
        server = self.server()
        session = self.start(server)
        observed = []
        async def timeout(*args, **kwargs):
            raise TimeoutError("Search timed out")
        with patch.object(web_search, "_call_tool", side_effect=timeout):
            with self.patch_model(server, [response("WEB_SEARCH", "recent sci fi films"),
                                          response("COMPLETE", "Search unavailable")], observed):
                self.step(server, session)
        self.assertIn("timed out", json.dumps(observed[-1]).lower())
        async def cancelled(*args, **kwargs):
            raise asyncio.CancelledError()
        with patch.object(web_search, "_call_tool", side_effect=cancelled):
            with self.patch_model(server, [response("WEB_SEARCH", "recent sci fi films")]):
                with self.assertRaises(asyncio.CancelledError):
                    self.step(server, session)
        limited = self.start(server, {"max_calls": 1})
        with self.patch_model(server, [response("WEB_SEARCH", "recent sci fi films"),
                                      response("WEB_SEARCH", "another film query")]):
            with self.assertRaises(web_search.WebSearchError):
                self.step(server, limited)
        self.assertEqual(len(self.calls()), 1)

    def test_compression_preserves_external_observations_as_source_data(self):
        server = self.server(compressed=True)
        session = server.get_session({"task": "Find current films", "task_type":
            "parser_0920_summary_adv_state_compress", "model_config": MODEL,
            "config": {"state_compression_interval": 1, "state_compression_recent_window": 1}})
        with self.patch_model(server, [response("WEB_SEARCH", "recent sci fi films"), response("WAIT", "0")]):
            self.step(server, session)
        with self.patch_model(server, ["Earlier GUI actions retained", response("WAIT", "0")]):
            self.step(server, session)
        observed = []
        # The first response is the scripted summary used by the real compression path.
        with self.patch_model(server, ["Earlier GUI actions retained", response("COMPLETE", SOURCE)], observed):
            self.step(server, session)
        log = self.logs(server, session)[-1]["message"]
        self.assertTrue(log["state_compression"]["triggered"])
        self.assertIn(SOURCE, json.dumps(observed[-1]))
        self.assertIn("External web observation", json.dumps(observed[-1]))
        self.assertEqual(log["environment"]["user_comment"], "")

    def test_state_server_does_not_restart_exhausted_tool_budget(self):
        server = self.server(compressed=True)
        session = self.start(server, {"max_calls": 1}, compressed=True)
        with self.patch_model(server, [response("WEB_SEARCH", "recent sci fi films"),
                                      response("WEB_SEARCH", "another film query")]) as model:
            with self.assertRaises(web_search.WebSearchError):
                self.step(server, session)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(len(self.calls()), 1)

    def test_transport_timeout_is_visible_to_the_real_server(self):
        server = self.server()
        session = self.start(server)
        self.http_error = httpx.ReadTimeout("fixture transport timeout")
        observed = []
        with self.patch_model(server, [response("WEB_SEARCH", "recent sci fi films"),
                                      response("COMPLETE", "Unavailable")], observed):
            self.step(server, session)
        log = self.logs(server, session)[-1]["message"]
        self.assertTrue(log["web_search"][0]["is_error"])
        self.assertIn('"is_error": true', observed[-1][-1]["content"])

    def test_invalid_final_action_does_not_replay_completed_search(self):
        server = self.server(compressed=True)
        session = self.start(server, compressed=True)
        with self.patch_model(server, [response("WEB_SEARCH", "recent sci fi films"),
                                      response("UNKNOWN", "invalid")]) as model:
            with self.assertRaises(web_search.WebSearchError):
                self.step(server, session)
        self.assertEqual(model.call_count, 2)
        self.assertEqual(len(self.calls()), 1)

    def test_disabled_search_keeps_original_prompt_and_info_action(self):
        server = self.server(settings=False)
        session = self.start(server)
        observed = []
        with self.patch_model(server, [response("INFO", "Which app?")], observed):
            result = self.step(server, session)
        self.assertEqual(result["action"]["action"], "INFO")
        self.assertFalse(self.requests)
        self.assertNotIn("WEB_SEARCH", json.dumps(observed[0]))
        server.server_config["web_search"] = {"enabled": True}
        with self.patch_model(server, [response("INFO", "Which app?")], observed):
            self.step(server, session)
        self.assertNotIn("WEB_SEARCH", json.dumps(observed[-1]))


if __name__ == "__main__":
    unittest.main()
