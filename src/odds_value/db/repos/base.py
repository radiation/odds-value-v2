from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from odds_value.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def add(self, obj: ModelT, *, flush: bool = True) -> ModelT:
        self.session.add(obj)
        if flush:
            self.session.flush()  # assigns PKs, etc.
        return obj

    def get(self, id_: Any) -> ModelT | None:
        return self.session.get(self.model, id_)

    def first_where(self, *predicates: ColumnElement[bool]) -> ModelT | None:
        stmt = select(self.model).where(*predicates).limit(1)
        return self.session.execute(stmt).scalars().first()

    def one_where(self, *predicates: ColumnElement[bool]) -> ModelT:
        stmt = select(self.model).where(*predicates)
        return self.session.execute(stmt).scalars().one()

    def list(self, *, offset: int = 0, limit: int = 100) -> list[ModelT]:
        stmt = select(self.model).offset(offset).limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def delete(self, obj: ModelT, *, flush: bool = True) -> None:
        self.session.delete(obj)
        if flush:
            self.session.flush()

    def patch(self, obj: ModelT, changes: Mapping[str, Any], *, flush: bool = True) -> ModelT:
        for k, v in changes.items():
            if v is None:
                continue
            setattr(obj, k, v)
        if flush:
            self.session.flush()
        return obj

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
