"""
MemGrip - Entry Point
Basic chat loop with Ollama backend.
Memory layer will be integrated in Week 2-3.
"""

import ollama
import config


def build_messages(system_prompt: str, history: list, user_input: str) -> list:
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})
    return messages


def chat_loop():
    print(f"MemGrip ({config.MODEL_NAME}) — type 'exit' to quit\n")

    history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Exiting.")
            break

        messages = build_messages(config.SYSTEM_PROMPT, history, user_input)

        try:
            response = ollama.chat(
                model=config.MODEL_NAME,
                messages=messages,
                options={
                    "temperature": config.TEMPERATURE,
                    "num_predict": config.MAX_TOKENS,
                }
            )
            reply = response["message"]["content"]
        except Exception as e:
            print(f"[Error] {e}")
            continue

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": reply})

        print(f"MemGrip: {reply}\n")


if __name__ == "__main__":
    chat_loop()