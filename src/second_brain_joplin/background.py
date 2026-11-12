"""Background sync of the semantic index for the long-running HTTP server.

A remote tool call must finish quickly: claude.ai stops waiting after 240 seconds
and Cloudflare drops a response that sends nothing for 125. Indexing therefore
stays out of the request path. In HTTP mode the server syncs the index once at
start-up and then every ``SBJ_SYNC_INTERVAL_MINUTES``; a first full build of a
large vault is best done beforehand with ``second-brain-joplin reindex``.
"""

import asyncio
import logging

from .context import AppContext
from .errors import JoplinError, NotebookFilterError, SemanticUnavailableError

logger = logging.getLogger("second_brain_joplin.background")

DEFAULT_SYNC_INTERVAL_MINUTES = 15


async def sync_forever(app: AppContext, interval_seconds: float) -> None:
    """Sync now, then every ``interval_seconds``, until cancelled.

    Runs are sequential, so two never overlap (and the service's own lock keeps
    them apart from a ``joplin_reindex`` call). A failed run is logged and the
    loop goes on; a missing semantic extra stops the loop for good, since no
    later run could succeed.
    """
    while True:
        try:
            stats = await app.semantic().sync()
        except SemanticUnavailableError:
            logger.info("background index sync is off: semantic search isn't installed")
            return
        except JoplinError as exc:  # messages are about Joplin, never note content
            logger.warning("background index sync failed: %s", exc)
        except NotebookFilterError as exc:  # names the entry at fault, never a note
            logger.warning(
                "background index sync skipped, the notebook filter is wrong: %s", exc.detail
            )
        except Exception as exc:  # keep going; the type is enough to investigate
            logger.warning("background index sync failed: %s", type(exc).__name__)
        else:
            logger.info(
                "background index sync: added=%d updated=%d deleted=%d total=%d",
                stats.added,
                stats.updated,
                stats.deleted,
                stats.total,
            )
        await asyncio.sleep(interval_seconds)
