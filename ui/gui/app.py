import flet as ft
from core.client import TeleClient
from ui.gui.screens.login import LoginScreen
from ui.gui.screens.download import DownloadScreen
from ui.gui.screens.upload import UploadScreen


async def main(page: ft.Page):
    page.title = "Tele Downloader Toolkit Pro"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1100
    page.window_height = 800

    # Biến lưu client hiện tại (sẽ được set sau khi login)
    app_state = {"client": None}

    # Hàm xây dựng giao diện chính
    def build_main_ui():
        if not app_state["client"]:
            return ft.Text("Lỗi: Chưa có Client")

        # Truyền client đã login vào các màn hình
        download_screen = DownloadScreen(page, app_state["client"])
        upload_screen = UploadScreen(page, app_state["client"])

        tabs_content = [
            download_screen.get_view(),
            upload_screen.get_view(),
            ft.Container(content=ft.Text("Cài đặt / Info", size=20))
        ]

        content_area = ft.Container(content=tabs_content[0], expand=True, padding=20)

        def change_tab(e):
            selected_idx = e.control.selected_index
            content_area.content = tabs_content[selected_idx]
            content_area.update()

        rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=100,
            min_extended_width=200,
            destinations=[
                ft.NavigationRailDestination(icon=ft.icons.DOWNLOAD, label="Download"),
                ft.NavigationRailDestination(icon=ft.icons.UPLOAD, label="Upload"),
                ft.NavigationRailDestination(icon=ft.icons.SETTINGS, label="Cài đặt"),
            ],
            on_change=change_tab,
        )

        async def logout_action(e):
            # CHỈ NGẮT KẾT NỐI, KHÔNG XÓA SESSION TRÊN SERVER
            if app_state["client"]:
                await app_state["client"].disconnect()
                app_state["client"] = None
            page.go("/login")

        return ft.View(
            route="/",
            controls=[
                ft.AppBar(
                    title=ft.Text("Tele Downloader Toolkit"),
                    actions=[ft.IconButton(ft.icons.LOGOUT, tooltip="Đổi tài khoản", on_click=logout_action)]
                ),
                ft.Row([rail, ft.VerticalDivider(width=1), content_area], expand=True)
            ]
        )

    # Callback khi login thành công từ LoginScreen
    def handle_login_success(active_client):
        app_state["client"] = active_client
        page.go("/")

    def route_change(route):
        page.views.clear()

        if page.route == "/login":
            # Truyền class TeleClient và hàm callback vào LoginScreen
            login_screen = LoginScreen(page, TeleClient, handle_login_success)
            page.views.append(login_screen.get_view())

        elif page.route == "/":
            if not app_state["client"]:
                page.go("/login")
                return
            page.views.append(build_main_ui())

        page.update()

    page.on_route_change = route_change
    page.go("/login")


if __name__ == "__main__":
    ft.app(target=main)