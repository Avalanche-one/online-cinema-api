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


class MovieNotInCartError(AppError):
    status_code = 404
    detail = "Movie not found in cart"


class UserAlreadyExistsError(AppError):
    status_code = 409
    detail = "A user with this email already exists."


class UserGroupNotFoundError(AppError):
    status_code = 500
    detail = "Default user group not found."


class InvalidActivationTokenError(AppError):
    status_code = 400
    detail = "Invalid or expired activation token."


class AccountAlreadyActiveError(AppError):
    status_code = 400
    detail = "User account is already active."


class InvalidCredentialsError(AppError):
    status_code = 401
    detail = "Invalid email or password."


class AccountNotActivatedError(AppError):
    status_code = 403
    detail = "User account is not activated."


class RefreshTokenNotFoundError(AppError):
    status_code = 401
    detail = "Refresh token not found."


class UserNotFoundError(AppError):
    status_code = 404
    detail = "User not found."


class PermissionForReadUserCartError(AppError):
    status_code = 403
    detail = "Not enough permissions"
