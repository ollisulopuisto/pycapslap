import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.broll import looks, reel
from app.services.broll.picks import Picks
from app.services.broll.assets import Asset

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="needs ffmpeg")


# --- the pure choices --------------------------------------------------------


def test_motions_cycle_so_neighbouring_shots_differ():
    seen = [looks.auto_motion(i) for i in range(len(looks.MOTIONS))]
    assert len(set(seen)) == len(looks.MOTIONS)
    assert looks.auto_motion(0) == looks.auto_motion(len(looks.MOTIONS))
    assert all(looks.auto_motion(i) != looks.auto_motion(i + 1) for i in range(12))


def test_every_motion_has_an_opposite_that_is_another_motion():
    for m in looks.MOTIONS:
        o = looks.opposite(m)
        assert o in looks.MOTIONS and o != m and looks.opposite(o) == m


def test_a_tall_picture_fills_the_frame_and_a_wide_or_square_one_is_fitted():
    assert looks.auto_layout((1080, 1920)) == "fill"
    assert looks.auto_layout((900, 1200)) == "fill"  # 3:4 loses a quarter, no more
    assert looks.auto_layout((1000, 1000)) == "blur"
    assert looks.auto_layout((1920, 1080)) == "blur"
    assert looks.auto_layout(None) == "fill"


def test_zoompan_reaches_its_target_over_the_whole_shot():
    # 60 frames: the last one (on=59) is progress 1, whatever the length.
    zi = looks.zoompan("zoom_in", 60, 270, 480)
    assert "z='1+0.1500*min(on/59,1)'" in zi and "s=270x480" in zi
    zo = looks.zoompan("zoom_out", 60, 270, 480)
    assert "z='1.1500-0.1500*min(on/59,1)'" in zo
    pr = looks.zoompan("pan_right", 60, 270, 480)
    assert "z='1.2'" in pr and "x='(iw-iw/zoom)*min(on/59,1)'" in pr
    pl = looks.zoompan("pan_left", 60, 270, 480)
    assert "x='(iw-iw/zoom)*(1-min(on/59,1))'" in pl


def test_a_one_frame_shot_does_not_divide_by_zero():
    assert "on/1" in looks.zoompan("zoom_in", 1, 270, 480)


def test_every_motion_makes_a_filter():
    for m in looks.MOTIONS:
        assert looks.zoompan(m, 30, 270, 480).startswith("zoompan=")


# --- transitions -------------------------------------------------------------


def shot(a, b, name="a.jpg", **kw):
    return reel.Shot(a, b, Path(name), "image", f"credit {name}", **kw)


def test_the_first_shot_arrives_by_the_chosen_style_and_a_cut_style_is_all_cuts():
    s = reel.assign_transitions([shot(0, 4000), shot(4000, 8000)], "cut")
    assert [x.transition for x in s] == ["cut", "cut"]
    s = reel.assign_transitions([shot(0, 4000), shot(4000, 8000)], "fade")
    assert [x.transition for x in s] == ["fade", "fade"]


def test_mixed_style_varies_the_arrivals():
    shots = [shot(i * 4000, (i + 1) * 4000) for i in range(8)]
    kinds = [x.transition for x in reel.assign_transitions(shots, "mixed")]
    assert {"fade", "whip", "slide"} <= set(kinds)
    assert all(a != b for a, b in zip(kinds, kinds[1:]))


def test_a_transition_is_shorter_than_the_shots_it_joins():
    a, b = shot(0, 600), shot(600, 5000)
    assert reel.transition_seconds("fade", a, b) <= 0.4 * 0.6 + 1e-9
    assert reel.transition_seconds("whip", shot(0, 4000), shot(4000, 8000)) == 0.25
    assert reel.transition_seconds("cut", a, b) == 0.0


def test_only_adjacent_shots_overlap():
    assert reel.adjacent(shot(0, 4000), shot(4000, 8000))
    assert reel.adjacent(shot(0, 4000), shot(4030, 8000))  # a hair apart
    assert not reel.adjacent(shot(0, 4000), shot(6000, 8000))


def test_an_incoming_whip_slides_in_from_the_right_and_blurs():
    shots = reel.assign_transitions([shot(0, 4000), shot(4000, 8000)], "whip")
    expr = reel.overlay_x(shots, 1, width=1080)
    assert "1080*(1-" in expr and "clip((t-4)/0.25,0,1)" in expr
    assert reel.blur_enable(shots, 1) is not None


def test_an_outgoing_whip_leaves_to_the_left():
    shots = reel.assign_transitions([shot(0, 4000), shot(4000, 8000)], "whip")
    expr = reel.overlay_x(shots, 0, width=1080)
    assert "-1080*" in expr and "gte(t,4)" in expr


def test_a_slide_covers_the_old_shot_without_moving_it():
    shots = reel.assign_transitions([shot(0, 4000), shot(4000, 8000)], "slide")
    assert "gte" not in reel.overlay_x(
        shots, 0, width=1080
    )  # it is covered, not pushed
    assert "1080*(1-" in reel.overlay_x(shots, 1, width=1080)
    assert reel.blur_enable(shots, 1) is None


def test_the_old_shot_stays_through_the_transition_so_there_is_something_to_fade_over():
    shots = reel.assign_transitions([shot(0, 4000), shot(4000, 8000)], "fade")
    assert reel.extension(shots, 0) == 0.4
    assert reel.extension(shots, 1) == 0.0  # last shot, nothing follows
    assert (
        reel.extension(
            reel.assign_transitions([shot(0, 4000), shot(4000, 8000)], "cut"), 0
        )
        == 0.0
    )
    gap = reel.assign_transitions([shot(0, 3000), shot(5000, 8000)], "fade")
    assert reel.extension(gap, 0) == 0.0


# --- choosing and picking -----------------------------------------------------


def asset(title, w=1920, h=1080, kind="image"):
    return Asset(
        title=title,
        kind=kind,
        url=f"u/{title}",
        page_url=f"p/{title}",
        license="CC0",
        width=w,
        height=h,
    )


def proposals():
    return [
        {
            "startMs": 0,
            "endMs": 4000,
            "text": "t",
            "query": "q",
            "chosen": None,
            "candidates": [
                asset("wide.jpg").to_dict(),
                asset("tall.jpg", 900, 1600).to_dict(),
                asset("sq.jpg", 800, 800).to_dict(),
            ],
        },
        {
            "startMs": 4000,
            "endMs": 8000,
            "text": "u",
            "query": "r",
            "chosen": None,
            "candidates": [asset("tall.jpg", 900, 1600).to_dict()],
        },
    ]


def test_a_stack_takes_a_second_candidate():
    p = Picks(proposals())
    p.accept(0, 0, also=2)
    (choice,) = p.accepted()
    assert [a.title for a in choice.assets] == ["wide.jpg", "sq.jpg"]
    assert choice.layout == "stack"


def test_the_second_candidate_has_to_exist_and_differ():
    p = Picks(proposals())
    with pytest.raises(IndexError):
        p.accept(0, 0, also=9)
    with pytest.raises(ValueError):
        p.accept(0, 1, also=1)


def test_a_layout_can_be_forced_and_otherwise_follows_the_picture():
    p = Picks(proposals())
    p.accept(0, 0)  # wide
    p.accept(1, 0)  # tall
    wide, tall = p.accepted()
    assert wide.layout is None and tall.layout is None  # decided when the reel is built
    q = Picks(proposals())
    q.accept(0, 1, layout="blur")
    assert q.accepted()[0].layout == "blur"


def test_choices_survive_a_round_trip_through_json():
    p = Picks(proposals())
    p.accept(0, 0, also=1)
    q = Picks(p.data())
    assert [a.title for a in q.accepted()[0].assets] == ["wide.jpg", "tall.jpg"]


def test_shots_pick_layout_from_the_picture_and_cycle_the_motion(tmp_path):
    p = Picks(proposals())
    p.accept(0, 0)  # wide image: blurred fit
    p.accept(1, 0)  # tall image: fill
    files = {"wide.jpg": tmp_path / "w.jpg", "tall.jpg": tmp_path / "t.jpg"}
    a, b = reel.shots(p.accepted(), files, transition="fade")
    assert (a.layout, b.layout) == ("blur", "fill")
    assert a.motion != b.motion
    assert (a.transition, b.transition) == ("fade", "fade")


def test_a_stack_shot_has_two_parts_two_motions_and_both_credits(tmp_path):
    p = Picks(proposals())
    p.accept(0, 0, also=2)
    files = {"wide.jpg": tmp_path / "w.jpg", "sq.jpg": tmp_path / "s.jpg"}
    (s,) = reel.shots(p.accepted(), files, transition="cut")
    assert s.layout == "stack" and s.second is not None
    assert s.second.motion == looks.opposite(s.motion)
    assert len(s.credit_lines) == 2
    assert "wide.jpg" in s.credit_lines[0] and "sq.jpg" in s.credit_lines[1]


# --- the picture itself ------------------------------------------------------


def run(*a):
    subprocess.run([FFMPEG, "-v", "error", "-y", *a], check=True)


def solid(tmp_path, name, color, size="640x360"):
    out = tmp_path / name
    run("-f", "lavfi", "-i", f"color=c={color}:s={size}", "-frames:v", "1", str(out))
    return out


def tone(tmp_path, seconds):
    out = tmp_path / "ep.m4a"
    run("-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", str(out))
    return out


def pixel(video, t, x, y, size=(180, 320)):
    """The RGB of one pixel of the frame at time t."""
    raw = subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-ss",
            str(t),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    assert len(raw) == size[0] * size[1] * 3, "no frame at that time"
    i = (y * size[0] + x) * 3
    return tuple(raw[i : i + 3])


def reddish(c):
    return c[0] > 150 and c[1] < 90 and c[2] < 90


def bluish(c):
    return c[2] > 150 and c[0] < 90 and c[1] < 90


def render(tmp_path, shots, seconds, size=(180, 320), end_card_s=0):
    out = tmp_path / "reel.mp4"
    reel.render(
        tone(tmp_path, seconds),
        shots,
        out,
        work=tmp_path / "w",
        size=size,
        end_card_s=end_card_s,
        hw=False,
    )
    return out


@needs_ffmpeg
def test_a_stack_puts_one_picture_over_the_other(tmp_path):
    red = solid(tmp_path, "r.png", "red")
    blue = solid(tmp_path, "b.png", "blue")
    s = reel.Shot(
        0,
        2000,
        red,
        "image",
        "R",
        layout="stack",
        second=reel.Part(blue, "image", "B", None, "zoom_out"),
        motion="zoom_in",
    )
    out = render(tmp_path, [s], 2)
    assert reddish(pixel(out, 1.0, 90, 40))  # top half
    assert bluish(pixel(out, 1.0, 90, 200))  # bottom half


@needs_ffmpeg
def test_a_wide_picture_is_fitted_over_a_blurred_copy_not_cropped(tmp_path):
    # left third red, middle white, right third blue
    img = tmp_path / "wide.png"
    run(
        "-f",
        "lavfi",
        "-i",
        "color=c=white:s=900x300",
        "-vf",
        "drawbox=x=0:y=0:w=300:h=300:color=red:t=fill,drawbox=x=600:y=0:w=300:h=300:color=blue:t=fill",
        "-frames:v",
        "1",
        str(img),
    )
    f = render_one(tmp_path / "fill", img, "fill")
    b = render_one(tmp_path / "blur", img, "blur")
    # the centre row's left edge: fill has cropped the red away, the fit shows it
    assert not reddish(pixel(f, 1.0, 4, 160))
    assert reddish(pixel(b, 1.0, 4, 160))
    # above and below the fitted picture the blurred copy fills the frame: not black
    top = pixel(b, 1.0, 90, 8)
    assert sum(top) > 120


def render_one(folder, img, layout, motion="zoom_in", seconds=2):
    s = reel.Shot(0, seconds * 1000, img, "image", "c", layout=layout, motion=motion)
    folder.mkdir(exist_ok=True)
    out = folder / "reel.mp4"
    reel.render(
        tone(folder, seconds),
        [s],
        out,
        work=folder / "w",
        size=(180, 320),
        end_card_s=0,
        hw=False,
    )
    return out


@needs_ffmpeg
@pytest.mark.parametrize("motion", looks.MOTIONS)
def test_every_ken_burns_motion_renders(tmp_path, motion):
    img = solid(tmp_path, "a.png", "green")
    out = render_one(tmp_path / motion, img, "fill", motion=motion, seconds=1)
    assert out.stat().st_size > 0


@needs_ffmpeg
def test_a_pan_really_moves_the_picture(tmp_path):
    # left half red, right half blue: panning right shows more blue as it goes
    img = tmp_path / "rb.png"
    run(
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=1600x1600",
        "-vf",
        "drawbox=x=0:y=0:w=800:h=1600:color=red:t=fill",
        "-frames:v",
        "1",
        str(img),
    )
    out = render_one(tmp_path / "p", img, "fill", motion="pan_right", seconds=3)
    early, late = pixel(out, 0.1, 90, 160), pixel(out, 2.8, 90, 160)
    assert late[2] > early[2]  # bluer as the view slides right


def two_colours(tmp_path, kind_a="red", kind_b="blue"):
    return solid(tmp_path, "r.png", kind_a), solid(tmp_path, "b.png", kind_b)


def two_shots(tmp_path, transition):
    a, b = two_colours(tmp_path)
    shots = [
        reel.Shot(0, 2000, a, "image", "A", layout="fill", motion="pan_right"),
        reel.Shot(2000, 4000, b, "image", "B", layout="fill", motion="pan_left"),
    ]
    return reel.assign_transitions(shots, transition)


@needs_ffmpeg
def test_a_cut_switches_at_once(tmp_path):
    out = render(tmp_path, two_shots(tmp_path, "cut"), 4)
    assert reddish(pixel(out, 1.9, 90, 160)) and bluish(pixel(out, 2.1, 90, 160))


@needs_ffmpeg
def test_a_crossfade_passes_through_a_mix(tmp_path):
    out = render(tmp_path, two_shots(tmp_path, "fade"), 4)
    assert reddish(pixel(out, 1.5, 90, 160)) and bluish(pixel(out, 2.6, 90, 160))
    mid = pixel(out, 2.2, 90, 160)  # 0.4 s fade starting at 2.0, halfway
    assert mid[0] > 40 and mid[2] > 40, mid


@needs_ffmpeg
def test_a_slide_brings_the_new_shot_in_over_the_old_one(tmp_path):
    out = render(tmp_path, two_shots(tmp_path, "slide"), 4)
    left, right = pixel(out, 2.17, 20, 160), pixel(out, 2.17, 160, 160)
    assert reddish(left) and bluish(
        right
    )  # mid-slide: old on the left, new coming in on the right
    assert bluish(pixel(out, 2.6, 20, 160))


@needs_ffmpeg
def test_a_whip_pushes_the_old_shot_out_to_the_left(tmp_path):
    out = render(tmp_path, two_shots(tmp_path, "whip"), 4)
    left, right = pixel(out, 2.125, 20, 160), pixel(out, 2.125, 160, 160)
    assert reddish(left) and bluish(right)
    assert bluish(pixel(out, 2.6, 20, 160)) and reddish(pixel(out, 1.8, 160, 160))


@needs_ffmpeg
def test_a_video_clip_can_be_stacked_and_blurred(tmp_path):
    clip = tmp_path / "c.webm"
    run("-f", "lavfi", "-i", "testsrc=s=320x240:d=1", "-c:v", "libvpx", str(clip))
    img = solid(tmp_path, "r.png", "red")
    s = reel.Shot(
        0,
        2000,
        clip,
        "video",
        "V",
        layout="stack",
        second=reel.Part(img, "image", "I", None, "zoom_in"),
        motion="zoom_in",
    )
    out = render(tmp_path, [s], 2)
    assert reddish(pixel(out, 1.0, 90, 200))  # the still is the bottom half
    b = reel.Shot(0, 2000, clip, "video", "V", layout="blur", size=(320, 240))
    out2 = tmp_path / "blur.mp4"
    reel.render(
        tone(tmp_path, 2),
        [b],
        out2,
        work=tmp_path / "w2",
        size=(180, 320),
        end_card_s=0,
        hw=False,
    )
    assert out2.stat().st_size > 0


@needs_ffmpeg
def test_credits_of_a_stack_are_two_lines_and_both_reach_the_end_card(tmp_path):
    red, blue = two_colours(tmp_path)
    s = reel.Shot(
        0,
        2000,
        red,
        "image",
        "Red by Ann, CC0",
        layout="stack",
        second=reel.Part(blue, "image", "Blue by Bob, CC BY", None, "zoom_out"),
    )
    cmd = reel.command(
        tone(tmp_path, 2),
        [s],
        tmp_path / "o.mp4",
        2.0,
        tmp_path / "w",
        size=(180, 320),
        end_card_s=3,
        hw=False,
    )
    assert cmd
    assert (tmp_path / "w" / "credit0.txt").read_text().count("\n") >= 1
    card = (tmp_path / "w" / "endcard.txt").read_text()
    assert "Red by Ann" in card and "Blue by Bob" in card


def loud_tone(folder, seconds):
    folder.mkdir(exist_ok=True)
    out = folder / "loud.m4a"
    run("-f", "lavfi", "-i", f"aevalsrc=0.95*sin(2*PI*440*t):d={seconds}", str(out))
    return out


@needs_ffmpeg
@pytest.mark.parametrize("layout", ["fill", "blur"])
def test_a_transparent_picture_does_not_let_the_waveform_show_through(tmp_path, layout):
    # A red square on a fully transparent ground, with white underneath the
    # transparency, as cut-out PNGs from Commons often have.
    logo = tmp_path / "logo.png"
    run(
        "-f",
        "lavfi",
        "-i",
        "color=c=white@0.0:s=640x360,format=rgba",
        "-vf",
        "drawbox=x=280:y=140:w=80:h=80:color=red@1:t=fill",
        "-frames:v",
        "1",
        str(logo),
    )
    s = reel.Shot(0, 2000, logo, "image", "c", layout=layout)
    out = tmp_path / "reel.mp4"
    reel.render(
        loud_tone(tmp_path, 2),
        [s],
        out,
        work=tmp_path / "w",
        size=(180, 320),
        end_card_s=0,
        hw=False,
    )
    # a row well away from the red square, where only the ground is
    row = [pixel(out, 1.0, x, 40) for x in range(0, 180, 3)]
    assert not any(sum(p) > 300 for p in row), "waveform lines show through the ground"
    assert max(max(p) for p in row) < 120
