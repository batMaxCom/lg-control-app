from __future__ import annotations

import flet as ft


class C:
    BG = "#070B16"
    BG_ALT = "#0B1020"
    SURFACE = "#2A182136"
    SURFACE_STRONG = "#52192236"
    SURFACE_SOFT = "#1E172033"

    TEXT = "#F5F7FB"
    TEXT_2 = "#BAC2D1"
    TEXT_3 = "#778196"

    CYAN = "#68D8FF"
    BLUE = "#77A8FF"
    VIOLET = "#A46FFF"
    MAGENTA = "#D85CBD"
    GREEN = "#39D6A2"
    RED = "#F05B6A"
    YELLOW = "#DFB74D"

    BORDER = "#29FFFFFF"
    BORDER_ACTIVE = "#667BCBFF"
    DIVIDER = "#18FFFFFF"
    SHADOW = "#5C000000"

    KEY_RED = "#CB3845"
    KEY_GREEN = "#35AD88"
    KEY_YELLOW = "#CDA63C"
    KEY_BLUE = "#4E8ED2"


class S:
    PAGE_X = 16
    HEADER_H = 56
    TABS_H = 82
    BOTTOM_H = 76

    RADIUS = 24
    RADIUS_SMALL = 17
    ACTION_H = 62
    ACTION_H_SMALL = 54

    REMOTE_PRIMARY = 78
    REMOTE_SECONDARY = 66
    D_PAD = 262
    OK = 78


def border(color: str = C.BORDER, width: float = 1) -> ft.Border:
    return ft.Border.all(width, color)


def shadow(blur: float = 22, opacity_hex: str = "48") -> list[ft.BoxShadow]:
    return [
        ft.BoxShadow(
            blur_radius=blur,
            spread_radius=0,
            color=f"#{opacity_hex}000000",
            offset=ft.Offset(0, 6),
        )
    ]


def glass_gradient() -> ft.LinearGradient:
    return ft.LinearGradient(
        begin=ft.Alignment.TOP_LEFT,
        end=ft.Alignment.BOTTOM_RIGHT,
        colors=["#4A222B44", "#2D111827", "#45162439"],
        stops=[0.0, 0.56, 1.0],
    )


def active_gradient() -> ft.LinearGradient:
    return ft.LinearGradient(
        begin=ft.Alignment.TOP_LEFT,
        end=ft.Alignment.BOTTOM_RIGHT,
        colors=["#64372F5E", "#451B2948", "#54173558"],
        stops=[0.0, 0.55, 1.0],
    )
