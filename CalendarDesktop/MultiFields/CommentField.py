from typing import Tuple

from .BaseField import BaseField


class CommentField(BaseField):
    type_name = "COMMENT"

    @staticmethod
    def perform_type_check(value) -> Tuple[bool, int]:
        return True, 1
