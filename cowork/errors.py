"""Lỗi nghiệp vụ có mã HTTP — route bắt và trả trang/JSON tương ứng."""
from __future__ import annotations


class CoworkError(Exception):
    status = 400
    code = "LOI"

    def __init__(self, message: str = "", *, code: str | None = None):
        super().__init__(message or self.__class__.__name__)
        self.message = message or "Đã xảy ra lỗi."
        if code:
            self.code = code


class AuthRequired(CoworkError):
    status = 401
    code = "CHUA_DANG_NHAP"


class Forbidden(CoworkError):
    status = 403
    code = "KHONG_DU_QUYEN"


class NotFound(CoworkError):
    status = 404
    code = "KHONG_TIM_THAY"


class ValidationError(CoworkError):
    status = 400
    code = "DU_LIEU_SAI"


class Conflict(CoworkError):
    status = 409
    code = "XUNG_DOT"
