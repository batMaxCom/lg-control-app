from __future__ import annotations

from collections.abc import Callable

import flet as ft

from theme import C, S, active_gradient, border, glass_gradient, shadow

ClickHandler = Callable[[ft.Event], None]


def ambient_background() -> ft.Control:
    return ft.Stack(
        expand=True,
        controls=[
            ft.Container(expand=True, bgcolor=C.BG),
            ft.Container(
                expand=True,
                gradient=ft.RadialGradient(
                    center=ft.Alignment.TOP_RIGHT,
                    radius=1.15,
                    colors=["#513B3F89", "#00101629"],
                    stops=[0.0, 1.0],
                ),
            ),
            ft.Container(
                expand=True,
                gradient=ft.RadialGradient(
                    center=ft.Alignment.CENTER_LEFT,
                    radius=1.05,
                    colors=["#45145B6F", "#000A1020"],
                    stops=[0.0, 1.0],
                ),
            ),
            ft.Container(
                expand=True,
                gradient=ft.RadialGradient(
                    center=ft.Alignment.BOTTOM_RIGHT,
                    radius=0.95,
                    colors=["#446F205E", "#00070B16"],
                    stops=[0.0, 1.0],
                ),
            ),
            ft.Container(
                expand=True,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_CENTER,
                    end=ft.Alignment.BOTTOM_CENTER,
                    colors=["#18040813", "#06070B16", "#2003070F"],
                ),
            ),
        ],
    )


def glass_panel(
    content: ft.Control,
    *,
    padding: int | ft.Padding = 16,
    radius: float = S.RADIUS,
    height: float | None = None,
    expand: bool | int | None = None,
    active: bool = False,
) -> ft.Container:
    return ft.Container(
        content=content,
        padding=padding,
        height=height,
        expand=expand,
        border_radius=radius,
        border=border(C.BORDER_ACTIVE if active else C.BORDER),
        gradient=active_gradient() if active else glass_gradient(),
        shadow=shadow(20, "34"),
    )


def icon_disc(
    icon: ft.IconData,
    *,
    size: int = 44,
    icon_size: int = 22,
    color: str = C.TEXT,
) -> ft.Container:
    return ft.Container(
        width=size,
        height=size,
        shape=ft.BoxShape.CIRCLE,
        alignment=ft.Alignment.CENTER,
        border=border(),
        bgcolor="#42161E31",
        shadow=shadow(12, "2C"),
        content=ft.Icon(icon, size=icon_size, color=color),
    )


def tab_item(
    label: str,
    icon: ft.IconData,
    active: bool,
    on_click: ClickHandler,
) -> ft.Container:
    return ft.Container(
        width=66,
        height=72,
        padding=ft.Padding(left=4, right=4, top=7, bottom=5),
        border_radius=18,
        border=border("#25FFFFFF" if active else "#00FFFFFF"),
        gradient=active_gradient() if active else None,
        ink=True,
        ink_color="#18FFFFFF",
        on_click=on_click,
        content=ft.Column(
            spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(icon, size=24, color=C.CYAN if active else C.TEXT_3),
                ft.Text(
                    label,
                    size=10,
                    max_lines=1,
                    text_align=ft.TextAlign.CENTER,
                    color=C.TEXT if active else C.TEXT_2,
                ),
                ft.Container(
                    width=28 if active else 0,
                    height=2,
                    border_radius=3,
                    bgcolor=C.CYAN if active else "#00000000",
                ),
            ],
        ),
    )


def bottom_nav_item(
    label: str,
    icon: ft.IconData,
    active: bool,
    on_click: ClickHandler,
) -> ft.Container:
    return ft.Container(
        expand=True,
        height=58,
        border_radius=18,
        gradient=active_gradient() if active else None,
        ink=True,
        ink_color="#14FFFFFF",
        on_click=on_click,
        content=ft.Column(
            spacing=3,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(icon, size=22, color=C.CYAN if active else C.TEXT_3),
                ft.Text(
                    label,
                    size=9,
                    max_lines=1,
                    text_align=ft.TextAlign.CENTER,
                    color=C.CYAN if active else C.TEXT_2,
                ),
            ],
        ),
    )


def pill_button(
    label: str,
    *,
    icon: ft.IconData | None = None,
    on_click: ClickHandler | None = None,
    height: int = S.ACTION_H,
    icon_color: str = C.TEXT,
    trailing: bool = False,
    active: bool = False,
    disabled: bool = False,
) -> ft.Container:
    controls: list[ft.Control] = []
    if icon is not None:
        controls.append(icon_disc(icon, size=40, icon_size=21, color=icon_color))
    controls.append(
        ft.Text(
            label,
            expand=True,
            size=14,
            weight=ft.FontWeight.W_500,
            color=C.TEXT_3 if disabled else C.TEXT,
            max_lines=2,
        )
    )
    if trailing:
        controls.append(ft.Icon(ft.Icons.CHEVRON_RIGHT, size=21, color=C.TEXT_3))

    return ft.Container(
        height=height,
        padding=ft.Padding(left=12, right=12, top=7, bottom=7),
        border_radius=height / 2,
        border=border(C.BORDER_ACTIVE if active else C.BORDER),
        gradient=active_gradient() if active else glass_gradient(),
        shadow=shadow(17, "30"),
        opacity=0.52 if disabled else 1.0,
        ink=not disabled,
        ink_color="#18FFFFFF",
        on_click=None if disabled else on_click,
        content=ft.Row(
            spacing=11,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=controls,
        ),
    )


def remote_circle(
    *,
    icon: ft.IconData | None = None,
    text: str | None = None,
    label: str | None = None,
    size: int = S.REMOTE_PRIMARY,
    color: str = C.TEXT,
    on_click: ClickHandler | None = None,
    active: bool = False,
) -> ft.Container:
    controls: list[ft.Control] = []
    if icon is not None:
        controls.append(ft.Icon(icon, size=30, color=color))
    if text:
        controls.append(ft.Text(text, size=20, color=C.TEXT, weight=ft.FontWeight.W_600))
    if label:
        controls.append(
            ft.Text(
                label,
                size=11,
                color=C.TEXT_2,
                text_align=ft.TextAlign.CENTER,
                max_lines=2,
            )
        )
    return ft.Container(
        width=size,
        height=size,
        shape=ft.BoxShape.CIRCLE,
        alignment=ft.Alignment.CENTER,
        border=border(C.BORDER_ACTIVE if active else "#42FFFFFF"),
        gradient=active_gradient() if active else glass_gradient(),
        shadow=shadow(22, "42"),
        ink=True,
        ink_color="#20FFFFFF",
        on_click=on_click,
        content=ft.Column(
            tight=True,
            spacing=3,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=controls,
        ),
    )


def status_pair(label: str, value: str, *, value_color: str = C.TEXT) -> ft.Row:
    return ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        controls=[
            ft.Text(label, size=12, color=C.TEXT_2),
            ft.Text(
                value,
                size=12,
                color=value_color,
                text_align=ft.TextAlign.RIGHT,
                weight=ft.FontWeight.W_500,
            ),
        ],
    )


def section_title(title: str, subtitle: str | None = None) -> ft.Column:
    controls: list[ft.Control] = [
        ft.Text(title, size=21, weight=ft.FontWeight.W_600, color=C.TEXT)
    ]
    if subtitle:
        controls.append(ft.Text(subtitle, size=11, color=C.TEXT_3))
    return ft.Column(spacing=3, controls=controls)


def color_key(color: str, dots: int, on_click: ClickHandler) -> ft.Container:
    return ft.Container(
        width=56,
        height=56,
        shape=ft.BoxShape.CIRCLE,
        alignment=ft.Alignment.CENTER,
        bgcolor=color,
        border=border("#4AFFFFFF"),
        shadow=shadow(16, "42"),
        ink=True,
        ink_color="#24FFFFFF",
        on_click=on_click,
        content=ft.Row(
            tight=True,
            spacing=3,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=5,
                    height=5,
                    shape=ft.BoxShape.CIRCLE,
                    bgcolor=C.TEXT,
                )
                for _ in range(dots)
            ],
        ),
    )
