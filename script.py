"""
charlie_test.py — sends the 5 benchmark questions to Charlie and prints results.
Run from inside your venv on the Charlie machine:
    python charlie_test.py
"""

import httpx
import json

BASE_URL  = "http://127.0.0.1:8000"
TIMEOUT   = 180  # seconds — give Charlie time to think

QUESTIONS = [
    "What is Surigao City's official vision statement?",
    "What are the 5 sectors in Surigao City's development plan and what is the overall goal of each one?",
    "What are the current gaps in Surigao City's health sector? I want to know about workforce shortages, immunization rates, and teen pregnancy.",
    "How does Mayor Dumlao's 8-point agenda align with the national priorities of the Marcos administration? Give me specific examples from each.",
    "Compare the vision-reality gaps across all five sectors. Which sector has the most critical gaps, and what specific programs has the city proposed to address them?",
]

DIVIDER = "═" * 80


def send_message(client: httpx.Client, message: str) -> str:
    resp = client.post(
        f"{BASE_URL}/api/chat/",
        json={"message": message},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "[no response field in reply]")


def main():
    print(DIVIDER)
    print("CHARLIE BENCHMARK — 5 TEST QUESTIONS")
    print(DIVIDER)

    # Use a session cookie so Charlie treats all messages as one conversation,
    # which also tests that conversation history doesn't bloat the prompt.
    with httpx.Client(base_url=BASE_URL) as client:
        # Touch the homepage once to get a session cookie
        client.get("/")

        for i, question in enumerate(QUESTIONS, start=1):
            print(f"\nQ{i}: {question}")
            print("─" * 60)

            try:
                answer = send_message(client, question)
                print(answer)
            except httpx.HTTPStatusError as e:
                print(f"[HTTP ERROR {e.response.status_code}]: {e.response.text}")
            except httpx.TimeoutException:
                print("[TIMEOUT] Charlie took too long to respond.")
            except Exception as e:
                print(f"[ERROR]: {e}")

            print()

    print(DIVIDER)
    print("TEST COMPLETE")
    print(DIVIDER)


if __name__ == "__main__":
    main()