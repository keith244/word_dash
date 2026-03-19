"""
Word Dash — WebSocket Race Condition & Latency Tester
======================================================
Simulates two players in a match to test:
  1. Race condition — both submit a word at nearly the same time
  2. Latency — how fast events propagate between players
  3. Turn enforcement — wrong player tries to pick a letter
  4. Invalid word rejection

SETUP:
  pip install websockets requests

USAGE:
  1. Make sure your Daphne server is running:
       daphne -p 8000 core.asgi:application

  2. Create two test users in your Django shell if you haven't:
       python manage.py shell
       from django.contrib.auth import get_user_model
       User = get_user_model()
       User.objects.create_user('testplayer1', 'p1@test.com', 'password123')
       User.objects.create_user('testplayer2', 'p2@test.com', 'password123')

  3. Run this script:
       python test_match.py

  4. Watch the output — each event is timestamped so you can see latency.
"""

import asyncio
import json
import time
import requests
import websockets
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"
WS_BASE  = "ws://127.0.0.1:8000"

# ── credentials ────────────────────────────────────────────────
PLAYER1 = {"username": "testplayer1", "password": "password123"}
PLAYER2 = {"username": "testplayer2", "password": "password123"}


# ── helpers ────────────────────────────────────────────────────

def log(player: str, msg: str):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    color = "\033[92m" if player == "P1" else "\033[94m"
    reset = "\033[0m"
    print(f"[{ts}] {color}{player}{reset}  {msg}")

def sys_log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] \033[93mSYS\033[0m {msg}")


def get_session(credentials: dict) -> requests.Session:
    """Log in via HTTP and return a session with cookies."""
    session = requests.Session()
    # Fetch login page first to get CSRF token
    r = session.get(f"{BASE_URL}/")
    csrf = session.cookies.get("csrftoken")
    r = session.post(f"{BASE_URL}/", data={
        "username_or_email": credentials["username"],
        "password": credentials["password"],
        "csrfmiddlewaretoken": csrf,
    }, headers={"Referer": f"{BASE_URL}/"})
    if r.url.rstrip("/") == BASE_URL.rstrip("/") or "login" in r.url:
        raise Exception(f"Login failed for {credentials['username']} — check credentials and LOGIN_URL below")
    sys_log(f"Logged in as {credentials['username']}")
    return session


def create_match(session: requests.Session, opponent_id: int) -> int:
    """Hit start_match to create a match and return match_id."""
    r = session.get(f"{BASE_URL}/word_dash/match/start/{opponent_id}/",
                    allow_redirects=True)
    # The redirect lands on /word_dash/match/<id>/
    match_id = int(r.url.rstrip("/").split("/")[-1])
    sys_log(f"Match created — id={match_id}")
    return match_id


def get_player_id(session: requests.Session, username: str) -> int:
    r = session.get(f"{BASE_URL}/word_dash/search/?q={username}")
    users = r.json().get("users", [])
    for u in users:
        if u["username"] == username:
            return u["id"]
    raise Exception(f"Could not find user {username} via search")


def cookies_to_ws_header(session: requests.Session) -> dict:
    """Convert requests session cookies into a format websockets can use."""
    cookie_str = "; ".join(
        f"{name}={value}" for name, value in session.cookies.items()
    )
    return {"Cookie": cookie_str}


# ── core test runner ───────────────────────────────────────────

async def player(
    name: str,
    match_id: int,
    headers: dict,
    actions: asyncio.Queue,
    events: asyncio.Queue,
):
    """
    Connects to the match WebSocket, processes incoming events,
    and sends actions from the queue.
    """
    uri = f"{WS_BASE}/ws/match/{match_id}/"
    connect_start = time.perf_counter()

    async with websockets.connect(uri, additional_headers=headers) as ws:
        connect_ms = (time.perf_counter() - connect_start) * 1000
        log(name, f"WebSocket connected in {connect_ms:.1f}ms")

        async def sender():
            while True:
                action = await actions.get()
                if action is None:
                    break
                await asyncio.sleep(action.get("delay", 0))
                payload = json.dumps(action["payload"])
                send_time = time.perf_counter()
                await ws.send(payload)
                log(name, f"SENT     {action['payload']['action']} — {action.get('note', '')}")
                action["_sent_at"] = send_time

        async def receiver():
            try:
                async for raw in ws:
                    recv_time = time.perf_counter()
                    data = json.loads(raw)
                    log(name, f"RECEIVED {data['type']}")
                    await events.put({
                        "player": name,
                        "data": data,
                        "recv_time": recv_time,
                    })
            except websockets.exceptions.ConnectionClosedOK:
                log(name, "connection closed cleanly")
            except websockets.exceptions.ConnectionClosedError as e:
                log(name, f"connection closed with error: {e}")

        await asyncio.gather(sender(), receiver())


async def run_test(test_name: str, p1_actions: list, p2_actions: list,
                   p1_headers: dict, p2_headers: dict, match_id: int):
    sys_log(f"{'─'*50}")
    sys_log(f"TEST: {test_name}")
    sys_log(f"{'─'*50}")

    q1 = asyncio.Queue()
    q2 = asyncio.Queue()
    events = asyncio.Queue()

    for a in p1_actions:
        await q1.put(a)
    await q1.put(None)  # sentinel

    for a in p2_actions:
        await q2.put(a)
    await q2.put(None)

    await asyncio.gather(
        player("P1", match_id, p1_headers, q1, events),
        player("P2", match_id, p2_headers, q2, events),
    )


# ── individual tests ───────────────────────────────────────────

async def test_normal_round(match_id, round_id, p1_headers, p2_headers,
                             first_picker: str):
    """P1 picks first letter, P2 picks second, then both race to submit."""
    sys_log(f"Round id={round_id} | first_picker={first_picker}")

    # Whoever goes first picks T, second picks E → T→E pattern
    if first_picker == "P1":
        p1_actions = [
            {"payload": {"action": "pick_letter", "letter": "T", "round_id": round_id},
             "note": "picks T"},
            {"payload": {"action": "submit_word", "word": "time", "round_id": round_id},
             "delay": 0.5, "note": "submits 'time'"},
        ]
        p2_actions = [
            {"payload": {"action": "pick_letter", "letter": "E", "round_id": round_id},
             "delay": 0.3, "note": "picks E"},
            {"payload": {"action": "submit_word", "word": "tide", "round_id": round_id},
             "delay": 0.6, "note": "submits 'tide'"},
        ]
    else:
        p1_actions = [
            {"payload": {"action": "pick_letter", "letter": "E", "round_id": round_id},
             "delay": 0.3, "note": "picks second letter E"},
            {"payload": {"action": "submit_word", "word": "time", "round_id": round_id},
             "delay": 0.6, "note": "submits 'time'"},
        ]
        p2_actions = [
            {"payload": {"action": "pick_letter", "letter": "T", "round_id": round_id},
             "note": "picks T"},
            {"payload": {"action": "submit_word", "word": "tide", "round_id": round_id},
             "delay": 0.5, "note": "submits 'tide'"},
        ]

    await run_test("Normal round", p1_actions, p2_actions,
                   p1_headers, p2_headers, match_id)


async def test_race_condition(match_id, round_id, p1_headers, p2_headers,
                               first_picker: str):
    sys_log(f"Race condition test — round_id={round_id}")
    sys_log("Both players will submit simultaneously after letters are picked.")

    if first_picker == "P1":
        p1_actions = [
            {"payload": {"action": "pick_letter", "letter": "S", "round_id": round_id},
             "note": "picks S (first)"},
            {"payload": {"action": "submit_word", "word": "snake", "round_id": round_id},
             "delay": 0.5, "note": "SIMULTANEOUS submit"},
        ]
        p2_actions = [
            {"payload": {"action": "pick_letter", "letter": "E", "round_id": round_id},
             "delay": 0.2, "note": "picks E (second)"},
            {"payload": {"action": "submit_word", "word": "sole", "round_id": round_id},
             "delay": 0.5, "note": "SIMULTANEOUS submit"},
        ]
    else:
        p1_actions = [
            {"payload": {"action": "pick_letter", "letter": "E", "round_id": round_id},
             "delay": 0.2, "note": "picks E (second)"},
            {"payload": {"action": "submit_word", "word": "snake", "round_id": round_id},
             "delay": 0.5, "note": "SIMULTANEOUS submit"},
        ]
        p2_actions = [
            {"payload": {"action": "pick_letter", "letter": "S", "round_id": round_id},
             "note": "picks S (first)"},
            {"payload": {"action": "submit_word", "word": "sole", "round_id": round_id},
             "delay": 0.5, "note": "SIMULTANEOUS submit"},
        ]

    await run_test("Race condition — simultaneous submit", p1_actions, p2_actions,
                   p1_headers, p2_headers, match_id)


async def test_turn_violation(match_id, round_id, p1_headers, p2_headers,
                               first_picker: str):
    """Wrong player tries to pick a letter — server should reject."""
    sys_log(f"Turn violation test — first_picker={first_picker}, wrong player will try to pick")

    # If P1 goes first, P2 tries to pick first (violation)
    if first_picker == "P1":
        p1_actions = [
            {"payload": {"action": "pick_letter", "letter": "M", "round_id": round_id},
             "delay": 0.3, "note": "correct turn"},
        ]
        p2_actions = [
            {"payload": {"action": "pick_letter", "letter": "X", "round_id": round_id},
             "note": "WRONG TURN — should be rejected"},
        ]
    else:
        p1_actions = [
            {"payload": {"action": "pick_letter", "letter": "X", "round_id": round_id},
             "note": "WRONG TURN — should be rejected"},
        ]
        p2_actions = [
            {"payload": {"action": "pick_letter", "letter": "M", "round_id": round_id},
             "delay": 0.3, "note": "correct turn"},
        ]

    await run_test("Turn violation", p1_actions, p2_actions,
                   p1_headers, p2_headers, match_id)


async def test_invalid_word(match_id, round_id, p1_headers, p2_headers,
                             first_picker: str):
    """P1 submits a word that doesn't match the pattern."""
    sys_log(f"Invalid word test — round_id={round_id}")

    if first_picker == "P1":
        p1_actions = [
            {"payload": {"action": "pick_letter", "letter": "B", "round_id": round_id},
             "note": "picks B"},
            {"payload": {"action": "submit_word", "word": "cat", "round_id": round_id},
             "delay": 0.5, "note": "submits 'cat' — INVALID for B→?"},
            {"payload": {"action": "submit_word", "word": "bone", "round_id": round_id},
             "delay": 0.8, "note": "submits 'bone' — valid"},
        ]
        p2_actions = [
            {"payload": {"action": "pick_letter", "letter": "E", "round_id": round_id},
             "delay": 0.2, "note": "picks E"},
        ]
    else:
        p1_actions = [
            {"payload": {"action": "pick_letter", "letter": "E", "round_id": round_id},
             "delay": 0.2, "note": "picks second letter"},
            {"payload": {"action": "submit_word", "word": "cat", "round_id": round_id},
             "delay": 0.5, "note": "submits 'cat' — INVALID for B→E"},
            {"payload": {"action": "submit_word", "word": "bone", "round_id": round_id},
             "delay": 0.8, "note": "submits 'bone' — valid"},
        ]
        p2_actions = [
            {"payload": {"action": "pick_letter", "letter": "B", "round_id": round_id},
             "note": "picks B"},
        ]

    await run_test("Invalid word then valid word", p1_actions, p2_actions,
                   p1_headers, p2_headers, match_id)


# ── main ───────────────────────────────────────────────────────

async def main():
    sys_log("Word Dash — WebSocket Test Suite")
    sys_log(f"Server: {BASE_URL}")
    print()

    # ── HTTP login ──
    try:
        p1_session = get_session(PLAYER1)
        p2_session = get_session(PLAYER2)
    except Exception as e:
        print(f"\n\033[91mERROR: {e}\033[0m")
        print("Make sure the server is running and test users exist.")
        return

    # ── Get player IDs ──
    p2_id = get_player_id(p1_session, PLAYER2["username"])
    sys_log(f"Player 2 id={p2_id}")

    # ── Create a match ──
    try:
        match_id = create_match(p1_session, p2_id)
    except Exception as e:
        print(f"\n\033[91mERROR creating match: {e}\033[0m")
        print("Check that start_match URL resolves and redirects to /word_dash/match/<id>/")
        return

    # ── Build WS headers from session cookies ──
    p1_headers = cookies_to_ws_header(p1_session)
    p2_headers = cookies_to_ws_header(p2_session)

    # ── Fetch current round info ──
    # ── Fetch current round info from state endpoint ──
    r = p1_session.get(f"{BASE_URL}/word_dash/match/{match_id}/state/")
    state = r.json()
    current_round = state.get('current_round')

    if not current_round:
        sys_log("ERROR: no active round found — match may already be complete")
        return

    round_id = current_round['id']
    p1_actual_id = get_player_id(p2_session, PLAYER1['username'])
    first_picker = "P1" if current_round['first_letter_picker_id'] == p1_actual_id else "P2"

    sys_log(f"Round id={round_id} | round_number={current_round['round_number']} | first_picker={first_picker}")
    print()

    # ── Run tests ──
    # Uncomment the test you want to run.
    # Run one at a time — each test consumes the current round.

    # --- Test 1: Normal round flow + latency ---
    # await test_normal_round(match_id, round_id, p1_headers, p2_headers, first_picker)

    # --- Test 2: Race condition (both submit simultaneously) ---
    await test_race_condition(match_id, round_id, p1_headers, p2_headers, first_picker)
    # --- Test 3: Turn violation ---
    # await test_turn_violation(match_id, round_id, p1_headers, p2_headers, first_picker)

    # --- Test 4: Invalid word then valid word ---
    # await test_invalid_word(match_id, round_id, p1_headers, p2_headers, first_picker)

    print()
    sys_log("Done.")


if __name__ == "__main__":
    asyncio.run(main())