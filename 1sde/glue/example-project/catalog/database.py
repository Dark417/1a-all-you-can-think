"""Glue Data Catalog *database* operations.

A database is a logical namespace that groups tables. It carries no data — only
a name, optional description, and parameters.
"""
from __future__ import annotations

from botocore.exceptions import ClientError

from catalog.client import glue_client


def create_database(name: str, description: str = "", client=None) -> None:
    """Create a database. Idempotent: a pre-existing database is treated as OK."""
    client = client or glue_client()
    try:
        client.create_database(
            DatabaseInput={"Name": name, "Description": description}
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "AlreadyExistsException":
            raise


def database_exists(name: str, client=None) -> bool:
    client = client or glue_client()
    try:
        client.get_database(Name=name)
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "EntityNotFoundException":
            return False
        raise


def list_databases(client=None) -> list[str]:
    """Return all database names, paginating through results."""
    client = client or glue_client()
    names: list[str] = []
    paginator = client.get_paginator("get_databases")
    for page in paginator.paginate():
        names.extend(db["Name"] for db in page["DatabaseList"])
    return names


def delete_database(name: str, client=None) -> None:
    """Delete a database (and its tables). Safe if it does not exist."""
    client = client or glue_client()
    try:
        client.delete_database(Name=name)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "EntityNotFoundException":
            raise
