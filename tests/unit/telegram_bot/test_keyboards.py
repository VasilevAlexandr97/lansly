import pytest

from lansly.apps.telegram_bot.keyboards import (
    PresetPriceFilterCB,
    _format_price_preset,
    build_start_set_price_filter_kbd,
)
from lansly.preferences.consts import PRICE_FILTER_PRESETS


@pytest.mark.parametrize(
    ("min_price", "max_price", "expected"),
    [
        (0, 1_000, "0-1 000₽"),
        (1_000, 5_000, "1 000-5 000₽"),
        (5_000, 15_000, "5 000-15 000₽"),
        (15_000, 30_000, "15 000-30 000₽"),
        (30_000, 100_000, "30 000-100 000₽"),
        (100_000, 1_000_000, "100 000-1 000 000₽"),
        (1_000_000, 10_000_000, "1 000 000-10 000 000₽"),
    ],
)
def test_format_price_preset(min_price, max_price, expected):
    assert _format_price_preset(min_price, max_price) == expected


def test_build_start_set_price_filter_kbd_has_preset_buttons():
    kbd = build_start_set_price_filter_kbd()
    # Количество рядов = len(PRICE_FILTER_PRESETS) + 1 (Кнопка "Отмена")
    assert len(kbd.inline_keyboard) == len(PRICE_FILTER_PRESETS) + 1


def test_build_start_set_price_filter_kbd_callback_data():
    kbd = build_start_set_price_filter_kbd()
    preset_rows = kbd.inline_keyboard[:-1]
    for row, (min_p, max_p) in zip(
        preset_rows,
        PRICE_FILTER_PRESETS,
        strict=True,
    ):
        assert len(row) == 1
        btn = row[0]
        assert (
            btn.callback_data
            == PresetPriceFilterCB(
                min_price=min_p,
                max_price=max_p,
            ).pack()
        )


def test_build_start_set_price_filter_kbd_cancel_button():
    kbd = build_start_set_price_filter_kbd()
    cancel_row = kbd.inline_keyboard[-1]
    assert cancel_row[0].callback_data == "cancel_set_price_filter"


def test_preset_price_filter_cb_roundtrip():
    cb = PresetPriceFilterCB(min_price=5_000, max_price=15_000)
    packed = cb.pack()
    unpacked = PresetPriceFilterCB.unpack(packed)
    assert unpacked.min_price == 5_000
    assert unpacked.max_price == 15_000
