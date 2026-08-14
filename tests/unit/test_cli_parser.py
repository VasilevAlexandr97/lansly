import pytest

from lansly.main.cli import build_parser


def test_create_admin_parses_flags():
    args = build_parser().parse_args(
        ["create-admin", "--username", "admin", "--password", "secret123"],
    )
    assert args.command == "create-admin"
    assert args.username == "admin"
    assert args.password == "secret123"


def test_create_admin_requires_flags():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["create-admin"])


def test_unknown_command_rejected():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["nope"])
