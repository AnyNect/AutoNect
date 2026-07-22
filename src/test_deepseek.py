from src.ai.providers.deepseek import DeepSeekProvider


def main():
    deepseek = DeepSeekProvider()

    try:
        deepseek.connect()

        # --- First prompt ---
        deepseek.send_prompt("What is AutoNect?")
        response1 = deepseek.get_response()

        print("\n===== RESPONSE 1 THINKING =====")
        print(response1["thinking"])
        print("\n===== RESPONSE 1 ANSWER =====")
        print(response1["answer"])

        # --- Second prompt ---
        deepseek.send_prompt("Explain how it works.")
        response2 = deepseek.get_response()

        print("\n===== RESPONSE 2 THINKING =====")
        print(response2["thinking"])
        print("\n===== RESPONSE 2 ANSWER =====")
        print(response2["answer"])

        input("\nPress Enter to close...")

    finally:
        deepseek.close()


if __name__ == "__main__":
    main()