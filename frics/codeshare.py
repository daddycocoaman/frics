from ast import literal_eval
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import aiosqlite
import bs4
import httpx
from platformdirs import user_data_dir
from textual import Logger


class CodeshareClient:
    def __init__(self, logger: Logger) -> None:
        self._data_dir = Path(user_data_dir("frics", "frics", ensure_exists=True))
        self._db_path = self._data_dir / "codeshare.db"
        self._log = logger

    def db_exists(self) -> bool:
        """Check if the database exists."""
        return self._db_path.exists()

    async def _ensure_db_schema(self) -> None:
        """Ensure the database schema is up to date."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("DROP TABLE IF EXISTS projects")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS projects
                (
                    id TEXT PRIMARY KEY,
                    project_name TEXT,
                    author TEXT,
                    frida_version TEXT,
                    description TEXT,
                    source TEXT
                )
                """
            )

    async def update_db(self) -> None:
        """Update the database of codeshare snippets."""
        await self._ensure_db_schema()
        async with httpx.AsyncClient(base_url="https://codeshare.frida.re") as client:
            page = 1
            while True:
                response = await client.get("browse", params={"page": page}, timeout=10)

                if response.status_code != 200:
                    break

                # Parse the projects and extract the hrefs
                soup = bs4.BeautifulSoup(response.text, "html.parser")
                for article in soup.find_all("article"):
                    project_url = article.find("a").get("href")
                    split_url = urlsplit(project_url.replace("@", ""))
                    project_api_url: str = urlunsplit(split_url._replace(path="/api/project" + split_url.path))

                    # Get the project details
                    author = split_url.path.split("/")[1]
                    api_response = await client.get(project_api_url, timeout=10)
                    if api_response.status_code == 200:
                        project = api_response.json()

                        project_id = project["id"]
                        project_name = project["project_name"]
                        project_description = project["description"]
                        project_frida_version = project["frida_version"]
                        project_source = project["source"]

                        # Frida version from API is either a string or a list as a string
                        # We try to use literal eval to get the most recent version if a list is provided
                        try:
                            frida_version = literal_eval(project["frida_version"])
                            project_frida_version = frida_version[0]
                        except Exception:
                            pass

                        async with aiosqlite.connect(self._db_path) as db:
                            await db.execute(
                                "INSERT OR REPLACE INTO projects VALUES (?, ?, ?, ?, ?, ?)",
                                (
                                    project_id,
                                    project_name,
                                    author,
                                    project_frida_version,
                                    project_description,
                                    project_source,
                                ),
                            )
                            await db.commit()
                page += 1

    async def query_all(self):
        """Query all projects."""

        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute("""SELECT id, project_name, author, frida_version FROM projects""") as cursor:
                async for row in cursor:
                    yield list(row)

    async def get_project(self, project_id: str) -> list[str] | None:
        """Query a project by ID."""

        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                """SELECT description, source FROM projects WHERE id=?""",
                (project_id,),
            ) as cursor:
                async for row in cursor:
                    if row:
                        return list(row)
                    else:
                        raise ValueError(f"Project with ID {project_id} not found")

    async def search(self, search_term: str):
        """Search for a project by term."""

        like_search_term = f"%{search_term}%"
        async with aiosqlite.connect(self._db_path) as db:
            try:
                # We need to search all columns for the search term
                # We use LIKE to do a case-insensitive search
                # FTS5 doesn't support LIKE, so we can't use it :(
                async with db.execute(
                    """
                    SELECT id, project_name, author, frida_version
                    FROM projects
                    WHERE project_name LIKE ?
                    OR author LIKE ?
                    OR description LIKE ?
                    OR source LIKE ?
                    """,
                    (
                        like_search_term,
                        like_search_term,
                        like_search_term,
                        like_search_term,
                    ),
                ) as cursor:
                    async for row in cursor:
                        yield list(row)
            except aiosqlite.OperationalError:
                return
