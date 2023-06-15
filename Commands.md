## system
* `/system shutdown`
  * Triggers the bot's shutdown procedure
  * Requirements: Invoker is an owner
* `/system ip`
  * Returns the local IP of the bot for SSH purposes
  * Requirements: Invoker is an owner

## extensions.hoyolab
### Commands
* `/genshin daily redeem_daily [game]`
  * Triggers redeeming the user's daily hoyolab check-in
  * Requirements: User has shared Hoyolab valid cookies
  * Arguments:
    * game: The game to run the command for (`Genshin Impact`, `Hokai Impact 3rd`, or `Honkai Star Rail`)
* `/genshin code redeem <code> [game]`
  * Redeems the code for the user's genshin account
  * Requirements: User has shared Hoyolab valid cookies, code is valid
  * Arguments:
    * code: The code to try redeeming. 
      * Automatically set to uppercase and strips whitespace
    * game: The game to run the command for 
      * `Genshin Impact`, `Hokai Impact 3rd`, or `Honkai Star Rail`
* `/genshin code share <code> [game]`
  * Redeems the code for all users there is cookie data for and have enabled `auto_codes`
  * Requirements: User has shared Hoyolab valid cookies, code is valid
  * Arguments:
    * code: The code to try redeeming.
      * Automatically set to uppercase and strips whitespace
    * game: The game to run the command for 
      * `Genshin Impact`, `Hokai Impact 3rd`, or `Honkai Star Rail`
* `/genshin config check`
  * Checks the user's cookies and settings and returns a report
  * Requirements: User has shared Hoyolab valid cookies
* `/genshin config cookies`
  * Returns a modal for the user to configure their Hoyolab cookies
  * Existing setting will be preserved, else defaulting to True/Enabled
* `/genshin config delete`
  * Deletes the user's cookies / settings if they are present
* `/genshin config settings [auto_daily] [auto_codes] [notif_daily] [notif_codes]`
  * Allows users to update their settings for interactions with Hoyolab
  * Requirements: User has shared Hoyolab valid cookies
  * Arguments:
    * auto_daily: Allow the bot to automatically redeem your HoyoLab daily check-in.
      * True: Enabled | False: Disabled | None: Leave unchanged
    * auto_codes: Allow the bot to redeem codes others share with the share_codes command.
      * True: Enabled | False: Disabled | None: Leave unchanged
    * notif_daily: Receive DMs for automatically claimed daily check-in rewards.
      * True: Enabled | False: Disabled | None: Leave unchanged
    * notif_codes: Receive DMs for automatically claimed gift codes.
      * True: Enabled | False: Disabled | None: Leave unchanged
* `/genshin unlock`
  * Returns a modal to enter the key for the Hoyolab data
  * Requirements: Invoker is an owner
  * Commands / Routines that require HoyolabData will not work until this is provided
    * Exceptions: `/genshin config delete`
* `/genshin lock`
  * Deletes the key for the Hoyolab data, returning it to a pre-`/genshin unlock` state
  * Requirements: Invoker is an owner

### Routines / Listeners
* `auto_redeem_daily`
  * Automatically redeems Hoyolab daily check-in for all users with valid cookies 
and the `auto_daily` option enabled. Additionally, users with `notif_daily` enabled will
receive a DM informing them of the result.
  * Trigger: `16:15:05 UTC` daily. (`00:15:05 UTC+08:00`)
* `unlock_reminder`
  * Informs the bot owner(s) that HoyoLabData doesn't have a key.
  * Trigger: `bot.on_ready` (initial startup / reconnect)

## extensions.vc_log
### Commands
* `/vclog force_scan_vcs`
  * Make voice states assumed by logs match actual voice states
  * Requirements: Invoker is an owner
* `/vclog joined [channel] [amount] [time_format]`
  * View the joined log of the current or provided voice channel
* `/vclog left [channel] [amount] [time_format]`
  * View the left log of the current or provided voice channel
* `/vclog all [channel] [amount] [ignore_empty] [remove_dupes] [remove_undo] [time_format]`
  * View all the logs of the current or provided voice channel
* `/vclog get <include> <include_alt> [channel] [amount] [ignore_empty] [remove_dupes] [remove_undo] [time_format]`
  * View a specific log of the current or provided voice channel
  * Arguments:
    * include: The voice state change type to show the logs of
    * include_alt: Include the 'opposite' voice state change type as well
      * e.g. `channel_join` and `channel_left`
* Arguments:
    * channel: The channel to get logs from
      * If empty: Uses channel sent in, channel invoker is in, or fails
    * amount: The number of entries to display
      * -1 = all (or at least however many can fit in the field)
    * time_format: The time format to send with the timestamps
    * ignore_empty: Weather or not to include fields for voice state change types that have no events
    * remove_dupes: Weather or not to include multiple events by the same member
      for the same voice state change type
    * remove_undo: Weather or not to include actions that where 'undone' by later actions
      * e.g. exclude a `channel_join` if that member has a later `channel_left`
    * time_format: The time format for the timestamps
      * See [Discord's Docs](https://discord.com/developers/docs/reference#message-formatting-timestamp-styles)
        and [LeviSnoot's Explanation](https://gist.github.com/LeviSnoot/d9147767abeef2f770e9ddcd91eb85aa)
### Routines / Listeners
* `on_ready`
  * When the bot is fully connected, make voice states assumed by logs match actual voice states
  * Same as manually running `/vclog force_scan_vcs`
* `on_voice_state_update`
  * When a member performs a voice state update, log the who, what, and when.
  * When a member leaves and the voice channel is then empty, clears all logs for that channel
