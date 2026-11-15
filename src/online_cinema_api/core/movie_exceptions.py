from online_cinema_api.core.exceptions import AppError


class MovieAlreadyExistsError(AppError):
    status_code = 409
    detail = "A movie with the same name, year and duration already exists"


class MovieHasOrdersError(AppError):
    status_code = 409
    detail = "This movie is part of existing orders and cannot be deleted"


class RelatedEntitiesNotFoundError(AppError):
    status_code = 422
    detail = "Certification, genre, star or director with the given id not found"


class EntityNotFoundError(AppError):
    status_code = 404
    detail = "Entity not found"


class NameAlreadyExistsError(AppError):
    status_code = 409
    detail = "An entity with this name already exists"


class MovieAlreadyInFavoritesError(AppError):
    status_code = 409
    detail = "Movie is already in favorites"


class MovieNotInFavoritesError(AppError):
    status_code = 404
    detail = "Movie not found in favorites"


class CommentNotFoundError(AppError):
    status_code = 404
    detail = "Comment not found"


class CommentForbiddenError(AppError):
    status_code = 403
    detail = "You can delete only your own comments"


class NotificationNotFoundError(AppError):
    status_code = 404
    detail = "Notification not found"
