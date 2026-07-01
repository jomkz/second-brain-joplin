# How I Built My Second Brain with Obsidian and Claude (MCP Included)

Syed Ali Turab
Jun 12, 2026

https://medium.com/@syedturab97/how-i-built-my-second-brain-with-obsidian-and-claude-mcp-included-66bf656a3179

## Article

A fresh Mac, a folder of Markdown files, and an AI that can actually read my notes.

A few weeks ago I retired my old Intel i7 MacBook and upgraded to an M5. You know that feeling when a new machine arrives and you swear this time you’ll keep it clean? No 400 desktop icons, no seventeen note apps fighting for your attention?

Full disclosure: I tried this whole setup on the i7 first. It did not go well. Obsidian by itself was fine, but the moment I stacked Claude Desktop and an MCP server on top, the poor thing would just freeze on me. Fans screaming, beachball spinning, the works. An eight year old Intel chip running an Electron note app, an AI client, and Node processes at the same time was never going to win that fight.

So the M5 became my fresh start. Instead of migrating my mess, I finally built a proper Second Brain. And I went one step further than most guides: I wired it up to Claude with MCP, so my AI assistant can read, search, and write my notes directly.

Here’s the whole setup, the stuff that broke along the way, and how I actually use it every day.
Why Obsidian

I’d read Kevin T’Syen’s piece on building a Second Brain with Obsidian, and the core argument stuck with me: your notes should be plain Markdown files, on your own disk, in folders you control. No proprietary cloud, no lock-in, no laggy web app. If Obsidian disappears tomorrow, my notes are still just text files.

On the M5, Obsidian is instant. Search across the entire vault feels like running grep on a local SSD, because that’s basically what it is.
The Vault Structure

My vault is a single folder on my desktop called Second Brain:

    1.  Inbox: a scratchpad. Everything lands here first: ideas, links, “look this up later.” No organizing allowed at capture time.
    2.  Daily Notes: one note per day. Tasks, a running log, and a quick end of day reflection.
    3.  Projects: anything with a goal and an end date. One note or folder per project.
    4.  Areas: ongoing stuff with no end date. Health, finances, the courses I teach.
    5.  Resources: reference material I might need someday. My sports notes live here too (more on that below).
    6.  Learnings: takeaways from books, courses, and articles. Writing the summary is what makes it stick.
    Excalidraw: diagrams and mind maps, drawn right inside Obsidian.
    Files: PDFs, images, attachments.
    Templates: reusable formats for daily notes, meetings, project kickoffs, learning notes, and weekly reviews.

Five plugins power the whole thing: Templater for consistent note formats, Tasks for due dates and recurring todos inside Markdown, Dataview to query your notes like a database, Kanban for bigger projects, and Excalidraw. A Home.md dashboard uses Dataview to show open tasks, active projects, and recently edited notes the moment I open the app.
The Part Most Guides Skip: Connecting Claude via MCP

Obsidian alone is a great filing cabinet. But a filing cabinet doesn’t answer questions.

MCP, the Model Context Protocol, is an open standard that lets AI assistants talk to external tools and data. An MCP server exposes capabilities (read a note, search a vault, create a file) and the AI client connects to it. Claude Desktop supports MCP natively, which means Claude can work inside my vault. Not pasted snippets. The actual files.
The setup

Since the vault is plain Markdown, you don’t need anything heavy. I used a filesystem based Obsidian MCP server that runs via npx. No Obsidian plugin required, and it works even when Obsidian is closed.

The config goes in ~/Library/Application Support/Claude/claude_desktop_config.json:

{
  "mcpServers": {
    "obsidian": {
      "command": "npx",
      "args": ["-y", "obsidian-mcp", "/Users/you/Desktop/Second Brain"]
    }
  }
}

Quit and reopen Claude Desktop, and the server shows up under the tools icon.
Two things broke (so you don’t have to debug them)

Problem #1: “Could not attach to MCP server.” A brand new Mac doesn’t ship with Node.js, and npx is part of Node. The MCP log at ~/Library/Logs/Claude/mcp-server-obsidian.log said it plainly: Failed to spawn process: No such file or directory. Five minutes later (nodejs.org, LTS installer, done) Node was sitting in /usr/local/bin, exactly where Claude Desktop looks.

Problem #2: “Not a valid Obsidian vault.” The server refused to start because my vault folder had never been opened in Obsidian, so it was missing the hidden .obsidian config directory. Open the folder once in Obsidian ("Open folder as vault") and you're good. Restart Claude, and this time: attached.

Lesson: when an MCP server acts up, read the log. The answer is usually sitting right there.
How I Actually Use It Day to Day

The mechanics are simple. Capture into the Inbox all day, keep a Daily Note running, sort everything during a weekly review. The Claude layer is what changed my habits, because now the vault talks back.

Mornings. “Create today’s daily note from my template and carry over any unfinished tasks from yesterday.” Done before my coffee is.

Capture. Random thought mid meeting? “Add ‘compare backup strategies for the vault’ to my Inbox.” I never leave what I’m doing.

Sports, my favorite use case. It’s June 2026, which means I’m juggling the World Cup happening right here in North America, the MLB season grinding along, and the NBA and NHL finals overlapping in the same two weeks. My system:

    A World Cup 2026 note in Resources. After matches I tell Claude “log today’s results in my World Cup note and update my knockout bracket predictions.” Watch parties, group stage tables, my increasingly wrong predictions. All in one note I’ll enjoy rereading for years.
    An MLB 2026 note where I track my team’s series results and a watchlist of players. Once a week: “summarize what I logged about the season this week.”
    A Finals note for the NBA and NHL playoffs. Before game nights I ask “what did I write after the last game?” and get my own takes back, which beats scrolling a feed of everyone else’s.

The point isn’t that an AI tracks sports for me. It’s that my own notes became something I can ask questions to. Same pattern works for anything you log over time.

Weekly review. Sunday evening: “Search my vault for everything I added this week and group it by folder. What’s still sitting in the Inbox?” Claude does the boring half of the review. I just make the decisions.
Gym, Intramural Ball, and Actually Tracking It

I don’t just watch sports, I play them badly twice a week. Gym sessions, intramural basketball, and softball all live in the vault now, each with a note under Areas.

Gym. Every session gets two lines in my daily note: what I lifted, how it felt. That’s it, thirty seconds. The magic is on the other end. “What was my squat working weight three weeks ago?” or “when did my shoulder last complain on bench?” and Claude pulls it straight from my own logs. I stopped guessing whether I’m progressing because the answer is sitting in my notes.

Get Syed Ali Turab’s stories in your inbox

Join Medium for free to get updates from this writer.

Remember me for faster sign in

Intramural basketball. After games I dump quick thoughts into the Inbox: what worked against that zone, who on our team should never bring the ball up again (sometimes that’s me), what to try next week. Before the next game I ask “what did I write after our last two games?” and walk in with an actual plan instead of vibes.

Softball. Same deal. Lineup notes, which field we’re on, how I did at the plate, the adjustment I keep telling myself to make and keep not making. There’s something humbling about asking Claude “how many times have I written ‘stop swinging at the high ones’?” and getting a number back.

None of this is fancy. It’s the same Inbox and daily note habit pointed at sweat instead of work. But it turns “I feel like I’m improving” into “here’s what I logged,” and that’s a different level of honest.
The Security Rabbit Holes

I spend a lot of my free time going down security rabbit holes. OSINT investigations, new CVEs, detection rules, write ups from incidents other people were unlucky enough to live through. The problem with rabbit holes is that you climb out with twenty browser tabs and remember none of it a month later.

Now it all goes in the vault:

    OSINT notes. When I’m digging into a technique or tool (Google dorking tricks, DNS recon, social media footprinting), each one gets a note with what worked and what didn’t. Later I just ask Claude “what OSINT techniques do I have for domain recon?” and my own research comes back to me.
    CVE and threat notes. Interesting advisories get a quick Learning note with the takeaway. Over time it turns into a personal, searchable feed of the threats I actually cared about, not whatever the algorithm pushed that day.
    Lab write ups. CTF solutions, Sigma rules I’ve messed with, home lab experiments. Tagged, linked, and findable when I hit something similar six months later.

One thing I’ll say because the security folks will think it anyway: think before pointing an AI at a folder. My vault is one directory of Markdown that I chose to expose. The MCP server runs locally and nothing sensitive (credentials, anything regulated, anything about real people) goes in the vault, full stop. Least privilege applies to your notes too.
The Professor Side of Things

I also teach, and this setup has quietly made me a better prof.

Every course I run has its own folder under Areas. Lecture notes, lab instructions, the questions students asked that I didn’t have a great answer for in the moment. That last one is the gold. After class I dump them into the Inbox, and before the next lecture I ask Claude “what student questions am I still owing answers on?”

It compounds across semesters too. When I’m refreshing a course, I ask “what tripped students up in week 5 last time?” and my own notes tell me exactly where the lecture lost people. The labs that landed, the ones that flopped, the analogies that finally made a concept click. All of it written down in thirty seconds at the time, all of it retrievable when I’m planning.

Students think I have a great memory. I have a folder of Markdown files and an AI that reads it.
Adding a Local Brain: Ollama and Qwen

Claude is the assistant I reach for first. But I didn’t love the idea that every question about my notes had to leave my machine. Some of what’s in the vault (security research, half-formed ideas, the embarrassing softball self-talk) I’d rather keep entirely local. So I added a second engine: open models running on my own hardware through Ollama.

Ollama is the easiest way to run local LLMs on a Mac. Download the app from ollama.com, drag it to Applications, launch it once to install the command line helper, and you’ve got a local model server listening on localhost:11434. No cloud, no API key, no per-token bill. On the M5, with its unified memory, this is where the new machine really earns its keep.

The models I run are from Alibaba’s Qwen family, which has become my favorite open weights for this kind of work. With 48 GB of unified memory, my sweet spot is the 35B-class model in its Apple-Silicon-optimized MLX build:

ollama pull qwen3.6:35b-mlx     
ollama pull qwen3.6:27b-mlx     
ollama pull qwen3-embedding     

A quick ollama run qwen3.6:35b-mlx "summarize this" and I'm talking to a model that never phones home. For semantic search ("find me notes related to this idea, not just keyword matches"), the embedding model feeds an Obsidian plugin like Smart Connections or Copilot, both of which let you point at a local Ollama endpoint instead of a cloud API.

How I split the work. Claude stays my primary for anything heavy: long synthesis across dozens of notes, tricky reasoning, drafting. Local Qwen is the backup, and it shines in three spots. When I’m offline or on a sketchy connection, the vault still talks back. For routine, high-volume chores (tagging, quick lookups, “what did I log Tuesday”) a local model is plenty smart and instant. And for the genuinely sensitive folders, nothing leaves the laptop, full stop. Same vault, two engines, and I choose based on the question.

A note on hardware honesty: a local 35B model is excellent, but it isn’t Claude. For the hardest reasoning I still go to the cloud. The point isn’t to replace Claude, it’s to have a private, always-available fallback that costs nothing to run.
Wiring Qwen into the vault (the part that actually trips people up)

Running Qwen in a terminal is one thing. Getting it to read my notes inside Obsidian is the part worth writing down, because I lost a few minutes to one non-obvious gotcha.

I used the Copilot community plugin. The flow:

    In Obsidian, enable community plugins, install Copilot, and open its settings.
    Go to the Model tab and click Add Model. Set the model name to qwen3.6:35b-mlx, choose Ollama as the provider, and leave the Base URL blank (it defaults to localhost:11434).
    Hit Test. It failed. Red X.

This is the gotcha: Ollama rejects requests coming from the Obsidian app origin by default, so the connection gets blocked. The fix turned out to be one checkbox in that same form, labeled CORS. Tick it, hit Test again, and this time: “Model verification successful.” Click Add Model, then set it as the Default Chat Model in Copilot’s Basic tab.

Now Copilot has two modes that matter. Chat is a plain local assistant. Vault QA is the one that earns its keep: it searches the whole vault and answers from my own notes, entirely offline. The first reply is slow while 22 GB of model loads into memory, then it’s snappy. Ask it “what did I log at the gym this week” and the answer comes back without a single byte leaving the laptop.

Lesson, again: when the local stack won’t connect, it’s almost always CORS or a model that isn’t actually pulled. Check those two before you touch anything else.
A Second Life for the Intel Mac

The i7 didn’t go in a drawer, by the way. It chokes on the AI layer, but it’s still a perfectly good Unix box, so it became the vault’s infrastructure:

    Git sync and backup server. The vault is a Git repo (via the Obsidian Git plugin) and the i7 holds a clone. Every change versioned in two places, no subscription required.
    Capture station. Obsidian alone runs fine on it, so it sits on my desk as a second screen for notes while the M5 does the heavy lifting.
    Lab machine. Old hardware is exactly what you want for security tinkering. An isolated box for testing tools and breaking things, with the findings written up into the vault afterwards.

Old Mac protects the brain. New Mac thinks with it.
Do You Actually Need MCP?

Honest answer: no, and then yes.

You don’t need it to build a Second Brain. Obsidian plus five plugins is a complete system, and that’s where the real habit lives: capture, daily notes, weekly review.

But once the vault grows past a few dozen notes, MCP is the difference between a notebook and an assistant. A notebook stores what you wrote. An assistant finds it, summarizes it, and files new things in the right place while you stay focused. The setup costs twenty minutes plus two gotchas, and the payoff compounds with every note you add.
Final Thoughts

My old i7 had years of scattered notes across apps I barely remember installing. The M5 has one folder of Markdown files and two AIs that know their way around it: Claude in the cloud for the heavy lifting, and a local Qwen model on the metal for everything I want to keep private or run offline.

Start simple: one folder, one daily note, one Inbox. Let it grow. Wire it up to Claude and watch your notes start answering back. Then, when you’re ready, add a local model so the brain keeps thinking even when the internet doesn’t.

If you want my templates or the exact config, reach out. Happy to share.
