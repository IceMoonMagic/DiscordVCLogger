import inspect
from typing import Any, Callable, Coroutine

import discord

import database as db


class ToggleButton(discord.ui.Button):
    TRUE_EMOJI = "✅"  # ✔
    FALSE_EMOJI = "❎"  # ✖

    def __init__(
        self,
        starting_value: bool,
        *,
        label: str = None,
        disabled: bool = False,
        custom_id: str = None,
        row: int = None,
    ):
        super().__init__(
            label=label, disabled=disabled, custom_id=custom_id, row=row
        )
        self._value = None
        self.value = starting_value

    @property
    def value(self) -> bool:
        return self._value

    @value.setter
    def value(self, value: bool) -> None:
        self._value = value
        self.emoji = self.TRUE_EMOJI if value else self.FALSE_EMOJI

    def toggle(self) -> None:
        self.value = not self.value

    async def callback(self, interaction: discord.Interaction):
        self.toggle()
        await interaction.response.edit_message(view=self.view)


class DBToggleButton(ToggleButton):
    def __init__(
        self,
        attribute: str,
        data: db.S = None,
        *,
        label: str = "",
        disabled: bool = False,
        custom_id: str = None,
        row: int = None,
    ):
        self.attribute = attribute
        self.data = data
        super().__init__(
            starting_value=self._value,
            label=label,
            disabled=disabled,
            custom_id=custom_id,
            row=row,
        )

    @property
    def _value(self) -> bool:
        return self.data.__getattribute__(self.attribute)

    @_value.setter
    def _value(self, value: bool) -> None:
        self.data.__setattr__(self.attribute, value)


class DBSelect(discord.ui.Select):
    def __init__(
        self,
        options: list[db.S],
        label_key: Callable[[db.S], str] = None,
        desc_key: Callable[[db.S], str] = lambda _: None,
        emoji_key: Callable[[db.S], str] = lambda _: None,
        default_index: int = None,
        *,
        custom_id: str = None,
        placeholder: str = None,
        min_values: int = 1,
        max_values: int = 1,
        disabled: bool = False,
        row: int = None,
    ):
        super().__init__(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            row=row,
        )
        self.data_options = options
        if label_key is None:
            label_key = self.default_label
        for i, option in enumerate(options):
            self.add_option(
                label=label_key(option),
                value=str(i),
                description=desc_key(option),
                emoji=emoji_key(option),
                default=default_index == i,
            )

    @property
    def values(self) -> list[db.S]:
        return [self.data_options[int(i)] for i in super().values]

    @property
    def value(self) -> db.S | None:
        if self.min_values != 1 or self.max_values != 1:
            raise ValueError(
                "min_values and max_values must be 1 to get single value."
            )
        if len(values := self.values) == 0:
            return None
        return values[0]

    @staticmethod
    def default_label(data: db.S) -> str:
        return str(data.__getattribute__(data.primary_key_name))


def db_select(
    label_key: Callable[[db.S], str] = None,
    desc_key: Callable[[db.S], str] = lambda _: None,
    emoji_key: Callable[[db.S], str] = lambda _: None,
    default_index: int = None,
    *,
    custom_id: str = None,
    placeholder: str = None,
    min_values: int = 1,
    max_values: int = 1,
    disabled: bool = False,
    row: int = None,
):
    def decorator(func):
        # From `discord.ui.select`
        if not inspect.iscoroutinefunction(func):
            raise TypeError("select function must be a coroutine function")
        # ---

        func.__discord_ui_model_type__ = DBSelect
        func.__discord_ui_model_kwargs__ = {
            "label_key": label_key,
            "desc_key": desc_key,
            "emoji_key": emoji_key,
            "default_index": default_index,
            "custom_id": custom_id,
            "placeholder": placeholder,
            "min_values": min_values,
            "max_values": max_values,
            "disabled": disabled,
            "row": row,
        }
        return func

    return decorator


class DBSelector(discord.ui.View):
    def __init__(
        self,
        options: list[db.S],
        followup: Callable[
            [db.S, discord.Interaction], Coroutine[Any, Any, None]
        ],
        label_key: Callable[[db.S], str] = None,
        desc_key: Callable[[db.S], str] = lambda _: None,
        emoji_key: Callable[[db.S], str] = lambda _: None,
        *,
        custom_id: str = None,
        placeholder: str = None,
        disabled: bool = False,
        row: int = None,
        timeout: float = 180.0,
        disable_on_timeout: bool = False,
    ):
        # self.select.__discord_ui_model_type__ = DBSelect
        self.select.__discord_ui_model_kwargs__.update(
            {
                "options": options,
                "label_key": label_key,
                "desc_key": desc_key,
                "emoji_key": emoji_key,
                "custom_id": custom_id,
                "placeholder": placeholder,
                "disabled": disabled,
                "row": row,
            }
        )
        super().__init__(
            timeout=timeout, disable_on_timeout=disable_on_timeout
        )
        self.followup = followup

    @db_select()
    async def select(self, select: DBSelect, interaction: discord.Interaction):
        await self.followup(select.value, interaction)


def disable_on_call(
    element: discord.ui.Button | discord.ui.Select, send_edit: bool = True
):
    async def new_callback(interaction: discord.Interaction):
        await old_callback(interaction)
        element.disabled = True
        if send_edit:
            await interaction.response.edit_message(view=element.view)

    old_callback, element.callback = element.callback, new_callback
