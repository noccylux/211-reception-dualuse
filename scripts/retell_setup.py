"""Point the Retell agent at the voice bridge's current public URL and list its phone numbers.

    bash scripts/uv-run.sh python scripts/retell_setup.py https://<bridge-tunnel>.trycloudflare.com

Creates the agent on first use (then add the printed RETELL_AGENT_ID to .env) and
updates it afterwards. Quick-tunnel URLs change on every restart, so rerun it then.
This changes the Retell account; it never buys or binds phone numbers.
"""
import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retell import Retell  # noqa: E402

from dualuse.config import require  # noqa: E402

AGENT_NAME = "211 reception demo (hackathon)"


def endpoints(bridge_url: str, secret: str) -> tuple[str, str]:
    parts = urlsplit(bridge_url)
    if parts.scheme != "https" or not parts.netloc or parts.path.strip("/"):
        raise SystemExit(f"Expected the bridge origin as https://host, got {bridge_url!r}")
    return f"wss://{parts.netloc}/llm-websocket/{secret}", f"https://{parts.netloc}/retell-webhook"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bridge_url", help="public https origin of the voice bridge")
    parser.add_argument("--voice-id", default="11labs-Adrian", help="Retell voice for a newly created agent")
    args = parser.parse_args()

    websocket_url, webhook_url = endpoints(args.bridge_url, require("RETELL_WS_SECRET"))
    client = Retell(api_key=require("RETELL_API_KEY"))
    engine = {"type": "custom-llm", "llm_websocket_url": websocket_url}
    agent_id = os.environ.get("RETELL_AGENT_ID")
    if agent_id:
        client.agent.update(agent_id, response_engine=engine, webhook_url=webhook_url)
        print(f"Updated agent {agent_id}")
    else:
        agent_id = client.agent.create(response_engine=engine, voice_id=args.voice_id,
                                       agent_name=AGENT_NAME, webhook_url=webhook_url).agent_id
        print(f"Created agent {agent_id}. Add this line to .env:\nRETELL_AGENT_ID={agent_id}")
    print(f"LLM websocket: wss://{urlsplit(websocket_url).netloc}/llm-websocket/<RETELL_WS_SECRET>")
    print(f"Webhook:       {webhook_url}")

    numbers, key = [], None
    while True:
        page = client.phone_number.list(**({"pagination_key": key} if key else {}))
        numbers += page.items
        if not page.has_more:
            break
        key = page.pagination_key
    bound = [(number, agent) for number in numbers
             for agent in number.inbound_agents or [] if agent.agent_id == agent_id]
    for number, agent in bound:
        print(f"Inbound number {number.phone_number_pretty or number.phone_number} -> agent version {agent.agent_version or 'default'}")
    if not bound:
        print("No phone number sends inbound calls to this agent. Bind one in the Retell dashboard, "
              "or use the dashboard's test call for this agent.")


if __name__ == "__main__":
    main()
