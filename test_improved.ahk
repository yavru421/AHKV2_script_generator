F3::
{
    SoundSetMute(-1)
    GetVolumeState := SoundGetMute()
    if (GetVolumeState = 1)
        TrayTip('Mute Status', 'Muted')
    else
        TrayTip('Mute Status', 'Unmuted')
}