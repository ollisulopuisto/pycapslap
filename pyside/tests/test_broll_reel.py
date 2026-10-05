import shutil
import subprocess

import pytest

from app.services.broll import picks, reel
from app.services.broll.assets import Asset

FFMPEG = shutil.which("ffmpeg")


def asset(title="A.jpg", kind="image", **kw):
    return Asset(
        title=title,
        kind=kind,
        url=f"https://x/{title}",
        page_url=f"https://p/{title}",
        license="CC BY 2.0",
        author="Ann",
        source="Wikimedia Commons",
        thumb_url=f"https://t/{title}",
        **kw,
    )


def out_t(cmd):
    """The output's -t, which comes after every input's."""
    return cmd[len(cmd) - 1 - cmd[::-1].index("-t") + 1]


def proposals():
    return [
        {
            "startMs": 0,
            "endMs": 4000,
            "text": "t",
            "query": "q",
            "candidates": [
                asset("A.jpg").to_dict(),
                asset("B.webm", "video").to_dict(),
            ],
            "chosen": None,
        },
        {
            "startMs": 4000,
            "endMs": 9000,
            "text": "u",
            "query": "r",
            "candidates": [asset("C.jpg").to_dict()],
            "chosen": None,
        },
    ]


# --- the picker's model -------------------------------------------------------


def test_nothing_is_accepted_until_a_person_accepts():
    p = picks.Picks(proposals())
    assert p.accepted() == []
    assert [s for s in p.status] == ["pending", "pending"]


def test_accept_and_reject_set_status_and_choice():
    p = picks.Picks(proposals())
    p.accept(0, 1)
    p.reject(1)
    assert p.status == ["accepted", "rejected"]
    (win, a) = p.accepted()[0]
    assert (win["startMs"], a.title) == (0, "B.webm")
    assert p.pending() == []


def test_accept_refuses_a_candidate_that_does_not_exist():
    p = picks.Picks(proposals())
    with pytest.raises(IndexError):
        p.accept(1, 3)


def test_reject_after_accept_clears_the_choice():
    p = picks.Picks(proposals())
    p.accept(0, 0)
    p.reject(0)
    assert p.accepted() == []
    assert p.data()[0]["chosen"] is None


def test_picks_round_trip_through_the_proposals_json():
    p = picks.Picks(proposals())
    p.accept(0, 1)
    p.reject(1)
    q = picks.Picks(p.data())
    assert q.status == ["accepted", "rejected"]
    assert q.accepted()[0][1].title == "B.webm"


# --- the reel's plan and ffmpeg command ---------------------------------------


def test_shots_have_start_end_file_and_credit(tmp_path):
    p = picks.Picks(proposals())
    p.accept(0, 0)
    p.accept(1, 0)
    files = {"A.jpg": tmp_path / "a.jpg", "C.jpg": tmp_path / "c.jpg"}
    shots = reel.shots(p.accepted(), files)
    assert [(s.start_ms, s.end_ms) for s in shots] == [(0, 4000), (4000, 9000)]
    assert shots[0].credit == "A.jpg by Ann, CC BY 2.0, Wikimedia Commons"
    assert shots[0].kind == "image"


def test_shots_are_cut_off_where_the_next_begins(tmp_path):
    p = picks.Picks(proposals())
    p.accept(0, 0)
    p.accept(1, 0)
    data = p.data()
    data[0]["endMs"] = 6000  # overlaps the next window
    q = picks.Picks(data)
    files = {"A.jpg": tmp_path / "a.jpg", "C.jpg": tmp_path / "c.jpg"}
    shots = reel.shots(q.accepted(), files)
    assert shots[0].end_ms == 4000


def test_command_has_one_input_per_shot_and_the_audio_first(tmp_path):
    shots = [
        reel.Shot(0, 4000, tmp_path / "a.jpg", "image", "credit A"),
        reel.Shot(4000, 9000, tmp_path / "c.webm", "video", "credit C"),
    ]
    cmd = reel.command(
        tmp_path / "ep.m4a", shots, tmp_path / "out.mp4", 9.0, work=tmp_path
    )
    assert cmd[0].endswith("ffmpeg") or cmd[0] == "ffmpeg"
    ins = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-i"]
    assert ins[0].endswith("ep.m4a") and len(ins) == 3
    assert "-loop" in cmd and "-stream_loop" in cmd
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "zoompan" in graph  # the still moves
    assert "showwaves" in graph  # gaps and the start show the audio
    assert graph.count("overlay=") == 2
    assert cmd[-1].endswith("out.mp4")


def test_credits_go_in_text_files_not_into_the_filtergraph(tmp_path):
    shots = [reel.Shot(0, 4000, tmp_path / "a.jpg", "image", "It's: 100% [odd], \\ ok")]
    cmd = reel.command(
        tmp_path / "ep.m4a", shots, tmp_path / "o.mp4", 5.0, work=tmp_path
    )
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "odd" not in graph  # nothing from the credit needs escaping
    assert "textfile=" in graph
    texts = [p.read_text() for p in tmp_path.glob("credit*.txt")]
    assert "It's: 100% [odd], \\ ok" in texts


def test_end_card_lengthens_the_reel_and_lists_every_credit(tmp_path):
    shots = [
        reel.Shot(0, 4000, tmp_path / "a.jpg", "image", "credit A"),
        reel.Shot(4000, 9000, tmp_path / "c.jpg", "image", "credit C"),
    ]
    cmd = reel.command(
        tmp_path / "ep.m4a", shots, tmp_path / "o.mp4", 9.0, work=tmp_path, end_card_s=4
    )
    assert out_t(cmd) == "13.000"
    card = (tmp_path / "endcard.txt").read_text()
    assert "credit A" in card and "credit C" in card


def test_no_end_card_when_zero(tmp_path):
    cmd = reel.command(
        tmp_path / "ep.m4a", [], tmp_path / "o.mp4", 9.0, work=tmp_path, end_card_s=0
    )
    assert out_t(cmd) == "9.000"
    assert not (tmp_path / "endcard.txt").exists()


@pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")
def test_the_reel_really_renders(tmp_path):
    def run(*a):
        subprocess.run([FFMPEG, "-v", "error", "-y", *a], check=True)

    audio = tmp_path / "ep.m4a"
    run("-f", "lavfi", "-i", "sine=frequency=440:duration=3", str(audio))
    img = tmp_path / "a.jpg"
    run("-f", "lavfi", "-i", "color=c=red:s=640x480", "-frames:v", "1", str(img))
    clip = tmp_path / "c.webm"
    run("-f", "lavfi", "-i", "testsrc=s=320x240:d=1", "-c:v", "libvpx", str(clip))
    shots = [
        reel.Shot(0, 1500, img, "image", "Red by Ann, CC0"),
        reel.Shot(1500, 3000, clip, "video", "Test by Bob, CC BY"),
    ]
    out = tmp_path / "reel.mp4"
    reel.render(audio, shots, out, work=tmp_path / "w", size=(270, 480), end_card_s=1)
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "width=270" in probe and "height=480" in probe
    assert "codec_type=audio" in probe
    dur = float(probe.split("duration=")[1].split()[0])
    assert 3.8 < dur < 4.3  # 3 s of audio and a 1 s end card


def test_render_reports_ffmpeg_failure(tmp_path):
    shots = [reel.Shot(0, 1000, tmp_path / "missing.jpg", "image", "c")]
    with pytest.raises(reel.ReelError):
        reel.render(
            tmp_path / "nope.m4a", shots, tmp_path / "o.mp4", work=tmp_path / "w"
        )
