from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NamedEntitySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class GenreSchema(NamedEntitySchema):
    pass


class StarSchema(NamedEntitySchema):
    pass


class DirectorSchema(NamedEntitySchema):
    pass


class CertificationSchema(NamedEntitySchema):
    pass


class GenreWithCountSchema(GenreSchema):
    movies_count: int


class NameCreateSchema(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]


class NameUpdateSchema(NameCreateSchema):
    pass


class MovieListItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: UUID
    name: str
    year: int
    time: int
    imdb: float
    votes: int
    price: Decimal
    genres: list[GenreSchema]


class MovieDetailSchema(MovieListItemSchema):
    meta_score: float | None
    gross: float | None
    description: str
    certification: CertificationSchema
    stars: list[StarSchema]
    directors: list[DirectorSchema]


YearField = Annotated[int, Field(ge=1888, le=2100)]
ImdbField = Annotated[float, Field(ge=0, le=10)]
PriceField = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]


class MovieCreateSchema(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=250)]
    year: YearField
    time: Annotated[int, Field(gt=0)]
    imdb: ImdbField
    votes: Annotated[int, Field(ge=0)]
    meta_score: Annotated[float | None, Field(ge=0, le=100)] = None
    gross: Annotated[float | None, Field(ge=0)] = None
    description: Annotated[str, Field(min_length=1)]
    price: PriceField
    certification_id: int
    genre_ids: list[int] = Field(default_factory=list)
    star_ids: list[int] = Field(default_factory=list)
    director_ids: list[int] = Field(default_factory=list)


class MovieUpdateSchema(BaseModel):
    name: Annotated[str | None, Field(min_length=1, max_length=250)] = None
    year: YearField | None = None
    time: Annotated[int | None, Field(gt=0)] = None
    imdb: ImdbField | None = None
    votes: Annotated[int | None, Field(ge=0)] = None
    meta_score: Annotated[float | None, Field(ge=0, le=100)] = None
    gross: Annotated[float | None, Field(ge=0)] = None
    description: Annotated[str | None, Field(min_length=1)] = None
    price: PriceField | None = None
    certification_id: int | None = None
    genre_ids: list[int] | None = None
    star_ids: list[int] | None = None
    director_ids: list[int] | None = None


class MovieSortBy(StrEnum):
    NAME = "name"
    YEAR = "year"
    IMDB = "imdb"
    PRICE = "price"
    POPULARITY = "popularity"  # у сервісі відповідає полю votes


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class MovieQueryParams(BaseModel):
    page: Annotated[int, Field(ge=1)] = 1
    per_page: Annotated[int, Field(ge=1, le=100)] = 20

    search: Annotated[str | None, Field(min_length=1, max_length=100)] = None

    year_from: YearField | None = None
    year_to: YearField | None = None
    imdb_min: ImdbField | None = None
    imdb_max: ImdbField | None = None
    price_min: Annotated[Decimal | None, Field(ge=0)] = None
    price_max: Annotated[Decimal | None, Field(ge=0)] = None

    genre_id: int | None = None
    certification_id: int | None = None
    star_id: int | None = None
    director_id: int | None = None

    sort_by: MovieSortBy = MovieSortBy.POPULARITY
    order: SortOrder = SortOrder.DESC

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @model_validator(mode="after")
    def check_ranges(self) -> MovieQueryParams:
        pairs = (
            ("year_from", "year_to", self.year_from, self.year_to),
            ("imdb_min", "imdb_max", self.imdb_min, self.imdb_max),
            ("price_min", "price_max", self.price_min, self.price_max),
        )
        for low_name, high_name, low, high in pairs:
            if low is not None and high is not None and low > high:
                raise ValueError(f"{low_name} must not be greater than {high_name}")
        return self


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int
