## system
* `/system shutdown`
  * Triggers the bot's shutdown procedure
  * Requirements: Invoker is an owner
* `/system ip`
  * Returns the local IP of the bot for SSH purposes
  * Requirements: Invoker is an owner

## extensions.hoyolab
### Commands
* `/genshin daily redeem_daily`
  * Triggers redeeming the user's daily hoyolab check-in
  * Requirements: User has shared Hoyolab valid cookies
* `/genshin code redeem <code>`
  * Redeems the code for the user's genshin account
  * Requirements: User has shared Hoyolab valid cookies, code is valid
* `/genshin code share <code>`
  * Redeems the code for all users there is cookie data for and have enabled `auto_codes`
  * Requirements: User has shared Hoyolab valid cookies, code is valid
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
***(WIP)***
### Commands
### Routines / Listeners
