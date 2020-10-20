# Digital Foundry Updater

This is a tool that will allow you to download new digital foundry videos to whichever folder you'd like! Perfect for Plex libraries and whatnot.
You can sign up for Twilio, and this app will text you updates for whenever a new video has been downloaded, or if you need to re-log in to your DF account.

## Configuration
All you need to do is supply a TOML file for configuration as `conf.toml` in the same directory as the main.py, and you should be good.
The Twilio configuration is optional, feel free to exclude it, but if included, this tool will text you when new videos are downloaded, or when you have to sign in again.
#### Example
```toml
[twilio]
    [twilio.auth]
    sid = "sid_from_twilio"
    token = "token_from_twilio"

    [twilio.phone]
    to = "phone number to send updates to"
    from = "twilio account phone number"

[conf]
browser = "chrome" # Can be "chrome", "safari", or "firefox"
refresh_mins = 60 # How often to check for new videos
```

## Usage
Just run `main.py` and be on your way!

You need to sign into Digital Foundry in your browser of choice that you specified in the TOML file. This can be done before or after you start the script, as the next time it checks for updates, it will reload the cookies.
To keep the load off of the Digital Foundry servers, this tool only checks for new videos once every hour by default, but you can change the frequency in the TOML. You can also send a `SIGTERM` (`^C`) to have it check for updates immediately. You can do a `^C^C` to kill it too.