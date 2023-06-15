# My Discord Bot
Everything related to my personal discord bot.

## Table of Contents
* [Setup](#setup)
    * [Requirements](#requirements)
    * [Preparations](#preparations)
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
2. Install requirements
   `python -m pip install -r requirements.txt`
3. Make `saves/bot_key.json` following the template of `bot_key_template.json`.
    - Set the `"key"` to your discord bot key.
    - Set the `"owners"` to your discord id(s).

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

### HoyoLab
Allows automatically redeeming [HoyoLab Daily Check-In](https://genshin-impact.fandom.com/wiki/HoYoLAB_Community_Daily_Check-In) 
and redeeming [Gift Codes](https://genshin.hoyoverse.com/en/gift).
(Note: Links here are specific to Genshin Impact, but functionality should be present for Honkai Impact 3rd and Honkai Star Rail as well)

Users can register their cookies using the `/genshin config cookeis`.
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

## Contributions
This is a personal project, any modifications you may want to make will likely be better suited for your own fork.
[See Licence](#license)

## License
[MIT License](LICENSE)

[Read More](https://choosealicense.com/licenses/mit/#)

