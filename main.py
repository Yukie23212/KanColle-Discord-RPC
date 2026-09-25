# Copyright (c) 2026 harunoyukie
# Licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/)

import sys

from discord_rpc_manager.app import App


def main():
    web_mode = "--web" in sys.argv
    app = App()
    if web_mode:
        from discord_rpc_manager.web_ui import start_web_server
        app.withdraw()
        server, url = start_web_server(app)
        app.web_server = server
        app.web_server_url = url
    app.mainloop()


if __name__ == "__main__":
    main()
