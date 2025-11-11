from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from localization import localization
from user_config import Language

def get_language_keyboard(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="English 🇬🇧", callback_data="setEnglish")],
            [InlineKeyboardButton(text="Українська 🇺🇦", callback_data="setUkrainian")]
        ]
    )

def get_config_menu(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=localization.get_text(language, "display_my_splits"), callback_data="displaySplits")],
            [InlineKeyboardButton(text=localization.get_text(language, "language_button"), callback_data="OpenLanguageMenu")],
            [InlineKeyboardButton(text=localization.get_text(language, "start_tracking_button"), callback_data="start_tracking")],
        ]
    )

def get_config_menu_active(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=localization.get_text(language, "stop_tracking_button"), callback_data="stop_tracking")],
        ]
    )

def get_splits_menu(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=localization.get_text(language, "split_names.Second Structure"), callback_data="fortSplit")],
            [InlineKeyboardButton(text=localization.get_text(language, "split_names.Blind"), callback_data="blindSplit")],
            [InlineKeyboardButton(text=localization.get_text(language, "split_names.Eye Spy"), callback_data="strongholdSplit")],
            [InlineKeyboardButton(text=localization.get_text(language, "split_names.End Enter"), callback_data="endSplit")],
            [InlineKeyboardButton(text=localization.get_text(language, "back_to_config"), callback_data="to_config")],
        ]
    )

def get_fort_menu(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=localization.get_text(language, "dont_track"), callback_data="fort_0")],
            [
                InlineKeyboardButton(text="Sub 3:00", callback_data="fort_180"),
                InlineKeyboardButton(text="Sub 3:30", callback_data="fort_210"),
                InlineKeyboardButton(text="Sub 4:00", callback_data="fort_240")
            ],
            [
                InlineKeyboardButton(text="Sub 4:30", callback_data="fort_270"),
                InlineKeyboardButton(text="Sub 5:00", callback_data="fort_300"),
                InlineKeyboardButton(text="Sub 5:30", callback_data="fort_330")
            ],
        ]
    )

def get_blind_menu(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=localization.get_text(language, "dont_track"), callback_data="blind_0")],
            [
                InlineKeyboardButton(text="Sub 4:00", callback_data="blind_240"),
                InlineKeyboardButton(text="Sub 4:30", callback_data="blind_270"),
                InlineKeyboardButton(text="Sub 5:00", callback_data="blind_300"),
            ],
            [
                InlineKeyboardButton(text="Sub 5:30", callback_data="blind_330"),
                InlineKeyboardButton(text="Sub 6:00", callback_data="blind_360"),
                InlineKeyboardButton(text="Sub 6:30", callback_data="blind_390"),
            ],
            [InlineKeyboardButton(text="Sub 7:00", callback_data="blind_420")],
        ]
    )

def get_strong_menu(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=localization.get_text(language, "dont_track"), callback_data="strong_0")],
            [
                InlineKeyboardButton(text="Sub 5:30", callback_data="strong_330"),
                InlineKeyboardButton(text="Sub 5:45", callback_data="strong_345"),
                InlineKeyboardButton(text="Sub 6:00", callback_data="strong_360"),
            ],
            [
                InlineKeyboardButton(text="Sub 7:30", callback_data="strong_450"),
                InlineKeyboardButton(text="Sub 6:30", callback_data="strong_390"),
                InlineKeyboardButton(text="Sub 7:00", callback_data="strong_420")
            ],
            [
                InlineKeyboardButton(text="Sub 8:00", callback_data="strong_480"),
                InlineKeyboardButton(text="Sub 8:30", callback_data="strong_510"),
                InlineKeyboardButton(text="Sub 9:00", callback_data="strong_540")
            ],
        ]
    )

def get_end_menu(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=localization.get_text(language, "dont_track"), callback_data="end_0")],
            [
                InlineKeyboardButton(text="Sub 6:00", callback_data="end_360"),
                InlineKeyboardButton(text="Sub 6:30", callback_data="end_390"),
                InlineKeyboardButton(text="Sub 7:00", callback_data="end_420")
            ],
            [
                InlineKeyboardButton(text="Sub 7:30", callback_data="end_450"),
                InlineKeyboardButton(text="Sub 8:00", callback_data="end_480"),
                InlineKeyboardButton(text="Sub 8:30", callback_data="end_510")
            ],
            [
                InlineKeyboardButton(text="Sub 9:00", callback_data="end_540"),
                InlineKeyboardButton(text="Sub 9:30", callback_data="end_570"),
                InlineKeyboardButton(text="Sub 10:00", callback_data="end_600")
            ],
        ]
    )

def get_display_splits_menu(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=localization.get_text(language, "configure_splits"), callback_data="openSplitsMenu")],
            [InlineKeyboardButton(text=localization.get_text(language, "back_to_config"), callback_data="to_config")],
        ]
    )

def get_language_set_menu(language: Language) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=localization.get_text(language, "to_configuration_menu"), callback_data="to_config")]
        ]
    )

# Keep static keyboards that don't need localization
user_not_found_menu = InlineKeyboardMarkup(inline_keyboard=[])