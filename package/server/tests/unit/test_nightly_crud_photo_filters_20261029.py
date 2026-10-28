"""2026-10-29 nightly coverage for the filter builder in ``app/crud/photo.py``.

The nightly coverage scan reported ``crud/photo.py`` at 85% with 99 uncovered
lines.  Most of them sit inside ``_build_photo_filter_query``, the function
that powers the photo browser: the folder tree filters, the capture/upload
time windows, the panorama and file-type switches, the geo bounding box and
radius search, and the camera make/model filters.

Every one of those filters decides what the user sees in the browser, and a
silently wrong filter is worse than a crash: the photo simply never appears.
The tests below build a real (in-memory SQLite) library and assert on the
photos each filter actually returns.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.crud import photo as photo_crud
from app.db.base import Base
from app.db.models.album import Album, AlbumPhoto
from app.db.models.photo import FileType, ImageType, Photo
from app.db.models.photo_metadata import PhotoMetadata
from app.db.models.tag import PhotoTag, PhotoTagRelation
from app.db.models.user import User


pytestmark = [pytest.mark.smoke, pytest.mark.module_photo]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _owner(db):
    user = User(id=uuid4(), username="filters-owner", hashed_password="x")
    db.add(user)
    db.commit()
    return user.id


def _photo(db, owner_id, filename="p.jpg", **kwargs):
    photo = Photo(
        id=kwargs.pop("id", uuid4()),
        owner_id=owner_id,
        filename=filename,
        file_path=kwargs.pop("file_path", filename),
        file_type=kwargs.pop("file_type", FileType.image),
        is_deleted=kwargs.pop("is_deleted", False),
        size=kwargs.pop("size", 1),
        width=10,
        height=10,
        **kwargs,
    )
    db.add(photo)
    db.commit()
    return photo


def _metadata(db, photo, **kwargs):
    row = PhotoMetadata(photo_id=photo.id, **kwargs)
    db.add(row)
    db.commit()
    return row


def _ids(photos):
    return {photo.id for photo in photos}


# ---------------------------------------------------------------------------
# folder tree filters
# ---------------------------------------------------------------------------


def test_folder_filter_matches_an_absolute_prefix(db):
    """An absolute folder (a path starting with ``/``) matches by raw prefix."""
    owner = _owner(db)
    inside = _photo(db, owner, file_path="/photos/旅游/a.jpg")
    outside = _photo(db, owner, file_path="/other/a.jpg")

    found = photo_crud.get_all_photos(db, user_id=owner, folder="/photos")

    assert _ids(found) == {inside.id}
    assert outside.id not in _ids(found)


def test_folder_filter_matches_a_relative_folder_below_any_root(db):
    owner = _owner(db)
    nested = _photo(db, owner, file_path="D:/photos/旅游/景点/a.jpg")
    other = _photo(db, owner, file_path="D:/photos/日常/a.jpg")

    found = photo_crud.get_all_photos(db, user_id=owner, folder="旅游")

    assert _ids(found) == {nested.id}
    assert other.id not in _ids(found)


def test_folder_filter_does_not_match_a_partial_folder_name(db):
    owner = _owner(db)
    target = _photo(db, owner, file_path="D:/photos/旅游/a.jpg")
    sibling = _photo(db, owner, file_path="D:/photos/b旅游/a.jpg")

    found = photo_crud.get_all_photos(db, user_id=owner, folder="旅游")

    assert _ids(found) == {target.id}
    assert sibling.id not in _ids(found)


def test_folder_direct_excludes_deeper_subfolders(db):
    owner = _owner(db)
    direct = _photo(db, owner, file_path="D:/photos/旅游/a.jpg")
    deeper = _photo(db, owner, file_path="D:/photos/旅游/景点/b.jpg")

    found = photo_crud.get_all_photos(db, user_id=owner, folder="旅游", folder_direct=True)

    assert _ids(found) == {direct.id}
    assert deeper.id not in _ids(found)


def test_folder_roots_keep_only_the_orphans_at_the_root_level(db):
    owner = _owner(db)
    orphan = _photo(db, owner, file_path="D:/loose/a.jpg")
    under_root = _photo(db, owner, file_path="D:/photos/旅游/a.jpg")

    found = photo_crud.get_all_photos(
        db, user_id=owner, folder_direct=True, folder_roots=["D:/photos"]
    )

    assert _ids(found) == {orphan.id}
    assert under_root.id not in _ids(found)


# ---------------------------------------------------------------------------
# time windows
# ---------------------------------------------------------------------------


def test_capture_time_window_filters_both_ends(db):
    owner = _owner(db)
    early = _photo(db, owner, "early.jpg", photo_time=datetime(2024, 1, 1))
    middle = _photo(db, owner, "middle.jpg", photo_time=datetime(2024, 6, 1))
    late = _photo(db, owner, "late.jpg", photo_time=datetime(2024, 12, 1))

    found = photo_crud.get_all_photos(
        db, user_id=owner,
        start_time=datetime(2024, 5, 1), end_time=datetime(2024, 7, 1),
    )

    assert _ids(found) == {middle.id}
    assert early.id not in _ids(found)
    assert late.id not in _ids(found)


def test_upload_time_window_is_independent_of_the_capture_time(db):
    owner = _owner(db)
    captured_early = _photo(
        db, owner, "old.jpg", photo_time=datetime(2024, 1, 1),
        upload_time=datetime(2024, 9, 1),
    )
    captured_late = _photo(
        db, owner, "new.jpg", photo_time=datetime(2024, 1, 1),
        upload_time=datetime(2024, 2, 1),
    )

    found = photo_crud.get_all_photos(
        db, user_id=owner, uploaded_after=datetime(2024, 8, 1)
    )

    assert _ids(found) == {captured_early.id}
    assert captured_late.id not in _ids(found)


def test_upload_time_window_has_an_exclusive_upper_bound(db):
    owner = _owner(db)
    before = _photo(db, owner, "before.jpg", upload_time=datetime(2024, 8, 31))
    on_boundary = _photo(db, owner, "boundary.jpg", upload_time=datetime(2024, 9, 1))

    found = photo_crud.get_all_photos(
        db, user_id=owner, uploaded_before=datetime(2024, 9, 1)
    )

    assert _ids(found) == {before.id}
    assert on_boundary.id not in _ids(found)


def test_browse_year_buckets_by_capture_time(db):
    owner = _owner(db)
    in_2023 = _photo(db, owner, "a.jpg", photo_time=datetime(2023, 5, 5))
    in_2024 = _photo(db, owner, "b.jpg", photo_time=datetime(2024, 5, 5))

    found = photo_crud.get_all_photos(db, user_id=owner, browse_year=2024)

    assert _ids(found) == {in_2024.id}
    assert in_2023.id not in _ids(found)


def test_browse_month_narrows_the_bucket(db):
    owner = _owner(db)
    may = _photo(db, owner, "may.jpg", photo_time=datetime(2024, 5, 5))
    june = _photo(db, owner, "june.jpg", photo_time=datetime(2024, 6, 5))

    found = photo_crud.get_all_photos(db, user_id=owner, browse_year=2024, browse_month=5)

    assert _ids(found) == {may.id}
    assert june.id not in _ids(found)


def test_browse_year_zero_selects_the_photos_without_a_timestamp(db):
    owner = _owner(db)
    undated = _photo(db, owner, "undated.jpg", photo_time=None)
    dated = _photo(db, owner, "dated.jpg", photo_time=datetime(2024, 5, 5))

    found = photo_crud.get_all_photos(db, user_id=owner, browse_year=0)

    assert _ids(found) == {undated.id}
    assert dated.id not in _ids(found)


# ---------------------------------------------------------------------------
# type switches
# ---------------------------------------------------------------------------


def test_image_type_filter(db):
    """The browser sends the enum *value* (``Camera``), not the member name."""
    owner = _owner(db)
    camera = _photo(db, owner, "camera.jpg", image_type=ImageType.CAMERA)
    screenshot = _photo(db, owner, "shot.jpg", image_type=ImageType.SCREENSHOT)

    found = photo_crud.get_all_photos(db, user_id=owner, image_type="Camera")

    assert _ids(found) == {camera.id}
    assert screenshot.id not in _ids(found)


def test_image_types_filter_accepts_a_list(db):
    owner = _owner(db)
    camera = _photo(db, owner, "camera.jpg", image_type=ImageType.CAMERA)
    screenshot = _photo(db, owner, "shot.jpg", image_type=ImageType.SCREENSHOT)
    other = _photo(db, owner, "other.jpg", image_type=ImageType.OTHER)

    found = photo_crud.get_all_photos(
        db, user_id=owner, image_types=["Camera", "Screenshot"]
    )

    assert _ids(found) == {camera.id, screenshot.id}
    assert other.id not in _ids(found)


def test_panorama_switch_selects_and_excludes_the_panoramas(db):
    owner = _owner(db)
    pano = _photo(db, owner, "pano.jpg", panorama_projection="equirectangular")
    normal = _photo(db, owner, "normal.jpg")

    only_panos = photo_crud.get_all_photos(db, user_id=owner, is_panorama=True)
    without_panos = photo_crud.get_all_photos(db, user_id=owner, is_panorama=False)

    assert _ids(only_panos) == {pano.id}
    assert _ids(without_panos) == {normal.id}


def test_panorama_file_type_filter_maps_onto_the_projection_column(db):
    owner = _owner(db)
    pano = _photo(db, owner, "pano.jpg", panorama_projection="equirectangular")
    normal = _photo(db, owner, "normal.jpg")

    found = photo_crud.get_all_photos(db, user_id=owner, file_types=["panorama"])

    assert _ids(found) == {pano.id}
    assert normal.id not in _ids(found)


def test_file_type_filter_accepts_a_single_value(db):
    owner = _owner(db)
    video = _photo(db, owner, "clip.mp4", file_type=FileType.video)
    image = _photo(db, owner, "a.jpg", file_type=FileType.image)

    found = photo_crud.get_all_photos(db, user_id=owner, file_type="video")

    assert _ids(found) == {video.id}
    assert image.id not in _ids(found)


# ---------------------------------------------------------------------------
# relation filters
# ---------------------------------------------------------------------------


def test_album_filter_returns_only_the_albums_photos(db):
    owner = _owner(db)
    album = Album(name="精选", type="user", owner_id=owner)
    db.add(album)
    db.commit()
    inside = _photo(db, owner, "in.jpg")
    outside = _photo(db, owner, "out.jpg")
    db.add(AlbumPhoto(album_id=album.id, photo_id=inside.id))
    db.commit()

    found = photo_crud.get_all_photos(db, user_id=owner, album_id=album.id)

    assert _ids(found) == {inside.id}
    assert outside.id not in _ids(found)


def test_tag_filter_returns_only_the_tagged_photos(db):
    owner = _owner(db)
    tag = PhotoTag(tag_name="旅行", type="custom", owner_id=owner)
    db.add(tag)
    db.commit()
    tagged = _photo(db, owner, "tagged.jpg")
    untagged = _photo(db, owner, "untagged.jpg")
    db.add(PhotoTagRelation(tag_id=tag.id, photo_id=tagged.id))
    db.commit()

    found = photo_crud.get_all_photos(db, user_id=owner, tag_id=tag.id)

    assert _ids(found) == {tagged.id}
    assert untagged.id not in _ids(found)


def test_ids_filter_narrows_the_result_set(db):
    owner = _owner(db)
    first = _photo(db, owner, "a.jpg")
    second = _photo(db, owner, "b.jpg")

    found = photo_crud.get_all_photos(db, user_id=owner, ids=[first.id])

    assert _ids(found) == {first.id}
    assert second.id not in _ids(found)


def test_deleted_photos_are_excluded_by_default(db):
    owner = _owner(db)
    alive = _photo(db, owner, "alive.jpg")
    gone = _photo(db, owner, "gone.jpg", is_deleted=True)

    found = photo_crud.get_all_photos(db, user_id=owner)

    assert _ids(found) == {alive.id}
    assert gone.id not in _ids(found)


def test_owner_scoping_hides_other_users_photos(db):
    owner = _owner(db)
    stranger = User(id=uuid4(), username="stranger", hashed_password="x")
    db.add(stranger)
    db.commit()
    mine = _photo(db, owner, "mine.jpg")
    theirs = _photo(db, stranger.id, "theirs.jpg")

    found = photo_crud.get_all_photos(db, user_id=owner)

    assert _ids(found) == {mine.id}
    assert theirs.id not in _ids(found)


# ---------------------------------------------------------------------------
# metadata filters
# ---------------------------------------------------------------------------


def test_city_filter_matches_a_substring(db):
    owner = _owner(db)
    wuhan = _photo(db, owner, "wuhan.jpg")
    _metadata(db, wuhan, city="武汉市")
    other = _photo(db, owner, "other.jpg")
    _metadata(db, other, city="宜昌市")

    found = photo_crud.get_all_photos(db, user_id=owner, city="武汉")

    assert _ids(found) == {wuhan.id}
    assert other.id not in _ids(found)


def test_province_and_country_filters(db):
    owner = _owner(db)
    hubei = _photo(db, owner, "hubei.jpg")
    _metadata(db, hubei, province="湖北省", country="中国")
    other = _photo(db, owner, "other.jpg")
    _metadata(db, other, province="云南省", country="中国")

    by_province = photo_crud.get_all_photos(db, user_id=owner, province="湖北")
    by_country = photo_crud.get_all_photos(db, user_id=owner, country="中国")

    assert _ids(by_province) == {hubei.id}
    assert _ids(by_country) == {hubei.id, other.id}


def test_camera_make_and_model_filters(db):
    owner = _owner(db)
    canon = _photo(db, owner, "canon.jpg")
    _metadata(db, canon, make="Canon", model="EOS R5")
    nikon = _photo(db, owner, "nikon.jpg")
    _metadata(db, nikon, make="NIKON", model="D750")

    by_make = photo_crud.get_all_photos(db, user_id=owner, make="canon")
    by_model = photo_crud.get_all_photos(db, user_id=owner, model="D750")

    assert _ids(by_make) == {canon.id}
    assert _ids(by_model) == {nikon.id}


def test_bounding_box_filters_on_latitude_and_longitude(db):
    owner = _owner(db)
    inside = _photo(db, owner, "inside.jpg")
    _metadata(db, inside, latitude=30.5, longitude=114.3)
    outside = _photo(db, owner, "outside.jpg")
    _metadata(db, outside, latitude=39.9, longitude=116.4)

    found = photo_crud.get_all_photos(
        db, user_id=owner, lat_min=30.0, lat_max=31.0, lng_min=114.0, lng_max=115.0
    )

    assert _ids(found) == {inside.id}
    assert outside.id not in _ids(found)


def test_radius_search_keeps_the_nearby_photos(db):
    owner = _owner(db)
    near = _photo(db, owner, "near.jpg")
    _metadata(db, near, latitude=30.5936, longitude=114.3055)
    far = _photo(db, owner, "far.jpg")
    _metadata(db, far, latitude=39.9042, longitude=116.4074)

    found = photo_crud.get_all_photos(
        db, user_id=owner, radius=50, center_lat=30.5936, center_lng=114.3055
    )

    assert _ids(found) == {near.id}
    assert far.id not in _ids(found)


def test_radius_search_is_skipped_without_a_complete_centre(db):
    owner = _owner(db)
    photo = _photo(db, owner, "a.jpg")
    _metadata(db, photo, latitude=30.5936, longitude=114.3055)

    found = photo_crud.get_all_photos(db, user_id=owner, radius=50, center_lat=30.5936)

    assert _ids(found) == {photo.id}


# ---------------------------------------------------------------------------
# ordering and paging
# ---------------------------------------------------------------------------


def test_order_by_filename_is_ascending_by_default(db):
    owner = _owner(db)
    b = _photo(db, owner, "b.jpg")
    a = _photo(db, owner, "a.jpg")

    found = photo_crud.get_all_photos(db, user_id=owner, order_by="filename")

    assert [photo.id for photo in found] == [a.id, b.id]


def test_order_by_filename_honours_an_explicit_direction(db):
    owner = _owner(db)
    b = _photo(db, owner, "b.jpg")
    a = _photo(db, owner, "a.jpg")

    found = photo_crud.get_all_photos(db, user_id=owner, order_by="filename", order_dir="desc")

    assert [photo.id for photo in found] == [b.id, a.id]


def test_order_by_size_is_descending_by_default(db):
    owner = _owner(db)
    small = _photo(db, owner, "small.jpg", size=1)
    large = _photo(db, owner, "large.jpg", size=100)

    found = photo_crud.get_all_photos(db, user_id=owner, order_by="size")

    assert [photo.id for photo in found] == [large.id, small.id]


def test_skip_and_limit_page_the_results(db):
    owner = _owner(db)
    photos = [_photo(db, owner, f"{index}.jpg") for index in range(5)]

    found = photo_crud.get_all_photos(db, user_id=owner, order_by="filename", skip=1, limit=2)

    assert len(found) == 2
    assert photos[1].id in _ids(found)
    assert photos[2].id in _ids(found)


def test_get_random_photos_only_returns_the_owners_photos(db):
    owner = _owner(db)
    stranger = User(id=uuid4(), username="rand-stranger", hashed_password="x")
    db.add(stranger)
    db.commit()
    mine = _photo(db, owner, "mine.jpg")
    _photo(db, stranger.id, "theirs.jpg")

    found = photo_crud.get_random_photos(db, owner, limit=10)

    assert _ids(found) == {mine.id}


def test_get_random_photos_honours_the_limit(db):
    owner = _owner(db)
    for index in range(4):
        _photo(db, owner, f"{index}.jpg")

    found = photo_crud.get_random_photos(db, owner, limit=2)

    assert len(found) == 2

