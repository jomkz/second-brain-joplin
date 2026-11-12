# Note templates

Four starter notes for a [PARA](https://fortelabs.com/blog/para/) notebook
layout ([docs/notebook-structure.md](../docs/notebook-structure.md)). They are
plain Markdown files that you import into Joplin yourself. Nothing here is
installed with the server, and the server never adds them for you.

| Template | For |
|---|---|
| [Project](Templates/Project.md) | Something with an outcome and an end: the outcome, the next actions, a log |
| [Area](Templates/Area.md) | An ongoing responsibility: the standard you keep, routines, a running log |
| [Resource](Templates/Resource.md) | Reference material: a summary in your own words and the points worth keeping |
| [Weekly review](Templates/Weekly%20review.md) | The checklist that keeps the Inbox empty and the projects moving |

There is no Inbox template on purpose: capture should take no thought. Sorting
happens in the weekly review.

## Import them into Joplin

1. Get the files: on GitHub choose **Code → Download ZIP** and unpack it, or
   clone the repository.
2. In Joplin Desktop choose **File → Import → MD - Markdown (directory)** and
   pick the `templates/Templates` folder.

Joplin makes a notebook named **Templates** holding the four notes, each titled
after its file. To import a single template into the notebook you have open,
choose **File → Import → MD - Markdown (file)** instead.

## Use them

**By hand.** Right-click a template, choose **Duplicate**, then rename the copy
and move it where it belongs.

**With the Templates plugin.** The
[Templates plugin](https://github.com/joplin/plugin-templates) makes a new note
from a template in one step. It treats any note tagged `template` as a
template, so tag the four notes. (Its settings can instead treat every note in a
notebook named "Templates" as one, which the import above already gives you.)
The plugin can also fill in values such as `{{date}}`; add those to your copies
if you use it.

**With your assistant.** Once the Templates notebook is visible to the server,
you can ask for a note made from one:

> Make a project note for the kitchen remodel from my Project template. The
> outcome is a finished kitchen by March. Put it in my Inbox.

The assistant reads the template, fills it in and creates the note with
`joplin_create_note`, which needs
[`SBJ_WRITE_NOTEBOOKS`](../docs/configuration.md#notebooks) to allow the
notebook. Keep your client set to ask before each note, and it shows you the
note before it is written
([Who confirms each note](../docs/remote-access.md#who-confirms-each-note)).

The weekly review works the same way:

> What's in my Inbox? For each note, suggest whether it belongs to a project,
> an area or Resources.

> Which notes did I change this week?

The server only adds notes. Moving a note out of the Inbox, and ticking a box,
stay with you in Joplin.

## Make them yours

These are starting points. Change the headings to fit how you work, and keep
your versions in Joplin: once imported, the notes are yours and nothing
overwrites them.
