F3::
SoundSet, +1, , Toggle
if (ErrorLevel = 0) {
    if (GetVolume() = 0) {
        TrayTip, Mute, Unmuted
    } else {
        TrayTip, Mute, Muted
    }
}
return

GetVolume() {
    SoundGet, volume, Master, Volume
    return volume
}