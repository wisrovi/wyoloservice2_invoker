class LlmAnalizer:
    NAME = "LLM Post-Analysis"
    VERSION = "1.0.0"

    def __init__(self, config):
        self.config = config

    def __call__(self, data):
        return data
