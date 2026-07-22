import queue


class DOMObserver:

    def __init__(self, page):

        self.page = page
        self.events = queue.Queue()



    def start(self):

        self.page.expose_function(
            "autonect_dom_event",
            self.handle_event
        )


        self.page.evaluate(
            """
            () => {

                const observer =
                    new MutationObserver(
                        (mutations) => {


                            for (const mutation of mutations) {


                                window.autonect_dom_event({

                                    type:
                                        mutation.type,

                                    target:
                                        mutation.target.className || "",

                                    text:
                                        mutation.target.innerText || ""

                                });

                            }

                        }
                    );


                observer.observe(
                    document.body,
                    {
                        childList: true,
                        subtree: true,
                        characterData: true
                    }
                );

            }
            """
        )


        print("[Observer] Started")



    def handle_event(self, event):

        self.events.put(
            event
        )



    def wait_for(self, keyword):

        while True:

            event = self.events.get()


            if keyword in str(event):

                return event