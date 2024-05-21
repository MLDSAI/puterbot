"""Implements basic CRUD operations for interacting with a database.

Module: crud.py
"""

from typing import Any, TypeVar
import asyncio

from loguru import logger
import sqlalchemy as sa

from openadapt import utils
from openadapt.config import config
from openadapt.db.db import Session
from openadapt.models import (
    ActionEvent,
    MemoryStat,
    PerformanceStat,
    Recording,
    Screenshot,
    ScrubbedRecording,
    WindowEvent,
    copy_sa_instance,
)
from openadapt.privacy.base import ScrubbingProvider

BATCH_SIZE = 1

db = Session()
lock = asyncio.Event()
lock.set()
action_events = []
screenshots = []
window_events = []
performance_stats = []
memory_stats = []


def _insert(
    event_data: dict[str, Any],
    table: sa.Table,
    buffer: list[dict[str, Any]] | None = None,
) -> sa.engine.Result | None:
    """Insert using Core API for improved performance (no rows are returned).

    Args:
        event_data (dict): The event data to be inserted.
        table (sa.Table): The SQLAlchemy table to insert the data into.
        buffer (list, optional): A buffer list to store the inserted objects
            before committing. Defaults to None.

    Returns:
        sa.engine.Result | None: The SQLAlchemy Result object if a buffer is
          not provided. None if a buffer is provided.
    """
    db_obj = {column.name: None for column in table.__table__.columns}
    for key in db_obj:
        if key in event_data:
            val = event_data[key]
            db_obj[key] = val
            del event_data[key]

    # make sure all event data was saved
    assert not event_data, event_data

    if buffer is not None:
        buffer.append(db_obj)

    if buffer is None or len(buffer) >= BATCH_SIZE:
        to_insert = buffer or [db_obj]
        result = db.execute(sa.insert(table), to_insert)
        db.commit()
        if buffer:
            buffer.clear()
        # Note: this does not contain the inserted row(s)
        return result


def insert_action_event(
    recording: Recording,
    event_timestamp: int,
    event_data: dict[str, Any],
) -> None:
    """Insert an action event into the database.

    Args:
        recording (Recording): The recording object.
        event_timestamp (int): The timestamp of the event.
        event_data (dict): The data of the event.
    """
    event_data = {
        **event_data,
        "timestamp": event_timestamp,
        "recording_id": recording.id,
        "recording_timestamp": recording.timestamp,
    }
    _insert(event_data, ActionEvent, action_events)


def insert_screenshot(
    recording: Recording,
    event_timestamp: int,
    event_data: dict[str, Any],
) -> None:
    """Insert a screenshot into the database.

    Args:
        recording (Recording): The recording object.
        event_timestamp (int): The timestamp of the event.
        event_data (dict): The data of the event.
    """
    event_data = {
        **event_data,
        "timestamp": event_timestamp,
        "recording_id": recording.id,
        "recording_timestamp": recording.timestamp,
    }
    _insert(event_data, Screenshot, screenshots)


def insert_window_event(
    recording: Recording,
    event_timestamp: int,
    event_data: dict[str, Any],
) -> None:
    """Insert a window event into the database.

    Args:
        recording (Recording): The recording object.
        event_timestamp (int): The timestamp of the event.
        event_data (dict): The data of the event.
    """
    event_data = {
        **event_data,
        "timestamp": event_timestamp,
        "recording_id": recording.id,
        "recording_timestamp": recording.timestamp,
    }
    _insert(event_data, WindowEvent, window_events)


def insert_perf_stat(
    recording: Recording,
    event_type: str,
    start_time: float,
    end_time: float,
) -> None:
    """Insert an event performance stat into the database.

    Args:
        recording (Recording): The recording object.
        event_type (str): The type of the event.
        start_time (float): The start time of the event.
        end_time (float): The end time of the event.
    """
    event_perf_stat = {
        "recording_timestamp": recording.timestamp,
        "recording_id": recording.id,
        "event_type": event_type,
        "start_time": start_time,
        "end_time": end_time,
    }
    _insert(event_perf_stat, PerformanceStat, performance_stats)


def get_perf_stats(
    recording: Recording, session: sa.orm.Session = None
) -> list[PerformanceStat]:
    """Get performance stats for a given recording.

    Args:
        recording (Recording): The recording object.
        session (sa.orm.Session, optional): The database session. Defaults to None.

    Returns:
        list[PerformanceStat]: A list of performance stats for the recording.
    """
    _db = session or db
    return (
        _db.query(PerformanceStat)
        .filter(PerformanceStat.recording_id == recording.id)
        .order_by(PerformanceStat.start_time)
        .all()
    )


def insert_memory_stat(
    recording: Recording,
    memory_usage_bytes: int,
    timestamp: int,
) -> None:
    """Insert memory stat into db."""
    memory_stat = {
        "recording_timestamp": recording.timestamp,
        "recording_id": recording.id,
        "memory_usage_bytes": memory_usage_bytes,
        "timestamp": timestamp,
    }
    _insert(memory_stat, MemoryStat, memory_stats)


def get_memory_stats(
    recording: Recording, session: sa.orm.Session = None
) -> list[MemoryStat]:
    """Return memory stats for a given recording.

    Args:
        recording (Recording): The recording object.
        session (sa.orm.Session, optional): The database session. Defaults to None.

    Returns:
        list[MemoryStat]: A list of memory stats for the recording.

    """
    _db = session or db
    return (
        _db.query(MemoryStat)
        .filter(MemoryStat.recording_id == recording.id)
        .order_by(MemoryStat.timestamp)
        .all()
    )


def insert_recording(recording_data: Recording) -> Recording:
    """Insert the recording into to the db."""
    db_obj = Recording(**recording_data)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


def delete_recording(recording_timestamp: float) -> None:
    """Remove the recording from the db."""
    db.query(Recording).filter(Recording.timestamp == recording_timestamp).delete()
    db.commit()


def get_all_recordings(session: sa.orm.Session = None) -> list[Recording]:
    """Get all recordings.

    Args:
        session (sa.orm.Session, optional): The database session. Defaults to None.

    Returns:
        list[Recording]: A list of all original recordings.
    """
    _db = session or db
    return (
        _db.query(Recording)
        .filter(Recording.original_recording_id == None)  # noqa: E711
        .order_by(sa.desc(Recording.timestamp))
        .all()
    )


def get_all_scrubbed_recordings(
    session: sa.orm.Session = None,
) -> list[ScrubbedRecording]:
    """Get all scrubbed recordings.

    Args:
        session (sa.orm.Session, optional): The database session. Defaults to None.

    Returns:
        list[ScrubbedRecording]: A list of all scrubbed recordings.
    """
    _db = session or db
    return _db.query(ScrubbedRecording).all()


def get_latest_recording(session: sa.orm.Session = None) -> Recording:
    """Get the latest recording.

    Args:
        session (sa.orm.Session, optional): The database session. Defaults to None.

    Returns:
        Recording: The latest recording object.
    """
    _db = session or db
    return _db.query(Recording).order_by(sa.desc(Recording.timestamp)).limit(1).first()


def get_recording_by_id(recording_id: int, session: sa.orm.Session = None) -> Recording:
    """Get the recording by an id.

    Args:
        recording_id (int): The id of the recording.
        session (sa.orm.Session, optional): The database session. Defaults to None.

    Returns:
        Recording: The latest recording object.
    """
    _db = session or db
    return _db.query(Recording).filter_by(id=recording_id).first()


def get_recording(timestamp: float, session: sa.orm.Session = None) -> Recording:
    """Get a recording by timestamp.

    Args:
        timestamp (float): The timestamp of the recording.
        session (sa.orm.Session, optional): The database session. Defaults to None.

    Returns:
        Recording: The recording object.
    """
    _db = session or db
    return _db.query(Recording).filter(Recording.timestamp == timestamp).first()


BaseModelType = TypeVar("BaseModelType")


def _get(
    table: BaseModelType, recording_id: int, session: sa.orm.Session = None
) -> list[BaseModelType]:
    """Retrieve records from the database table based on the recording timestamp.

    Args:
        table (BaseModel): The database table to query.
        recording_id (int): The recording id.
        session (sa.orm.Session, optional): The database session. Defaults to None.

    Returns:
        list[BaseModel]: A list of records retrieved from the database table,
          ordered by timestamp.
    """
    _db = session or db
    return (
        _db.query(table)
        .filter(table.recording_id == recording_id)
        .order_by(table.timestamp)
        .all()
    )


def get_action_events(
    recording: Recording,
    session: sa.orm.Session = None,
) -> list[ActionEvent]:
    """Get action events for a given recording.

    Args:
        recording (Recording): The recording object.
        session (sa.orm.Session, optional): The database session. Defaults to None.

    Returns:
        list[ActionEvent]: A list of action events for the recording.
    """
    assert recording, "Invalid recording."
    action_events = _get(ActionEvent, recording.id, session)
    # filter out stop sequences listed in STOP_SEQUENCES and Ctrl + C
    filter_stop_sequences(action_events)
    return action_events


def get_top_level_action_events(
    recording: Recording, session: sa.orm.Session = None
) -> list[ActionEvent]:
    """Get top level action events for a given recording.

    Args:
        recording (Recording): The recording object.

    Returns:
        list[ActionEvent]: A list of top level action events for the recording.
    """
    return [
        action_event
        for action_event in get_action_events(recording, session=session)
        if not action_event.parent_id
    ]


def filter_stop_sequences(action_events: list[ActionEvent]) -> None:
    """Filter stop sequences.

    Args:
        List[ActionEvent]: A list of action events for the recording.

    Returns:
        None
    """
    # check for ctrl c first
    # TODO: want to handle sequences like ctrl c the same way as normal sequences
    if len(action_events) >= 2:
        if (
            action_events[-1].canonical_key_char == "c"
            and action_events[-2].canonical_key_name == "ctrl"
        ):
            # remove ctrl c
            # ctrl c must be held down at same time, so no release event
            action_events.pop()
            action_events.pop()
            return

    # create list of indices for sequence detection
    # one index for each stop sequence in STOP_SEQUENCES
    # start from the back of the sequence
    stop_sequence_indices = [len(sequence) - 1 for sequence in config.STOP_SEQUENCES]

    # index of sequence to remove, -1 if none found
    sequence_to_remove = -1
    # number of events to remove
    num_to_remove = 0

    for i in range(0, len(config.STOP_SEQUENCES)):
        # iterate backwards through list of action events
        for j in range(len(action_events) - 1, -1, -1):
            # never go past 1st action event, so if a sequence is longer than
            # len(action_events), it can't have been in the recording
            if (
                action_events[j].canonical_key_char
                == config.STOP_SEQUENCES[i][stop_sequence_indices[i]]
                or action_events[j].canonical_key_name
                == config.STOP_SEQUENCES[i][stop_sequence_indices[i]]
            ) and action_events[j].name == "press":
                # for press events, compare the characters
                stop_sequence_indices[i] -= 1
                num_to_remove += 1
            elif action_events[j].name == "release" and (
                action_events[j].canonical_key_char in config.STOP_SEQUENCES[i]
                or action_events[j].canonical_key_name in config.STOP_SEQUENCES[i]
            ):
                # can consider any release event with any sequence char as
                # part of the sequence
                num_to_remove += 1
            else:
                # not part of the sequence, so exit inner loop
                break

        if stop_sequence_indices[i] == -1:
            # completed whole sequence, so set sequence_to_remove to
            # current sequence and exit outer loop
            sequence_to_remove = i
            break

    if sequence_to_remove != -1:
        # remove that sequence
        for _ in range(0, num_to_remove):
            action_events.pop()


def save_screenshot_diff(screenshots: list[Screenshot]) -> list[Screenshot]:
    """Save screenshot diff data to the database.

    Args:
        screenshots (list[Screenshot]): A list of screenshots.

    Returns:
        list[Screenshot]: A list of screenshots with diff data saved to the db.
    """
    data_updated = False
    logger.info("verifying diffs for screenshots...")

    for screenshot in screenshots:
        if not screenshot.prev:
            continue
        if not screenshot.png_diff_data:
            screenshot.png_diff_data = screenshot.convert_png_to_binary(screenshot.diff)
            data_updated = True
        if not screenshot.png_diff_mask_data:
            screenshot.png_diff_mask_data = screenshot.convert_png_to_binary(
                screenshot.diff_mask
            )
            data_updated = True

    if data_updated:
        logger.info("saving screenshot diff data to db...")
        db.bulk_save_objects(screenshots)
        db.commit()

    return screenshots


def get_screenshots(
    recording: Recording, session: sa.orm.Session = None
) -> list[Screenshot]:
    """Get screenshots for a given recording.

    Args:
        recording (Recording): The recording object.
        session (sa.orm.Session, optional): The database session. Defaults to None.

    Returns:
        list[Screenshot]: A list of screenshots for the recording.
    """
    screenshots = _get(Screenshot, recording.id, session)

    for prev, cur in zip(screenshots, screenshots[1:]):
        cur.prev = prev
    if screenshots:
        screenshots[0].prev = screenshots[0]

    if config.SAVE_SCREENSHOT_DIFF:
        screenshots = save_screenshot_diff(screenshots)
    return screenshots


def get_window_events(
    recording: Recording, session: sa.orm.Session = None
) -> list[WindowEvent]:
    """Get window events for a given recording.

    Args:
        recording (Recording): The recording object.
        session (sa.orm.Session, optional): The database session. Defaults to None.

    Returns:
        list[WindowEvent]: A list of window events for the recording.
    """
    return _get(WindowEvent, recording.id, session)


def new_session() -> None:
    """Create a new database session.

    This was necessary because the database session was not being closed
    properly, and the database would become locked.
    """
    global db
    if db:
        db.close()
    db = Session()


def get_new_session() -> sa.orm.Session:
    """Get a new database session.

    Returns:
        sa.orm.Session: A new database session.
    """
    return Session()


def update_video_start_time(recording: Recording, video_start_time: float) -> None:
    """Update the video start time of a specific recording.

    Args:
        recording (Recording): The recording object to update.
        video_start_time (float): The new video start time to set.
    """
    # Update the video start time
    recording.video_start_time = video_start_time

    db.add(recording)
    # Commit the changes to the database
    db.commit()

    logger.info(
        f"Updated video start time for recording {recording.timestamp} to"
        f" {video_start_time}."
    )


def post_process_events(recording: Recording) -> None:
    """Post-process events.

    Args:
        recording (Recording): The recording to post-process.
    """
    screenshots = _get(Screenshot, recording.id)
    action_events = _get(ActionEvent, recording.id)
    window_events = _get(WindowEvent, recording.id)

    screenshot_timestamp_to_id_map = {
        screenshot.timestamp: screenshot.id for screenshot in screenshots
    }
    window_event_timestamp_to_id_map = {
        window_event.timestamp: window_event.id for window_event in window_events
    }

    for action_event in action_events:
        action_event.screenshot_id = screenshot_timestamp_to_id_map.get(
            action_event.screenshot_timestamp
        )
        action_event.window_event_id = window_event_timestamp_to_id_map.get(
            action_event.window_event_timestamp
        )

    db.commit()


def get_action_event_children(
    action_event_id: int, session: sa.orm.Session = None
) -> list[ActionEvent]:
    """Get the children of an action event.

    Args:
        action_event (ActionEvent): The action event to get children for.
        session (Session, optional): The database session to use. Defaults to None.

    Returns:
        list[ActionEvent]: A list of children action events.
    """
    _db = session or db
    return _db.query(ActionEvent).filter(ActionEvent.parent_id == action_event_id).all()


def copy_recording(recording_id: int) -> int:
    """Copy a recording.

    Args:
        recording_id (int): The recording id to copy.

    Returns:
        Recording: The copied recording.
    """
    from openadapt.events import get_events

    try:
        recording = db.query(Recording).get(recording_id)
        new_recording = copy_sa_instance(recording, original_recording_id=recording.id)
        db.add(new_recording)
        db.commit()
        db.refresh(new_recording)

        def copy_action_event(
            action_event: ActionEvent, recording_id: int
        ) -> ActionEvent:
            new_action_event = copy_sa_instance(action_event, recording_id=recording_id)
            for child in action_event.children:
                new_child = copy_action_event(child, recording_id=recording_id)
                new_action_event.children.append(new_child)
            return new_action_event

        action_events = get_events(recording)
        new_action_events = [
            copy_action_event(action_event, recording_id=new_recording.id)
            for action_event in action_events
        ]

        screenshots = [action_event.screenshot for action_event in action_events]
        window_events = [action_event.window_event for action_event in action_events]

        for i, action_event in enumerate(new_action_events):
            action_event.screenshot = copy_sa_instance(
                screenshots[i], recording_id=new_recording.id
            )
            action_event.window_event = copy_sa_instance(
                window_events[i], recording_id=new_recording.id
            )
            db.add(action_event)

        db.commit()

        return new_recording.id
    except Exception as e:
        logger.error(f"Error copying recording: {e}")
        db.rollback()
        return None


@utils.trace(logger)
def scrub_item(item_id: int, table: sa.Table, scrubber: ScrubbingProvider) -> None:
    """Scrub an item in the database.

    Args:
        item_id (int): The item id to scrub.
        table (sa.Table): The table to scrub the item from.
        scrubber (ScrubbingProvider): The scrubbing provider to use.
    """
    with get_new_session() as session:
        item = session.query(table).get(item_id)
        item.scrub(scrubber)
        session.commit()


def insert_scrubbed_recording(recording_id: int, provider: str) -> int:
    """Insert a scrubbed recording into the database.

    Args:
        recording_id (int): The recording id to scrub.
        provider (str): The scrubbing provider to use.
    """
    scrubbed_recording = ScrubbedRecording(
        recording_id=recording_id,
        provider=provider,
        timestamp=utils.set_start_time(),
    )
    db.add(scrubbed_recording)
    db.commit()
    db.refresh(scrubbed_recording)
    scrubbed_recording_id = scrubbed_recording.id
    return scrubbed_recording_id


def mark_scrubbing_complete(scrubbed_recording_id: int) -> None:
    """Mark scrubbing as complete for a recording."""
    session = get_new_session()
    scrubbed_recording = session.query(ScrubbedRecording).get(scrubbed_recording_id)
    scrubbed_recording.scrubbed = True
    session.commit()
    session.close()


async def acquire_db_lock() -> bool:
    """Check if the database is locked.

    Returns:
        bool: True if acquired the lock, False otherwise.
    """
    global db, lock
    logger.info("Database is locked. Waiting...")
    await lock.wait()
    lock.clear()
    logger.info("Database lock acquired.")
    return True


def release_db_lock() -> None:
    """Release the database lock."""
    global lock
    lock.set()
    new_session()
    logger.info("Database lock released.")
