class VisibilityControl:
    __instance__ = None

    @classmethod
    def get(cls):
        if cls.__instance__ is None:
            cls.__instance__ = cls()
        return cls.__instance__

    def __init__(self):
        self.items = {}

    def ShouldBeVisible(self, item: int):
        return self.items.get(item, True)

    def SetVisibility(self, item: int, visible: bool) -> bool:
        self.items[item] = visible
        return visible

    def ToggleVisibility(self, item: int) -> bool:
        return self.SetVisibility(item, not self.ShouldBeVisible(item))
