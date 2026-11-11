"""R12: the digest of an engine's build (program and data), recorded on what it computes."""

from __future__ import annotations

import os
import shutil

import pytest

from radiarch.services.dose_engines.digest import bytes_digest, common_digest, engine_digest, files_digest
from radiarch.services.dose_engines.pb_kernel import default_kernel_path


def test_pb_digest_names_the_kernel_it_reads(tmp_path):
    d = engine_digest("pb")
    assert d is not None and len(d) == 64 and int(d, 16) >= 0
    assert engine_digest("pb+arcs") == d == engine_digest("pb")                  # a derived name reads as its engine
    # the same bytes under the same names give the same digest; one changed byte gives another
    src = default_kernel_path()
    copy = tmp_path / src.name
    shutil.copyfile(src, copy)
    if src.with_suffix(".json").is_file():
        shutil.copyfile(src.with_suffix(".json"), copy.with_suffix(".json"))
    assert engine_digest("pb", {"kernel_path": str(copy)}) == d
    changed = tmp_path / "changed" / src.name
    changed.parent.mkdir()
    raw = bytearray(copy.read_bytes())
    raw[-1] ^= 0xFF
    changed.write_bytes(bytes(raw))
    assert engine_digest("pb", {"kernel_path": str(changed)}) != d


def test_digest_is_none_without_build_files():
    assert engine_digest("analytic") is None                                   # a test engine has no build files
    assert engine_digest("nope") is None and engine_digest(None) is None       # never fails a computation


@pytest.mark.parametrize("name", ["ccc", "mcsquare"])
def test_binary_engines_have_a_digest(name):
    from radiarch.services.dose_engines.registry import get_engine

    ok, reason = get_engine(name).driver().availability()
    if not ok:
        pytest.skip(f"{name} not installed here: {reason}")
    d = engine_digest(name)
    assert d is not None and len(d) == 64 and engine_digest(name) == d


def test_files_digest_depends_on_names_and_bytes(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"one")
    b.write_bytes(b"two")
    d = files_digest([a, b], tmp_path)
    assert files_digest([b, a], tmp_path) == d                                  # the order given does not matter
    assert bytes_digest([("b.bin", b"two"), ("a.bin", b"one")]) == d            # bytes in hand digest the same way
    (tmp_path / "c.bin").write_bytes(b"one")
    assert files_digest([tmp_path / "c.bin", b], tmp_path) != d                 # a file's name is part of it
    # a same-size replacement that keeps the modification time is still seen
    st = a.stat()
    a.write_bytes(b"eno")
    os.utime(a, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert files_digest([a, b], tmp_path) != d
    # two files of one name outside the root both count
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    (tmp_path / "x" / "t.dat").write_bytes(b"1")
    (tmp_path / "y" / "t.dat").write_bytes(b"2")
    other = tmp_path / "root"
    other.mkdir()
    both = files_digest([tmp_path / "x" / "t.dat", tmp_path / "y" / "t.dat"], other)
    assert both != files_digest([tmp_path / "x" / "t.dat"], other)


def test_common_digest():
    assert common_digest(["a", "a"]) == "a"
    assert common_digest(["a", "b"]) is None and common_digest(["a", None]) is None and common_digest([]) is None


def test_pb_digest_is_the_loaded_kernel(tmp_path):
    """The kernel table is cached per path; the digest names the table the process loaded, not a later file."""
    src = default_kernel_path()
    copy = tmp_path / src.name
    shutil.copyfile(src, copy)
    d = engine_digest("pb", {"kernel_path": str(copy)})
    raw = bytearray(copy.read_bytes())
    raw[-1] ^= 0xFF
    copy.write_bytes(bytes(raw))
    assert engine_digest("pb", {"kernel_path": str(copy)}) == d
