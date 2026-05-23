from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GameStatus(StrEnum):
    LOBBY = "lobby"
    RUNNING = "running"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class GamePhase(StrEnum):
    LOBBY = "lobby"
    NIGHT = "night"
    DAY = "day"
    VOTING = "voting"
    FINISHED = "finished"


class PlayerStatus(StrEnum):
    ALIVE = "alive"
    DEAD = "dead"
    LEFT = "left"


class ActionStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255))

    players: Mapped[list["GamePlayer"]] = relationship(back_populates="user")


class Chat(Base, TimestampMixin):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))

    games: Mapped[list["Game"]] = relationship(back_populates="chat")


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    team: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    night_action: Mapped[str | None] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_unique: Mapped[bool] = mapped_column(default=False)
    min_players: Mapped[int] = mapped_column(Integer, default=0)
    image_file_id: Mapped[str | None] = mapped_column(String(255))
    image_path: Mapped[str | None] = mapped_column(String(255))
    ability_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    players: Mapped[list["GamePlayer"]] = relationship(back_populates="role")
    preset_roles: Mapped[list["RolePresetRole"]] = relationship(back_populates="role")


class RolePreset(Base, TimestampMixin):
    __tablename__ = "role_presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    min_players: Mapped[int] = mapped_column(Integer, default=4)
    max_players: Mapped[int | None] = mapped_column(Integer)

    roles: Mapped[list["RolePresetRole"]] = relationship(
        back_populates="preset",
        cascade="all, delete-orphan",
    )


class RolePresetRole(Base):
    __tablename__ = "role_preset_roles"
    __table_args__ = (UniqueConstraint("preset_id", "role_id", name="uq_preset_role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    preset_id: Mapped[int] = mapped_column(ForeignKey("role_presets.id", ondelete="CASCADE"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    count: Mapped[int] = mapped_column(Integer, default=1)

    preset: Mapped[RolePreset] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="preset_roles")


class Game(Base, TimestampMixin):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[GameStatus] = mapped_column(SAEnum(GameStatus), default=GameStatus.LOBBY)
    phase: Mapped[GamePhase] = mapped_column(SAEnum(GamePhase), default=GamePhase.LOBBY)
    day_number: Mapped[int] = mapped_column(Integer, default=0)
    preset_code: Mapped[str] = mapped_column(String(64), default="classic")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    winner_team: Mapped[str | None] = mapped_column(String(64))

    chat: Mapped[Chat] = relationship(back_populates="games")
    players: Mapped[list["GamePlayer"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )


class GamePlayer(Base, TimestampMixin):
    __tablename__ = "game_players"
    __table_args__ = (UniqueConstraint("game_id", "user_id", name="uq_game_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    status: Mapped[PlayerStatus] = mapped_column(SAEnum(PlayerStatus), default=PlayerStatus.ALIVE)
    is_owner: Mapped[bool] = mapped_column(default=False)

    game: Mapped[Game] = relationship(back_populates="players")
    user: Mapped[User] = relationship(back_populates="players")
    role: Mapped[Role | None] = relationship(back_populates="players")
    actions: Mapped[list["GameAction"]] = relationship(
        foreign_keys="GameAction.actor_player_id",
        back_populates="actor",
    )
    votes: Mapped[list["Vote"]] = relationship(
        foreign_keys="Vote.voter_player_id",
        back_populates="voter",
    )


class GameAction(Base, TimestampMixin):
    __tablename__ = "game_actions"
    __table_args__ = (
        UniqueConstraint("game_id", "actor_player_id", "day_number", name="uq_night_action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    actor_player_id: Mapped[int] = mapped_column(
        ForeignKey("game_players.id", ondelete="CASCADE"),
        index=True,
    )
    target_player_id: Mapped[int] = mapped_column(
        ForeignKey("game_players.id", ondelete="CASCADE"),
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(64))
    day_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[ActionStatus] = mapped_column(SAEnum(ActionStatus), default=ActionStatus.PENDING)

    actor: Mapped[GamePlayer] = relationship(
        foreign_keys=[actor_player_id],
        back_populates="actions",
    )
    target: Mapped[GamePlayer] = relationship(foreign_keys=[target_player_id])


class Vote(Base, TimestampMixin):
    __tablename__ = "votes"
    __table_args__ = (
        UniqueConstraint("game_id", "voter_player_id", "day_number", name="uq_day_vote"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    voter_player_id: Mapped[int] = mapped_column(
        ForeignKey("game_players.id", ondelete="CASCADE"),
        index=True,
    )
    target_player_id: Mapped[int] = mapped_column(
        ForeignKey("game_players.id", ondelete="CASCADE"),
        index=True,
    )
    day_number: Mapped[int] = mapped_column(Integer)

    voter: Mapped[GamePlayer] = relationship(
        foreign_keys=[voter_player_id],
        back_populates="votes",
    )
    target: Mapped[GamePlayer] = relationship(foreign_keys=[target_player_id])
