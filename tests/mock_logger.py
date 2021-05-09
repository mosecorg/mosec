class MockLogger:
    @staticmethod
    def info(content):
        print(f"\nMockLogger: info - {content}")

    @staticmethod
    def debug(content):
        print(f"\nMockLogger: debug - {content}")

    def warn(self, content):
        self.warning(content)

    @staticmethod
    def warning(content):
        print(f"\nMockLogger: warning - {content}")

    @staticmethod
    def error(content):
        print(f"\nMockLogger: error - {content}")
        raise RuntimeError(content)
