class AppError(Exception):
    status_code: int = 500
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)


class MovieNotFoundError(AppError):
    status_code = 404
    detail = "Movie not found"


class MovieExistInOrderError(AppError):
    status_code = 409
    detail = "You cant buy movie again"


class MovieExistInCart(AppError):
    status_code = 409
    detail = "Movie already in cart"
