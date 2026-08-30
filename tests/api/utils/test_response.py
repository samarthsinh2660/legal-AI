"""The response envelope, both directions."""

import json

from api.utils.errors import not_found, unauthorized
from api.utils.response import respond, success


def _body(response):
    return json.loads(response.body)


def test_a_success_carries_its_data():
    body = _body(success({"user_id": "abc"}))
    assert body == {"success": True, "data": {"user_id": "abc"}}


def test_a_success_defaults_to_200():
    assert success({"x": 1}).status_code == 200


def test_a_success_can_set_another_status():
    assert success({"x": 1}, status=201).status_code == 201


def test_a_failure_carries_its_code_and_message():
    body = _body(respond(unauthorized()))
    assert body["success"] is False
    assert body["error"]["code"] == "not_authenticated"
    assert body["error"]["message"]


def test_a_failure_uses_its_own_status():
    assert respond(not_found()).status_code == 404
    assert respond(unauthorized()).status_code == 401


def test_both_shapes_are_told_apart_by_one_field():
    """The reason for the envelope: a client checks `success` and knows
    which of the two shapes it has, on every endpoint."""
    assert _body(success(None))["success"] is True
    assert _body(respond(unauthorized()))["success"] is False


def test_a_failure_body_has_no_data_key():
    assert "data" not in _body(respond(unauthorized()))


def test_a_success_body_has_no_error_key():
    assert "error" not in _body(success({"x": 1}))


def test_data_may_be_absent():
    assert _body(success())["data"] is None
