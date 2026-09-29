from enum import StrEnum


class AccessEnum(StrEnum):
    level: int

    def __new__(cls, value: str, level: int):
        obj = str.__new__(cls, value)

        obj._value_ = value
        obj.level = level

        return obj

    def __gt__(self, other):
        return self.level > other.level

    def __ge__(self, other):
        return self.level >= other.level

    def __lt__(self, other):
        return self.level < other.level

    def __le__(self, other):
        return self.level <= other.level
