from steam_playtime.steam.log_parser import parse_line


def test_parses_a_shortcut_start_and_signed_stop_with_same_appid():
    start = parse_line(
        '[2026-08-04 14:45:58] AppID 14209595030481403904 adding PID 18837 as a tracked process '
        '"SteamLaunch AppId=3308429157 -- emulator"'
    )
    stop = parse_line('[2026-08-04 14:47:08] Remove -986538139 from running list')

    assert start.appid == "3308429157"
    assert stop.appid == "3308429157"
