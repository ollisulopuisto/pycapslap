from app.views.video_player import VideoPlayerWidget


def test_video_player_playback_speed_controls(qtbot):
    player = VideoPlayerWidget()
    qtbot.addWidget(player)

    # Initial state
    assert hasattr(player, "speed_btn")
    assert player.speed_btn.text() == "1.0x"
    assert player.playback_rate == 1.0
    assert player.media_player.playbackRate() == 1.0

    # Cycle speed: 1.0x -> 1.25x
    player.speed_btn.click()
    assert player.playback_rate == 1.25
    assert player.speed_btn.text() == "1.25x"
    assert player.media_player.playbackRate() == 1.25

    # Cycle speed: 1.25x -> 1.5x
    player.speed_btn.click()
    assert player.playback_rate == 1.5
    assert player.speed_btn.text() == "1.5x"
    assert player.media_player.playbackRate() == 1.5

    # Cycle speed: 1.5x -> 2.0x
    player.speed_btn.click()
    assert player.playback_rate == 2.0
    assert player.speed_btn.text() == "2.0x"
    assert player.media_player.playbackRate() == 2.0

    # Cycle speed: 2.0x -> 1.0x
    player.speed_btn.click()
    assert player.playback_rate == 1.0
    assert player.speed_btn.text() == "1.0x"
    assert player.media_player.playbackRate() == 1.0

    # Direct setter
    player.set_playback_rate(1.5)
    assert player.playback_rate == 1.5
    assert player.speed_btn.text() == "1.5x"
    assert player.media_player.playbackRate() == 1.5
