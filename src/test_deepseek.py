from ai.providers.deepseek import DeepSeekProvider


def main():

    deepseek = DeepSeekProvider()

    try:

        deepseek.connect()

        deepseek.send_prompt(
            "Explain AutoNect in one sentence."
        )


        response = deepseek.get_response()


        print("\n===== THINKING =====")
        print(response["thinking"])


        print("\n===== ANSWER =====")
        print(response["answer"])


        input(
            "\nPress Enter to close..."
        )


    finally:

        deepseek.close()



if __name__ == "__main__":
    main()