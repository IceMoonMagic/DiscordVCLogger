# My Discord Bot
Everything related to my personal discord bot.

## Table of Contents
* [Setup](#setup)
    * [Requirements](#requirements)
    * [Preparations](#preparations)
    * [Selecting Extensions](#selecting-extensions)
    * [Running](#running)
* [Extensions](#extensions)
    * [VC Log](#vc-log)
    * [HoyoLab](#hoyolab)
* [(Lack of) Contributions](#contributions)
* [Licence](#license)

## Setup
### Requirements
- [`Python 3.11`](https://www.python.org/)
- [`py-cord`](https://pypi.org/project/py-cord/): Discord API Library
- [`aiosqlite`](https://pypi.org/project/aiosqlite/): Async SQLite
- [`pynacl`](https://pypi.org/project/aiosqlite/): Encryption Library
- [`genshin`](https://pypi.org/project/genshin/): Interactions with [HoyoLab](https://www.hoyolab.com/)

### Preparations
1. Install a Python version of at least `3.11`
2. Optionally, create a virtual environment with `python -m venv .venv` and
    activate it.
   * Windows (cmd.exe) `.venv\Scripts\activate.bat`
   * Windows (PowerShell) `.venv\Scripts\activate.ps1`
   * MacOS / Linux (Bash) `source .venv/bin/activate` 
3. Install requirements with
   `python -m pip install -r requirements.txt`
4. Make `saves/bot_key.json` following the template of `bot_key_template.json`.
    - Set the `"key"` to your discord bot key.
    - Set the `"owners"` to your discord id(s).

### Selecting Extensions
All [extensions](#extensions) are enabled by default. 
They can be disabled by removing them from the extensions list in `saves/bot_key.json` (under `"__main__"` -> `"extensions"`).

### Running
Execute `python discord_bot.py`

```
usage: discord_bot.py [-h] [-q] [-d]

options:
  -h, --help   show this help message and exit
  -q, --quiet
  -d, --debug
```

Some extensions will use encryption for their data, you will need to provide a key to unlock them before they will work properly.

The following extensions require a key:
- `HoyoLab`: Unlocked with `/genshin unlock` and submitting a key to the modal.

## Extensions
A full list of commands is available [here](Commands.md).
### VC Log
Records voice state updates in discord.
This was started to help find out who just joined / left a voice channel or how long ago that was.

When a user performs (or has performed on them) a voice state update (e.g. joining / leaving a channel or (un)muting),
the event will be logged. Users can then use commands to view the logs.
The logs are cleared when the last person leaves a voice channel.

Users can view the logs for all voice state change types with `/vclog all`, or a specific set with `/vclog get`.

Users can fetch when the currently present members joined using `/vclog joined` 
and when currently absent members (that were previously present) left using `/vclog left`.

While `/vclog joined` is equivalent to 
`/vclog get {include: channel_join} {include_alt: False} {ignore_empty: False} {only_present: True}`,
`/vclog left` would be equivalent to 
`/vclog get {include: channel_left} {include_alt: False} {ignore_empty: False} {only_present: None}`,
but this can't be sent in a slash command set to expect a boolean response.

While the bot should automatically try fixing up the logs when it's 'ready' (properly connects / reconnects to Discord),
a call to the fixup method can be done with `/vclog force_scan_vcs` by owners.

### Misc
Simple commands that don't fit elsewhere.

A user can open the context menu of a message, `Apps > Convert Links` to have the bot replace parts of the link to work better with discord.
For example, fixing a twitter embed by using [vxTwitter](https://github.com/dylanpdx/BetterTwitFix).
This can be configured in the json under `link_fixes`. 
Note that this simply uses Python's `str.replace` 
and replacements logic can be tested with `python -c "print('link_text'.replace('old', 'new'))"`.

### HoyoLab
___Abandoned___ due to taking more work to maintain than it is worth (thanks Hoyoverse).
I may try to keep it working, but it may be dropped at any point and completely removed if everything stops working.

Allows automatically redeeming [HoyoLab Daily Check-In](https://genshin-impact.fandom.com/wiki/HoYoLAB_Community_Daily_Check-In) 
and redeeming [Gift Codes](https://genshin.hoyoverse.com/en/gift).
(Note: Links here are specific to Genshin Impact, but functionality should be present for Honkai Impact 3rd and Honkai Star Rail as well)

Users can register their cookies using the `/genshin config cookies`.
This will present them with a modal that for them to insert their `account_id` and `cookie_token` from [HoyoLab](https://www.hoyolab.com/).
The other necessary cookies are automatically created.
the cookies are encrypted before being stored.

Users can delete their registered cookies with `/genshin config delete`.

Users can set the following settings with `/genshin config settings`.

- Weather or not to automatically redeem daily check-in rewards.
- Weather or not to send a DM notification relating to automatically redeemed daily check-in rewards.
- Weather or not to redeem codes shared with `/genshin code share {code}`
- Weather or not to send a DM notification relating to automatically redeemed gift codes.

Users can check if their current settings and if their current cookies work with `/genshin config check`.

Users can share a gift code with themselves and anyone with the appropriate setting using `/genshin code share {code}`.
Alternatively, they can use `/genshin code redeem {code}` to only redeem it for themselves.

Users can manually redeem their daily check-in using `/genshin daily redeem_daily`.

Owners can manually trigger the automatic daily check-in redemption with `/genshin daily induce_daily`.

Owners can unlock the extension's data with `/genshin unlock` or re-lock it with `/genshin lock`.

### Epic Games
Notifications for the current free games on the Epic Games Store.

Users can check the current free games with `/epic current`.

Users in DMs, Webhook Managers, Channel Mangers in channels, and Thread Managers in threads can create a register a notification location with `/epic add_notif` and remove it with `/epic rm_notif`.
Registered DMs / Channels / Threads will be sent the embed for the new free games when they become free.

Owners can manually reset the internal loop with `/epic hard_reset`. This deletes the existing loop and starts a new one, which also re-fetches the free games.

### Time
Commands for helping users make discord timestamps.
All commands in this module return an embed with the specified time in all of discord's timestamp formats, along with a copy in copy-able text.

Users can get timestamps for the current time with `/time now`.

Users can get timestamps for a time after a specific delta `/time in [days] [hours] [minutes] [seconds] [milliseconds]`. The arguments are directly mapped to a python timedelta object, which is then added to a "now" datetime.

Users can get timestamps for a specific time with `/time at <year> <month> <day> [hour] [minute] [second] [microsecond] [tz_offset]`. The arguments are directly mapped to a python datetime object. The `tz_offset` is the hours offset from UTC.

## Contributions
This is a personal project, any modifications you may want to make will likely be better suited for your own fork.

Also, the code now follows 
[The _Black_ Style Guide](https://black.readthedocs.io/en/stable/the_black_code_style/current_style.html),
with the setting the line length to 79 (`--line-length 79`).
## License
[MIT License](LICENSE) | [Read More](https://choosealicense.com/licenses/mit/#)

