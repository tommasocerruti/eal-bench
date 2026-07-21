"""How to call models with eal_bench.llm: single call, batch, and tool calling.

Run: `uv run python examples/llm_calls.py`  (needs a key for the `default` task's provider).
"""

import asyncio

from eal_bench.llm import LLM, run_tool_loop

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current temperature for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]


def get_weather(city: str) -> str:
    temps = {"Paris": "18C", "Tokyo": "24C"}
    return f"The temperature in {city} is {temps.get(city, '21C')}."


def main() -> None:
    llm = LLM()  # loads config.yaml + .env

    # 1) Single call. The task name selects provider + model + limits from config.yaml.
    resp = llm.complete("default", messages=[{"role": "user", "content": "Say hi in one word."}])
    print("single:", resp.choices[0].message.content.strip())

    # 2) Batch — run many at once in waves of batch_size (default 20), retried to
    #    completion. Results come back in input order. Pass a target to switch routes.
    msgs = [[{"role": "user", "content": f"Fun fact about {n}?"}] for n in range(1, 6)]
    for i, r in enumerate(llm.batch("default", msgs), 1):
        print(f"batch {i}:", r.choices[0].message.content.strip()[:60])

    # 3) Tool calling — pass `tools`, read `tool_calls` back. run_tool_loop drives the loop.
    final = asyncio.run(
        run_tool_loop(
            llm, "default",
            messages=[{"role": "user", "content": "What's the weather in Tokyo?"}],
            tools=TOOLS,
            handlers={"get_weather": get_weather},
        )
    )
    print("tools:", final[-1]["content"])
    print("\nAll calls logged to logs/calls.jsonl")


if __name__ == "__main__":
    main()
