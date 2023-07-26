import re

import pyperclip
from rich.syntax import Syntax
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Header,
    Input,
    Label,
    LoadingIndicator,
    TextLog,
)

from frics.codeshare import CodeshareClient


class Frics(App):
    CSS_PATH = "frics.css"
    TITLE = "FЯICS"
    SUB_TITLE = "Frida Codeshare Explorer"

    def compose(self) -> ComposeResult:
        self.dark = True
        self._codeshare_client = CodeshareClient(self.log)

        yield Header()
        with Horizontal(name="root"):
            with Vertical(name="left", id="left_vert"):
                yield Input(placeholder="Search...", name="input_search", id="input_search")
                with Horizontal(name="update_container", id="update_container"):
                    yield Button(label="Update DB", name="btn_update_db", id="btn_update_db")
                    yield LoadingIndicator(name="loading", id="loading")
                yield DataTable(name="dt_db", id="dt_db")
                yield Label("Description", name="lbl_desc", id="lbl_desc")
                yield TextLog(name="text_desc", id="text_desc", wrap=True, highlight=True)
            with Vertical(name="right", id="right_vert"):
                yield Button(label="Copy to clipboard", name="btn_copy", id="btn_copy")
                yield TextLog(name="text_source", id="text_source", wrap=True, highlight=True)

    async def start_loading(self):
        """Start the loading indicator."""
        loading = self.query_one("#loading", LoadingIndicator)
        loading.styles.visibility = "visible"

    async def stop_loading(self):
        """Stop the loading indicator."""
        loading = self.query_one("#loading", LoadingIndicator)
        loading.styles.visibility = "hidden"

    @work(exclusive=True)
    @on(Button.Pressed, "#btn_update_db")
    async def update_db(self, message: Button.Pressed):
        """Update the database of codeshare snippets.

        Args:
            message (Button.Pressed): Button pressed message.
        """
        self.log("Updating database...")
        self.notify("Updating FЯICS database...")
        await self.start_loading()
        message.button.disabled = True

        await self._codeshare_client.update_db()
        self.notify("FЯICS database updated!")
        message.button.disabled = False
        await self.stop_loading()

        db_table = self.query_one(DataTable)
        db_table.clear()
        async for row in self._codeshare_client.query_all():
            db_table.add_row(*row)

    @on(Button.Pressed, "#btn_copy")
    def copy_to_clipboard(self, message: Button.Pressed):
        """Copy source code to the clipboard.

        Args:
            message (Button.Pressed): Button pressed message.
        """
        source_box = self.query_one("#text_source", TextLog)
        copy_string = ""

        # We need to copy the text without the line numbers
        for line in source_box.lines:
            code_line, *_ = line.text.rpartition(" ")
            code_line = code_line.partition("  ")[-1]

            code_match = re.match(r"\s*\d+\s(.*)", code_line)
            self.log(code_match)
            if code := code_match.group(1):  # type: ignore
                copy_string += code + "\n"
            else:
                copy_string += "\n"
        pyperclip.copy(copy_string)
        self.notify("Source code copied to clipboard!")

    @work(exclusive=True)
    @on(Input.Changed, "#input_search")
    async def search(self, message: Input.Changed):
        """Search the database.

        Args:
            message (Input.Changed): Input changed message.
        """
        search_term = message.input.value
        if not search_term:
            return

        db_table = self.query_one("#dt_db", DataTable)
        db_table.clear()

        async for row in self._codeshare_client.search(search_term):
            db_table.add_row(*row)

    @work(exclusive=True)
    @on(DataTable.RowSelected, "#dt_db")
    async def get_row_data(self, message: DataTable.RowSelected):
        """Get the row data.

        Args:
            message (DataTable.RowSelected): Row selected message.
        """
        project_id: str = message.data_table.get_row(message.row_key)[0]
        try:
            description, source = await self._codeshare_client.get_project(project_id)  # type: ignore
            desc_box = self.query_one("#text_desc", TextLog)
            source_box = self.query_one("#text_source", TextLog)

            desc_box.clear()
            desc_box.write(description)

            source_box.clear()
            source_box.write(
                Syntax(
                    source,
                    "js",
                    line_numbers=True,
                    word_wrap=True,
                    background_color="#090100",
                    theme="github-dark",
                ),
                scroll_end=False,
                expand=True,
                shrink=False,
            )

        except Exception as ex:
            self.log(f"Error getting project: {ex}")
            self.notify(f"Error getting project: {ex}")
            return

    async def on_mount(self):
        """Mount the app."""
        db_table = self.query_one("#dt_db", DataTable)
        db_table.cursor_type = "row"
        db_table.add_column("ID", width=0, key="project_id")
        db_table.add_column("Project Name", width=50, key="project_name")
        db_table.add_column("Author", width=15, key="author")
        db_table.add_column("Frida Version", key="frida_version")

        if not self._codeshare_client.db_exists():
            self.notify("FЯICS database not found. Please update the database.")
        else:
            async for row in self._codeshare_client.query_all():
                db_table.add_row(*row)


def run_app():
    """Run the app."""
    app = Frics()
    app.run()


if __name__ == "__main__":
    run_app()
