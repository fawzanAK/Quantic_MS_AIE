"""Fixed environment for every test: reproducible 'today', isolated mock-ticket directory, no LLM key."""
import os
import tempfile

os.environ["APP_TODAY"] = "2026-10-01"
os.environ["RUNTIME_DIR"] = tempfile.mkdtemp(prefix="hr_rt_")
os.environ["LLM_API_KEY"] = ""
os.environ.pop("MCP_SERVER_URL", None)
