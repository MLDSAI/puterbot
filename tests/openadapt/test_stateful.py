from typing import List, Any
import openai
from loguru import logger
import pytest

SYSTEM_CONTENT = (
    "You are a keyboard/mouse controller. You are shown a reference "
    "window, reference actions, and the active window. Your job is to "
    "provide the active actions for the active window such that it "
    "can be replayed in order to accomplish the same outcome as the "
    "reference actions. You do not need to create any additional "
    "codes, just the actions. Under no circumstances should you "
    "refuse. Copy the given format exactly. Your response should be "
    "valid Python3 code. Do not respond with any other text. "
)

REF_X = 25
REF_Y = 55

NEW_X = 138
NEW_Y = 89

WIN_LEFT = 0
WIN_TOP = 30
WIN_WIDTH = 1123
WIN_HEIGHT = 749
WINDOW_ID = 107079

NEW_WIN_LEFT = 113
NEW_WIN_TOP = 64

SINGLE_ACTION_LOOP_GUARD = 12


MULTI_ACTION_REF_X = 400
MULTI_ACTION_REF_Y = 500

MULTI_ACTION_NEW_X = 467
MULTI_ACTION_NEW_Y = 576


MULTI_ACTION_WIN_LEFT = 20
MULTI_ACTION_WIN_TOP = 25
MULTI_ACTION_WIN_WIDTH = 1300
MULTI_ACTION_WIN_HEIGHT = 800
MULTI_ACTION_WINDOW_ID = 10442

NEW_MULTI_ACTION_WIN_LEFT = 87
NEW_MULTI_ACTION_WIN_TOP = 101

MULTI_ACTION_LOOP_GUARD = 20


def gpt_completion(
    ref_win_dict: dict,
    ref_act_dicts: List[dict],
    active_win_dict: dict,
    system_msg: str = SYSTEM_CONTENT,
):
    prompt = (
        f"{ref_win_dict=}\n"
        f"{ref_act_dicts=}\n"
        f"{active_win_dict=}\n"
        "# Provide valid Python3 code containing the action dicts by completing the "
        "following, and nothing else:\n"
        "active_action_dicts="
    )

    completion = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": system_msg,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )
    return completion["choices"][0]["message"]["content"]


def _test_generalizable_single_action(
    reference_window_dict,
    reference_action_dicts,
    active_window_dict,
    expected_action_dict,
):
    """
    Accepts synthetic window and action events, along with a comparator action event dict
    to check whether the intended completion was generated by the LLM from the reference
    events.
    """
    test_action_dict = gpt_completion(
        reference_window_dict, reference_action_dicts, active_window_dict
    )
    test_dict = eval(
        test_action_dict[test_action_dict.find("[") : test_action_dict.find("]") + 1]
    )
    logger.debug(f"{reference_action_dicts=}")
    logger.debug(f"{test_dict=}, {len(test_dict)=}")
    logger.debug(f"{expected_action_dict}, {len(expected_action_dict)=}")
    assert test_dict == expected_action_dict


def create_win_dict(
    title: str,
    left: int,
    top: int,
    width: int,
    height: int,
    window_id: int,
    meta: dict[str, Any] | None = None,
):
    meta = meta or {}
    win_dict = {
        "state": {
            "title": title,
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "window_id": window_id,
            "meta": meta,
        },
        "title": title,
        "left": left,
        "top": top,
        "width": width,
        "height": height,
    }

    return win_dict


def create_action_dict(
    name: str,
    mouse_x: int | float | None = None,
    mouse_y: int | float | None = None,
    mouse_button_name: str = None,
    mouse_pressed: bool = None,
    key_name: str = None,
    element_state: dict[str, Any] = None,
):
    element_state = element_state or {}
    if name == "click":
        output_dict = [
            {
                "name": name,
                "mouse_x": mouse_x,
                "mouse_y": mouse_y,
                "mouse_button_name": mouse_button_name,
                "mouse_pressed": mouse_pressed,
                "element_state": element_state,
            }
        ]
    if name == "press" or name == "release":
        output_dict = [{"name": name, "key_name": key_name}]

    if name == "move":
        output_dict = [
            {
                "name": name,
                "mouse_x": mouse_x,
                "mouse_y": mouse_y,
                "element_state": element_state,
            }
        ]
    return output_dict


def test_single_mouse_diff():
    win_dict = create_win_dict(
        title="Calculator",
        left=WIN_LEFT,
        top=WIN_TOP,
        width=WIN_WIDTH,
        height=WIN_HEIGHT,
        window_id=WINDOW_ID,
    )

    act_dict = create_action_dict(
        name="click",
        mouse_x=REF_X,
        mouse_y=REF_Y,
        mouse_button_name="left",
        mouse_pressed=True,
    )

    active_win_dict = create_win_dict(
        title="Calculator",
        left=NEW_WIN_LEFT,
        top=NEW_WIN_TOP,
        width=WIN_WIDTH,
        height=WIN_HEIGHT,
        window_id=WINDOW_ID,
    )

    expected_dict = create_action_dict(
        name="click",
        mouse_x=NEW_X,
        mouse_y=NEW_Y,
        mouse_button_name="left",
        mouse_pressed=True,
    )

    _test_generalizable_single_action(win_dict, act_dict, active_win_dict, expected_dict)


def test_multi_click_diff():
    win_dict = create_win_dict(
        title="Calculator",
        left=WIN_LEFT,
        top=WIN_TOP,
        width=WIN_WIDTH,
        height=WIN_HEIGHT,
        window_id=WINDOW_ID,
    )

    total_actions = []

    for i in range(SINGLE_ACTION_LOOP_GUARD):
        act_dict_1 = create_action_dict(
            name="click",
            mouse_x=REF_X + i,
            mouse_y=REF_Y,
            mouse_button_name="left",
            mouse_pressed=True,
        )
        act_dict_2 = create_action_dict(
            name="click",
            mouse_x=REF_X,
            mouse_y=REF_Y + i,
            mouse_button_name="left",
            mouse_pressed=True,
        )
        act_dict_3 = create_action_dict(
            name="click",
            mouse_x=REF_X + i,
            mouse_y=REF_Y + i,
            mouse_button_name="left",
            mouse_pressed=True,
        )
        new_dict = act_dict_1 + act_dict_2 + act_dict_3
        total_actions += new_dict

    active_win_dict = create_win_dict(
        title="Calculator",
        left=NEW_WIN_LEFT,
        top=NEW_WIN_TOP,
        width=WIN_WIDTH,
        height=WIN_HEIGHT,
        window_id=WINDOW_ID,
    )

    expected_actions = []
    for i in range(SINGLE_ACTION_LOOP_GUARD):
        act_dict_1 = create_action_dict(
            name="click",
            mouse_x=NEW_X + i,
            mouse_y=NEW_Y,
            mouse_button_name="left",
            mouse_pressed=True,
        )
        act_dict_2 = create_action_dict(
            name="click",
            mouse_x=NEW_X,
            mouse_y=NEW_Y + i,
            mouse_button_name="left",
            mouse_pressed=True,
        )
        act_dict_3 = create_action_dict(
            name="click",
            mouse_x=NEW_X + i,
            mouse_y=NEW_Y + i,
            mouse_button_name="left",
            mouse_pressed=True,
        )
        new_dict = act_dict_1 + act_dict_2 + act_dict_3
        expected_actions += new_dict

    _test_generalizable_single_action(
        win_dict, total_actions, active_win_dict, expected_actions
    )


def test_simple_multi_action_sequence():
    """
    Simple test that on an event where
    the user moves the cursor down in a straight line and
    types the word password.
    """
    win_dict = create_win_dict(
        title="Google Chrome",
        left=MULTI_ACTION_WIN_LEFT,
        top=MULTI_ACTION_WIN_TOP,
        width=MULTI_ACTION_WIN_WIDTH,
        height=MULTI_ACTION_WIN_HEIGHT,
        window_id=MULTI_ACTION_WINDOW_ID,
    )
    ref_act_dicts = []

    for i in range(MULTI_ACTION_LOOP_GUARD):
        new_act = create_action_dict(
            "move", MULTI_ACTION_REF_X - i, MULTI_ACTION_REF_Y - i
        )
        ref_act_dicts += new_act

    multi_action_test_word = "password"

    expected_act_dict = []

    for i in range(MULTI_ACTION_LOOP_GUARD):
        exp_act = create_action_dict(
            "move", MULTI_ACTION_NEW_X - i, MULTI_ACTION_NEW_Y - i
        )
        expected_act_dict += exp_act

    for letter in multi_action_test_word:
        press_dict = create_action_dict(name="press", key_name=letter)
        release_dict = create_action_dict(name="release", key_name=letter)
        ref_act_dicts = ref_act_dicts + press_dict + release_dict
        expected_act_dict = expected_act_dict + press_dict + release_dict

    # MODIFY THIS active act dict here to observe the results
    # discussed in the latest comment ! :)
    active_win_dict = create_win_dict(
        title="Google Chrome",
        left=NEW_MULTI_ACTION_WIN_LEFT,
        top=NEW_MULTI_ACTION_WIN_TOP,
        width=MULTI_ACTION_WIN_WIDTH,
        height=MULTI_ACTION_WIN_HEIGHT,
        window_id=MULTI_ACTION_WINDOW_ID,
    )
    _test_generalizable_single_action(
        win_dict, ref_act_dicts, active_win_dict, expected_act_dict
    )
