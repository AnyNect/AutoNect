from ai.provider import AIProvider
from browser.manager import BrowserManager
import time


class DeepSeekProvider(AIProvider):

    def __init__(self):
        self.browser = BrowserManager()
        self.page = None


    def connect(self):

        print("[DeepSeek] Connecting...")

        self.page = self.browser.launch()

        self.page.goto(
            "https://chat.deepseek.com"
        )

        self.page.wait_for_load_state(
            "networkidle"
        )

        print("[DeepSeek] Connected")


    def send_prompt(self, prompt):

        print("[DeepSeek] Injecting prompt...")


        result = self.page.evaluate(
            """
            (text) => {

                const textarea =
                    document.querySelector(
                        'textarea[placeholder="Message DSeek"]'
                    );


                if (!textarea) {
                    return false;
                }


                const setter =
                    Object.getOwnPropertyDescriptor(
                        HTMLTextAreaElement.prototype,
                        "value"
                    ).set;


                setter.call(
                    textarea,
                    text
                );


                textarea.dispatchEvent(
                    new Event(
                        "input",
                        {
                            bubbles: true
                        }
                    )
                );


                textarea.dispatchEvent(
                    new Event(
                        "change",
                        {
                            bubbles: true
                        }
                    )
                );


                return true;
            }
            """,
            prompt
        )


        if not result:
            raise Exception(
                "DeepSeek input not found"
            )


        print("[DeepSeek] Prompt injected")


        self.click_send()



    def click_send(self):

        print("[DeepSeek] Waiting for send button...")


        button = self.page.locator(
            'div[role="button"].ds-button--primary.ds-button--filled:not(.ds-button--disabled)'
        ).last


        button.wait_for(
            timeout=5000
        )


        button.click()


        print("[DeepSeek] Sent")



    def wait_for_response(self):

        print("[DeepSeek] Waiting for response...")


        timeout = 120
        start = time.time()


        while True:

            if time.time() - start > timeout:
                raise TimeoutError(
                    "DeepSeek response timeout"
                )


            answers = self.page.locator(
                ".ds-assistant-message-main-content"
            )


            thinking = self.page.locator(
                ".ds-think-content"
            )


            answer_count = answers.count()
            thinking_count = thinking.count()


            print(
                f"\r[DeepSeek] Answers: {answer_count} | Thinking: {thinking_count}",
                end=""
            )


            if answer_count > 0:

                send_button = self.page.locator(
                    'div[role="button"].ds-button--primary.ds-button--filled'
                ).last


                if send_button.count():

                    classes = send_button.get_attribute(
                        "class"
                    )


                    if classes and "ds-button--disabled" not in classes:

                        print(
                            "\n[DeepSeek] Response finished"
                        )

                        time.sleep(1)

                        return


            time.sleep(0.5)



    def get_response(self):

        self.wait_for_response()


        print(
            "[DeepSeek] Extracting response..."
        )


        thinking_text = ""

        thinking = self.page.locator(
            ".ds-think-content"
        )


        if thinking.count() > 0:

            thinking_text = (
                thinking.last
                .inner_text()
            )


        answer_text = ""

        answers = self.page.locator(
            ".ds-assistant-message-main-content"
        )


        if answers.count() > 0:

            answer_text = (
                answers.last
                .inner_text()
            )


        print(
            "[DeepSeek] Extraction complete"
        )


        return {
            "thinking": thinking_text,
            "answer": answer_text
        }



    def close(self):

        self.browser.close()