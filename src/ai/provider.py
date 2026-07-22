from abc import ABC, abstractmethod


class AIProvider(ABC):

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def send_prompt(self, prompt):
        pass

    @abstractmethod
    def get_response(self):
        pass