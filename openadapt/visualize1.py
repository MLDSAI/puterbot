from base64 import b64encode
from functools import partial
from os import path, sep
from pprint import pformat

from loguru import logger
from nicegui import ui
from tqdm import tqdm

from openadapt import config
from openadapt.crud import get_latest_recording
from openadapt.events import get_events
from openadapt.models import Recording
from openadapt.utils import (
    EMPTY,
    configure_logging,
    display_event,
    image2utf8,
    plot_performance,
    row2dict,
    rows2dicts,
)

SCRUB = config.SCRUB_ENABLED

if SCRUB:
    # too many warnings from scrubbing
    __import__("warnings").filterwarnings("ignore", category=DeprecationWarning)
    from openadapt import scrub


LOG_LEVEL = "INFO"
MAX_EVENTS = None
MAX_TABLE_CHILDREN = 5
PROCESS_EVENTS = True


def create_tree(tree_dict: dict, max_children: str = MAX_TABLE_CHILDREN) -> list[dict]:
    tree_data = []
    for key, value in tree_dict.items():
        if value in EMPTY:
            continue
        node = {
            "id": str(key)
            + f"{(': '  + str(value)) if not isinstance(value, (dict, list)) else ''}"  # dynamic f-string
        }
        if isinstance(value, dict):
            node["children"] = create_tree(value)
        elif isinstance(value, list):
            if max_children is not None and len(value) > max_children:
                node["children"] = create_tree(
                    {i: v for i, v in enumerate(value[:max_children])}
                )
                node["children"].append({"id": "..."})
            else:
                node["children"] = create_tree({i: v for i, v in enumerate(value)})
        tree_data.append(node)
    return tree_data


def set_tree_props(tree: ui.tree) -> None:
    """
    The function sets properties for a UI tree based on values from config.

    Args:
      tree (ui.tree): A Quasar Tree.
    """
    tree._props["dense"] = config.DENSE_TREES
    tree._props["no-transition"] = config.NO_ANIMATIONS
    tree._props["default-expand-all"] = config.EXPAND_ALL
    tree._props["filter"] = ""


def set_filter(
    text: str,
    window_event_trees: list[ui.tree],
    action_event_trees: list[ui.tree],
    idx: int,
) -> None:
    window_event_trees[idx]._props["filter"] = text
    action_event_trees[idx]._props["filter"] = text
    window_event_trees[idx].update()
    action_event_trees[idx].update()


@logger.catch
def main(recording: Recording = get_latest_recording()) -> None:
    configure_logging(logger, LOG_LEVEL)

    ui_dark = ui.dark_mode(config.VISUALIZE_DARK_MODE)

    with ui.row():
        with ui.avatar(color="auto", size=128):
            logo_base64 = b64encode(
                open(
                    f"{path.dirname(__file__)}{sep}app{sep}assets{sep}logo.png", "rb"
                ).read()
            )
            img = bytes(
                f"data:image/png;base64,{(logo_base64.decode('utf-8'))}",
                encoding="utf-8",
            )
            ui.image(img.decode("utf-8"))
        ui.switch(
            text="Dark Mode",
            value=ui_dark.value,
            on_change=ui_dark.toggle,
        )

    if SCRUB:
        scrub.scrub_text(recording.task_description)
    logger.debug(f"{recording=}")

    meta = {}
    action_events = get_events(recording, process=PROCESS_EVENTS, meta=meta)
    event_dicts = rows2dicts(action_events)

    if SCRUB:
        event_dicts = scrub.scrub_list_dicts(event_dicts)
    logger.info(f"event_dicts=\n{pformat(event_dicts)}")

    recording_dict = row2dict(recording)

    if SCRUB:
        recording_dict = scrub.scrub_dict(recording_dict)

    # setup tables for recording / metadata
    recording_column = [
        (
            {
                "name": key,
                "field": key,
                "label": key,
                "sortable": False,
                "required": False,
                "align": "left",
            }
        )
        for key in recording_dict.keys()
    ]

    meta_col = [
        {
            "name": key,
            "field": key,
            "label": key,
            "sortable": False,
            "required": False,
            "align": "left",
        }
        for key in meta.keys()
    ]

    # create splitter with recording info on left and performance plot on right
    with ui.splitter(value=20).style("flex-wrap: nowrap;") as splitter:
        splitter._props["limits"] = [20, 80]

        # TODO: find a way to set "overflow: hidden;" for the splitter
        with splitter.before:
            ui.table(rows=[meta], columns=meta_col).style("min-width: 50em;")._props[
                "grid"
            ] = True
        with splitter.after:
            img = plot_performance(
                recording.timestamp,
                save_file=False,
                show=False,
                dark_mode=ui_dark.value,
            )
            with ui.interactive_image(img):
                ui.button(
                    on_click=lambda: plot_performance(
                        recording.timestamp, show=True, save_file=False
                    ),
                    icon="visibility",
                ).props("flat fab").tooltip("View")

                ui.button(
                    on_click=lambda: plot_performance(
                        recording.timestamp, save_file=True, show=False
                    ),
                    icon="save",
                ).props("flat fab").tooltip("Save as PNG")

            # this is not needed when running in browser (since users can just right click and save image)
            if config.RUN_NATIVELY:
                ui.button(
                    on_click=lambda: ui.notify("This feature is not implemented yet"),
                    icon="content_copy",
                ).props("flat fab").tooltip("Copy to clipboard")

    ui.table(rows=[recording_dict], columns=recording_column)

    interactive_images = []
    action_event_trees = []
    window_event_trees = []
    text_inputs = []

    logger.info(f"{len(action_events)=}")

    num_events = (
        min(MAX_EVENTS, len(action_events))
        if MAX_EVENTS is not None
        else len(action_events)
    )

    with tqdm(
        total=num_events,
        desc="Preparing HTML",
        unit="event",
        colour="green",
        dynamic_ncols=True,
    ) as progress:
        for idx, action_event in enumerate(action_events):
            if idx == MAX_EVENTS:
                break

            image = display_event(action_event)
            diff = display_event(action_event, diff=True)
            mask = action_event.screenshot.diff_mask

            if SCRUB:
                image = scrub.scrub_image(image)
                diff = scrub.scrub_image(diff)
                mask = scrub.scrub_image(mask)

            image_utf8 = image2utf8(image)
            diff_utf8 = image2utf8(diff)
            mask_utf8 = image2utf8(mask)
            width, height = image.size

            action_event_dict = row2dict(action_event)
            window_event_dict = row2dict(action_event.window_event)

            if SCRUB:
                action_event_dict = scrub.scrub_dict(action_event_dict)
                window_event_dict = scrub.scrub_dict(window_event_dict)

            with ui.column():
                with ui.row():
                    interactive_images.append(
                        ui.interactive_image(
                            source=image_utf8,
                        ).classes("drop-shadow-md rounded")
                    )
            with ui.splitter(value=60) as splitter:
                splitter.classes("w-full h-full")
                with splitter.after:
                    action_event_tree = create_tree(action_event_dict)
                    action_event_trees.append(
                        ui.tree(
                            action_event_tree,
                            label_key="id",
                            on_select=lambda e: ui.notify(e.value),
                        )
                    )
                    set_tree_props(action_event_trees[idx])
                with splitter.before:
                    ui.label("window_event_dict | action_event_dict:").style(
                        "font-weight: bold;"
                    )

                    def on_change_closure(e, idx):
                        return set_filter(
                            e.value, window_event_trees, action_event_trees, idx
                        )

                    text_inputs.append(
                        ui.input(
                            label="search",
                            placeholder="filter",
                            on_change=partial(
                                on_change_closure,
                                idx=idx,
                            ),
                        )
                    )
                    ui.html("<br/>")
                    window_event_tree = create_tree(window_event_dict, None)

                    window_event_trees.append(
                        ui.tree(
                            window_event_tree,
                            label_key="id",
                            on_select=lambda e: ui.notify(e.value),
                        )
                    )

                    set_tree_props(window_event_trees[idx])

            progress.update()

        progress.close()

    ui.run(
        reload=False,
        title=f"OpenAdapt: recording-{recording.id}",
        favicon="📊",
        native=config.RUN_NATIVELY,
        fullscreen=False,
    )


if __name__ == "__main__":
    main()
