class TelemetryBus:
    def __init__(self):
        self.data = {}

    def push(self, key, value):
        self.data[key] = value

    def snapshot(self):
        return dict(self.data)
