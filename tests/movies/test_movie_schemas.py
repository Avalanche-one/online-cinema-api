import pytest
from pydantic import ValidationError

from online_cinema_api.schemas.movie_comments import CommentCreateRequest
from online_cinema_api.schemas.movie_interactions import RatingRequest
from online_cinema_api.schemas.movies import (
    MovieCreateSchema,
    MovieQueryParams,
    MovieSortBy,
)
from online_cinema_api.services.movie_catalog import SORT_COLUMNS, _escape_like


def valid_movie(**overrides) -> dict:
    data = {
        "name": "Movie",
        "year": 2020,
        "time": 100,
        "imdb": 7.0,
        "votes": 10,
        "description": "Text",
        "price": "9.99",
        "certification_id": 1,
    }
    data.update(overrides)
    return data


def test_query_params_defaults_and_offset():
    params = MovieQueryParams()
    assert (params.page, params.per_page) == (1, 20)
    assert params.sort_by == MovieSortBy.POPULARITY
    assert MovieQueryParams(page=3, per_page=10).offset == 20


@pytest.mark.parametrize(
    "data",
    [
        {"year_from": 2020, "year_to": 2010},
        {"imdb_min": 9, "imdb_max": 5},
        {"price_min": 10, "price_max": 1},
        {"imdb_min": 11},
        {"page": 0},
        {"per_page": 101},
        {"sort_by": "unknown"},
    ],
)
def test_query_params_invalid(data):
    with pytest.raises(ValidationError):
        MovieQueryParams(**data)


def test_every_sort_option_has_a_column():
    assert set(SORT_COLUMNS) == set(MovieSortBy)


def test_escape_like():
    assert _escape_like("50%_a\\") == "50\\%\\_a\\\\"


def test_movie_create_accepts_valid_data():
    assert MovieCreateSchema(**valid_movie()).genre_ids == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"imdb": 11},
        {"imdb": -1},
        {"price": "-1"},
        {"price": "1.234"},
        {"year": 1800},
        {"time": 0},
        {"name": ""},
        {"meta_score": 101},
    ],
)
def test_movie_create_rejects_invalid_data(overrides):
    with pytest.raises(ValidationError):
        MovieCreateSchema(**valid_movie(**overrides))


@pytest.mark.parametrize("score", [1, 10])
def test_rating_accepts_bounds(score):
    assert RatingRequest(score=score).score == score


@pytest.mark.parametrize("score", [0, 11, -3])
def test_rating_rejects_out_of_range(score):
    with pytest.raises(ValidationError):
        RatingRequest(score=score)


def test_comment_text_is_stripped():
    assert CommentCreateRequest(text="  hi  ").text == "hi"


@pytest.mark.parametrize("text", ["", "   ", "x" * 2001])
def test_comment_text_rejects_invalid(text):
    with pytest.raises(ValidationError):
        CommentCreateRequest(text=text)
