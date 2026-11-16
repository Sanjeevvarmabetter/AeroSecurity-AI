"""Synthetic CSV fixtures (test data, not real observations)."""

import io
import tarfile
from pathlib import Path

import pytest

from app.ingestion.opensky_csv import DatasetError, OpenSkyCsvProvider
from app.ingestion.schema import NormalizedObservation, Rejection

HEADER = "time,icao24,lat,lon,velocity,heading,vertrate,callsign,onground,alert,spi,squawk,baroaltitude,geoaltitude,lastposupdate,lastcontact,serials\n"
ROWS = (
    "1790739541,a1b2c3,26.4,51.3,226.4,289.5,0.0,TST1 ,False,False,False,0527,9753.6,10340.3,1790739540.9,1790739540.9,[1]\n"
    "1790739542,a1b2c3,,,,,,TST1 ,False,False,False,,,,,1790739541.9,[1]\n"
    "1790739543,not-hex,26.4,51.3,1,1,0,X,False,False,False,,,,1790739543,1790739543,[1]\n"
)


def write_csv(tmp_path: Path) -> Path:
    p = tmp_path / "s.csv"
    p.write_text(HEADER + ROWS)
    return p


def write_tar(tmp_path: Path, members: dict[str, bytes]) -> Path:
    p = tmp_path / "a.tar.gz"
    with tarfile.open(p, "w:gz") as t:
        for name, data in members.items():
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    return p


def test_csv_parsed_with_rejection_and_missing_position(tmp_path: Path) -> None:
    out = list(OpenSkyCsvProvider(write_csv(tmp_path)).fetch())
    assert [type(x) for x in out] == [NormalizedObservation, NormalizedObservation, Rejection]
    first, second, rej = out
    assert isinstance(first, NormalizedObservation) and isinstance(second, NormalizedObservation)
    assert first.lat == 26.4 and first.observed_at.timestamp() == pytest.approx(1790739540.9)
    assert second.lat is None and second.raw["issues"] == ["missing_coordinates"]
    assert isinstance(rej, Rejection) and rej.reason == "invalid_icao24" and rej.row == 4


def test_tar_member_streamed(tmp_path: Path) -> None:
    p = write_tar(
        tmp_path, {"x/foo_state_vectors_data4.csv": (HEADER + ROWS).encode(), "x/README.txt": b"hi"}
    )
    assert len(list(OpenSkyCsvProvider(p).fetch())) == 3


def test_tar_traversal_names_never_touch_disk(tmp_path: Path) -> None:
    p = write_tar(tmp_path, {"../../evil_state_vectors_data4.csv": (HEADER + ROWS).encode()})
    assert len(list(OpenSkyCsvProvider(p).fetch())) == 3  # read in memory only
    assert not (tmp_path.parent.parent / "evil_state_vectors_data4.csv").exists()


def test_ambiguous_or_missing_member_rejected(tmp_path: Path) -> None:
    two = write_tar(tmp_path, {"a_state_vectors_data4.csv": b"x", "b_state_vectors_data4.csv": b"x"})
    with pytest.raises(DatasetError):
        list(OpenSkyCsvProvider(two).fetch())


def test_limits_and_format_enforced(tmp_path: Path) -> None:
    p = write_csv(tmp_path)
    with pytest.raises(DatasetError, match="size"):
        list(OpenSkyCsvProvider(p, max_bytes=10).fetch())
    with pytest.raises(DatasetError, match="row limit"):
        list(OpenSkyCsvProvider(p, max_rows=1).fetch())
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    with pytest.raises(DatasetError, match="missing required"):
        list(OpenSkyCsvProvider(bad).fetch())


def test_symlink_refused(tmp_path: Path) -> None:
    link = tmp_path / "link.csv"
    link.symlink_to(write_csv(tmp_path))
    with pytest.raises(DatasetError):
        list(OpenSkyCsvProvider(link).fetch())
