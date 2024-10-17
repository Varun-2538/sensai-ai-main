from typing import List, Dict, Literal
import itertools
import traceback
import time
import asyncio
from functools import partial
import numpy as np
import streamlit as st

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

from copy import deepcopy
import pandas as pd
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

# root_dir = os.path.dirname(os.path.abspath(__file__))

# if root_dir not in sys.path:
#     sys.path.append(root_dir)

from lib.llm import (
    get_llm_input_messages,
    call_llm_and_parse_output,
    COMMON_INSTRUCTIONS,
)
from lib.init import init_env_vars, init_db
from lib.db import (
    get_all_tasks,
    store_task as store_task_to_db,
    delete_tasks as delete_tasks_from_db,
    update_task as update_task_in_db,
    update_column_for_task_ids,
    update_tests_for_task,
    create_cohort,
    get_all_cohorts,
    get_cohort_by_id,
    get_all_milestones,
    insert_milestone as insert_milestone_to_db,
    delete_milestone as delete_milestone_from_db,
)
from lib.strings import *
from lib.utils import load_json, save_json
from lib.config import coding_languages_supported, tags_list_path

init_env_vars()
init_db()


def refresh_tasks():
    st.session_state.tasks = get_all_tasks()


def refresh_cohorts():
    st.session_state.cohorts = get_all_cohorts()


def refresh_milestones():
    st.session_state.milestones = get_all_milestones()


def refresh_tags():
    st.session_state.tags = load_json(tags_list_path)[::-1]


if "tasks" not in st.session_state:
    refresh_tasks()

if "cohorts" not in st.session_state:
    refresh_cohorts()

if "milestones" not in st.session_state:
    refresh_milestones()

if "tags" not in st.session_state:
    refresh_tags()


def reset_tests():
    st.session_state.tests = []


if "tests" not in st.session_state:
    reset_tests()

if "ai_answer" not in st.session_state:
    st.session_state.ai_answer = ""

if "final_answer" not in st.session_state:
    st.session_state.final_answer = ""

if "show_toast" not in st.session_state:
    st.session_state.show_toast = False

if "toast_message" not in st.session_state:
    st.session_state.toast_message = ""


def set_toast(message: str):
    if not message:
        return

    st.session_state.show_toast = True
    st.session_state.toast_message = message


def show_toast():
    if st.session_state.show_toast:
        st.toast(st.session_state.toast_message)
        st.session_state.show_toast = False


show_toast()

model = st.sidebar.selectbox(
    "Model",
    [
        {"label": "gpt-4o", "version": "gpt-4o-2024-08-06"},
        {"label": "gpt-4o-mini", "version": "gpt-4o-mini-2024-07-18"},
    ],
    format_func=lambda val: val["label"],
)


async def generate_answer_for_task(task_name, task_description):
    system_prompt_template = """You are a helpful and encouraging tutor.\n\nYou will be given a task that has been assigned to a student along with its description.\n\nYou need to work out your own solution to the task. You will use this solution later to evaluate the student's solution.\n\nImportant Instructions:\n- Give some reasoning before arriving at the answer but keep it concise.\n- Make sure to carefully read the task description and completely adhere to the requirements without making up anything on your own that is not already present in the description.{common_instructions}\n\nProvide the answer in the following format:\nLet's work this out in a step by step way to be sure we have the right answer\nAre you sure that's your final answer? Believe in your abilities and strive for excellence. Your hard work will yield remarkable results.\n<concise explanation>\n\n{format_instructions}"""

    user_prompt_template = (
        """Task name: {task_name}\n\nTask description: {task_description}"""
    )

    class Output(BaseModel):
        solution: str = Field(
            title="solution",
            description="The solution to the task",
        )

    output_parser = PydanticOutputParser(pydantic_object=Output)

    llm_input_messages = get_llm_input_messages(
        system_prompt_template,
        user_prompt_template,
        task_name=task_name,
        task_description=task_description,
        format_instructions=output_parser.get_format_instructions(),
        common_instructions=COMMON_INSTRUCTIONS,
    )

    try:
        pred_dict = await call_llm_and_parse_output(
            llm_input_messages,
            model=model["version"],
            output_parser=output_parser,
            max_tokens=2048,
            verbose=True,
            # labels=["final_answers", "audit rights"],
            # model_type=model_type,
        )
        return pred_dict["solution"]
    except Exception as exception:
        traceback.print_exc()
        raise Exception


@st.spinner("Generating answer...")
def generate_answer_for_form_task():
    st.session_state.ai_answer = asyncio.run(
        generate_answer_for_task(
            st.session_state.task_name, st.session_state.task_description
        )
    )


def get_task_type(is_code_editor_enabled: bool):
    if is_code_editor_enabled:
        return "coding"

    return "text"


def convert_tests_to_prompt(tests: List[Dict]) -> str:
    if not tests:
        return ""

    return "\n-----------------\n".join(
        [f"Input:\n{test['input']}\n\nOutput:\n{test['output']}" for test in tests]
    )


async def generate_tests_for_task_from_llm(
    task_name, task_description, num_test_inputs, tests
):
    system_prompt_template = """You are a test case generator for programming tasks.\n\nYou will be given a task name, its description, the number of inputs expected and, optionally, a list of test cases.\n\nYou need to generate a list of test cases in the form of input/output pairs.\n\n- Give some reasoning before arriving at the answer but keep it concise.\n- Create diverse test cases that cover various scenarios, including edge cases.\n- Ensure the test cases are relevant to the task description.\n- Provide at least 3 test cases, but no more than 5.\n- Ensure that every test case is unique.\n- If you are given a list of test cases, you need to ensure that the new test cases you generate are not duplicates of the ones in the list.\n{common_instructions}\n\nProvide the answer in the following format:\nLet's work this out in a step by step way to be sure we have the right answer\nAre you sure that's your final answer? Believe in your abilities and strive for excellence. Your hard work will yield remarkable results.\n<concise explanation>\n\n{format_instructions}"""

    user_prompt_template = """Task name: {task_name}\n\nTask description: {task_description}\n\nNumber of inputs: {num_test_inputs}\n\nTest cases:\n\n{tests}"""

    class TestCase(BaseModel):
        input: List[str] = Field(
            description="The list of inputs for a single test case. The number of inputs is {num_test_inputs}. Always return a list"
        )
        output: str = Field(description="The expected output for the test case")
        description: str = Field(
            description="A very brief description of the test case", default=""
        )

    class Output(BaseModel):
        test_cases: List[TestCase] = Field(
            description="A list of test cases for the given task",
        )

    output_parser = PydanticOutputParser(pydantic_object=Output)

    llm_input_messages = get_llm_input_messages(
        system_prompt_template,
        user_prompt_template,
        task_name=task_name,
        task_description=task_description,
        format_instructions=output_parser.get_format_instructions(),
        common_instructions=COMMON_INSTRUCTIONS,
        num_test_inputs=num_test_inputs,
        tests=convert_tests_to_prompt(tests),
    )

    try:
        pred_dict = await call_llm_and_parse_output(
            llm_input_messages,
            model=model["version"],
            output_parser=output_parser,
            max_tokens=2048,
            verbose=True,
        )
        return [
            {
                "input": tc["input"],
                "output": tc["output"],
                "description": tc["description"],
            }
            for tc in pred_dict["test_cases"]
        ]
    except Exception as exception:
        traceback.print_exc()
        raise exception


async def generate_tests_for_task(
    task_name: str, task_description: str, num_test_inputs: int, tests: List[Dict]
):
    with st.spinner("Generating tests..."):
        generated_tests = await generate_tests_for_task_from_llm(
            task_name,
            task_description,
            num_test_inputs,
            tests,
        )

    st.session_state.tests.extend(generated_tests)


def delete_test_from_session_state(test_index):
    st.session_state.tests.pop(test_index)


def update_test_in_session_state(test_index):
    st.session_state.tests[test_index] = {
        "input": [
            st.session_state[f"test_input_{test_index}_{i}"]
            for i in range(len(st.session_state.tests[test_index]["input"]))
        ],
        "output": st.session_state[f"test_output_{test_index}"],
        "description": st.session_state[f"test_description_{test_index}"],
    }


def add_verified_task_to_list(final_answer):
    task_type = get_task_type(st.session_state.show_code_editor)

    store_task_to_db(
        st.session_state.task_name,
        st.session_state.task_description,
        final_answer,
        st.session_state.task_tags,
        task_type,
        st.session_state.coding_languages,
        model["version"],
        True,
        st.session_state.tests,  # Add this line to include the tests
        st.session_state.milestone["id"] if st.session_state.milestone else None,
    )
    refresh_tasks()


def add_tests_to_task(
    task_name: str, task_description: str, mode: Literal["add", "edit"]
):
    container = st.container()
    cols = st.columns([3.5, 1])

    show_toast()

    if st.session_state.tests:
        num_test_inputs = len(st.session_state.tests[0]["input"])
        header_container = cols[0]
    else:
        header_container = container
        num_test_inputs = cols[0].number_input("Number of inputs", min_value=1, step=1)
        cols[-1].markdown("####")

    header_container.subheader(admin_code_test_cases_label)
    if cols[-1].button("Generate", key="generate_tests"):
        asyncio.run(
            generate_tests_for_task(
                task_name, task_description, num_test_inputs, st.session_state.tests
            )
        )

    for test_index, test in enumerate(st.session_state.tests):
        with st.expander(f"Test {test_index + 1}"):
            st.text("Inputs")
            for i, input_value in enumerate(test["input"]):
                st.text_area(
                    label=f"Input {i + 1}",
                    value=input_value,
                    key=f"test_input_{test_index}_{i}",
                    on_change=update_test_in_session_state,
                    args=(test_index,),
                    label_visibility="collapsed",
                )

            st.text("Output")
            st.text_area(
                label="Output",
                value=test["output"],
                key=f"test_output_{test_index}",
                on_change=update_test_in_session_state,
                args=(test_index,),
                label_visibility="collapsed",
            )
            st.text("Description (optional)")
            st.text_area(
                label="Description",
                value=test.get("description", ""),
                key=f"test_description_{test_index}",
                on_change=update_test_in_session_state,
                args=(test_index,),
                label_visibility="collapsed",
            )
            cols = st.columns([3, 1.1, 1])
            is_delete_disabled = mode == "edit" and len(st.session_state.tests) == 1
            cols[-1].button(
                "Delete",
                type="primary",
                on_click=delete_test_from_session_state,
                args=(test_index,),
                key=f"delete_test_{test_index}",
                disabled=is_delete_disabled,
                help=(
                    "To delete all tests, use the `Delete all tests` button below"
                    if is_delete_disabled
                    else ""
                ),
            )

    st.text("Inputs")
    for i in range(num_test_inputs):
        st.text_area(
            f"Input {i + 1}", key=f"new_test_input_{i}", label_visibility="collapsed"
        )

    st.text("Output")
    st.text_area("Output", key="test_output", label_visibility="collapsed")
    st.text("Description (optional)")
    st.text_area("Description", key="test_description", label_visibility="collapsed")

    def add_test():
        st.session_state.tests.append(
            {
                "input": [
                    st.session_state[f"new_test_input_{i}"]
                    for i in range(num_test_inputs)
                ],
                "output": st.session_state.test_output,
                "description": st.session_state.test_description,
            }
        )
        for i in range(num_test_inputs):
            st.session_state[f"new_test_input_{i}"] = ""

        st.session_state.test_output = ""
        st.session_state.test_description = ""
        set_toast("Added test!")

    st.info(
        "Tip: Click outside the boxes above after you are done typing the last input before clicking the button below"
    )
    st.button("Add Test", on_click=add_test)

    # st.session_state.tests


def update_tests_for_task_in_db(task_id, tests, toast_message: str = None):
    update_tests_for_task(task_id, tests)
    refresh_tasks()
    reset_tests()
    set_toast(toast_message)


@st.dialog("Edit tests for task")
def edit_tests_for_task(df, task_id):
    task_details = df[df["id"] == task_id].iloc[0]
    if not st.session_state.tests:
        st.session_state.tests = deepcopy(task_details["tests"])

    add_tests_to_task(
        task_details["name"],
        task_details["description"],
        mode="edit",
    )

    cols = st.columns(2) if st.session_state.tests else st.columns(1)

    is_tests_updated = task_details["tests"] != st.session_state.tests
    if cols[0].button(
        "Update tests",
        type="primary",
        use_container_width=True,
        disabled=not is_tests_updated,
        help=(
            "Nothing to update"
            if task_details["tests"] == st.session_state.tests
            else ""
        ),
    ):
        update_tests_for_task_in_db(
            task_id, st.session_state.tests, toast_message="Tests updated successfully!"
        )
        st.rerun()

    if len(cols) == 2:
        if cols[1].button(
            "Delete all tests",
            type="primary" if not is_tests_updated else "secondary",
            use_container_width=True,
        ):
            update_tests_for_task_in_db(task_id, [], "Tests deleted successfully!")
            st.rerun()


def milestone_selector():
    return st.selectbox(
        "Milestone",
        st.session_state.milestones,
        key="milestone",
        format_func=lambda row: row["name"],
        index=None,
        help="If you don't see the milestone you want, you can create a new one from the `Milestones` tab",
    )


def task_type_selector():
    return st.checkbox(
        admin_show_code_editor_label,
        value=True,
        help=admin_show_code_editor_help,
        key="show_code_editor",
    )


def coding_language_selector():
    return st.multiselect(
        admin_code_editor_language_label,
        coding_languages_supported,
        help=admin_code_editor_language_help,
        key="coding_languages",
        default=["Python"],
    )


@st.dialog("Add a new task")
def show_task_form():
    st.text_input("*Name", key="task_name", value="Greet function")
    st.text_area(
        "*Description",
        key="task_description",
        value="""Write a python code to take user input and display it.""",
    )

    cols = st.columns(2)
    cols[0].multiselect(
        "Tags",
        st.session_state.tags,
        key="task_tags",
        default=(
            [st.session_state.tags[st.session_state.tags.index("Python")]]
            if "Python" in st.session_state.tags
            else None
        ),
        help="If you don't see the tag you want, you can create a new one from the `Tags` tab",
    )

    with cols[1]:
        milestone_selector()

    if task_type_selector():
        if (
            "coding_languages" in st.session_state
            and st.session_state.coding_languages is None
        ):
            st.session_state.coding_languages = []

        coding_language_selector()
    else:
        st.session_state.coding_languages = None

    # test cases
    if st.session_state.show_code_editor and st.checkbox("I want to add tests", False):
        add_tests_to_task(
            st.session_state.task_name,
            st.session_state.task_description,
            mode="add",
        )

    st.subheader("*Answer")
    cols = st.columns([3.5, 1])

    if cols[-1].button(
        "Generate",
        disabled=(
            not st.session_state.task_description
            or not st.session_state.task_name
            or st.session_state.final_answer != ""
            or st.session_state.ai_answer != ""
        ),
        key="generate_answer",
    ):
        with cols[0]:
            generate_answer_for_form_task()

    final_answer = cols[0].text_area(
        "Answer",
        key="final_answer",
        value=st.session_state.ai_answer,
        label_visibility="collapsed",
    )
    if not final_answer and st.session_state.ai_answer:
        final_answer = st.session_state.ai_answer

    disabled_help_text = ""
    if not st.session_state.task_name:
        disabled_help_text = "Please enter a task name"
    elif not st.session_state.task_description:
        disabled_help_text = "Please enter a task description"
    elif not final_answer:
        disabled_help_text = "Please enter an answer"
    is_submit_disabled = disabled_help_text != ""

    if final_answer and st.button(
        "Verify and Add",
        on_click=add_verified_task_to_list,
        args=(final_answer,),
        use_container_width=True,
        type="primary",
        disabled=is_submit_disabled,
        help=disabled_help_text,
    ):
        # st.session_state.vote = {"item": item, "reason": reason}
        reset_tests()
        st.rerun()

    st.info("**Note:** Fields marked with an asterisk (*) are required")


async def generate_answer_for_bulk_task(task_id, task_name, task_description):
    answer = await generate_answer_for_task(task_name, task_description)
    return task_id, answer


def update_progress_bar(progress_bar, count, num_tasks, message):
    progress_bar.progress(count / num_tasks, text=f"{message} ({count}/{num_tasks})")


async def generate_answers_for_tasks(tasks_df):
    coroutines = []

    for index, row in tasks_df.iterrows():
        coroutines.append(
            generate_answer_for_bulk_task(index, row["Name"], row["Description"])
        )

    num_tasks = len(tasks_df)
    progress_bar = st.progress(
        0, text=f"Generating answers for tasks... (0/{num_tasks})"
    )

    count = 0

    tasks_df["Answer"] = [None] * num_tasks

    for completed_task in asyncio.as_completed(coroutines):
        task_id, answer = await completed_task
        tasks_df.at[task_id, "Answer"] = answer
        count += 1

        update_progress_bar(
            progress_bar, count, num_tasks, "Generating answers for tasks..."
        )

    progress_bar.empty()

    return tasks_df


@st.dialog("Bulk upload tasks")
def show_bulk_upload_tasks_form():
    show_code_editor = task_type_selector()
    coding_languages = None

    if show_code_editor:
        coding_languages = coding_language_selector()

    task_type = get_task_type(show_code_editor)

    milestone = milestone_selector()

    uploaded_file = st.file_uploader(
        "Choose a CSV file with the columns:\n\n`Name`, `Description`, `Tags`, `Answer` (optional)",
        type="csv",
        key="bulk_upload_tasks",
    )

    if uploaded_file:
        tasks_df = pd.read_csv(uploaded_file)

        if "Answer" not in tasks_df.columns:
            tasks_df = asyncio.run(generate_answers_for_tasks(tasks_df))

        for _, row in tasks_df.iterrows():
            store_task_to_db(
                row["Name"],
                row["Description"],
                row["Answer"],
                row["Tags"].split(","),
                task_type,
                coding_languages,
                model["version"],
                False,
                [],
                milestone["id"] if milestone else None,
            )

        refresh_tasks()
        st.rerun()


def delete_tasks_from_list(task_ids):
    delete_tasks_from_db(task_ids)
    refresh_tasks()
    st.rerun()


@st.dialog("Delete tasks")
def show_tasks_delete_confirmation(task_ids):
    st.write("Are you sure you want to delete the selected tasks?")

    confirm_col, cancel_col, _, _ = st.columns([1, 1, 2, 2])
    if confirm_col.button("Yes", use_container_width=True):
        delete_tasks_from_list(task_ids)
        st.rerun()

    if cancel_col.button("No", use_container_width=True, type="primary"):
        st.rerun()


def update_tasks_with_new_value(
    task_ids: List[int], column_to_update: str, new_value: str
):
    update_column_for_task_ids(task_ids, column_to_update, new_value)
    refresh_tasks()
    st.rerun()


@st.dialog("Edit tasks")
def show_task_edit_dialog(task_ids):
    column_to_update = st.selectbox(
        "Select a column to update", ["type", "coding_language", "milestone"]
    )
    kwargs = {}
    db_column = None
    if column_to_update == "type":
        option_component = st.selectbox
        options = ["text", "coding"]
    elif column_to_update == "milestone":
        option_component = st.selectbox
        options = st.session_state.milestones
        kwargs["format_func"] = lambda row: row["name"]
        value_key = "id"
        db_column = "milestone_id"
    else:
        option_component = st.multiselect
        options = coding_languages_supported

    new_value = option_component("Select the new value", options, **kwargs)

    st.write("Are you sure you want to update the selected tasks?")

    confirm_col, cancel_col, _, _ = st.columns([1, 1, 2, 2])
    if confirm_col.button("Yes", use_container_width=True):
        if option_component == st.selectbox and isinstance(new_value, dict):
            new_value = new_value[value_key]

        if db_column is None:
            db_column = column_to_update

        update_tasks_with_new_value(task_ids, db_column, new_value)
        st.rerun()

    if cancel_col.button("No", use_container_width=True, type="primary"):
        st.rerun()


tasks_heading = "Tasks"
tasks_description = ""

num_tasks = len(st.session_state.tasks)

if num_tasks > 0:
    tasks_heading = f"Tasks ({num_tasks})"
    tasks_description = f"You can select multiple tasks by clicking beside the `id` column of each task and do any of the following:\n\n- Delete tasks\n\n- Edit task attributes in bulk (e.g. task type, whether to show code preview, coding language)\n\n- You can also go through the unverified answers and verify them for learners to access them by selecting `Edit Mode`.\n\n- Add/Modify tests for one task at a time"

cohorts_heading = "Cohorts"
num_cohorts = len(st.session_state.cohorts)

if num_cohorts > 0:
    cohorts_heading = f"Cohorts ({num_cohorts})"

tab_names = [tasks_heading, cohorts_heading, "Milestones", "Tags"]
tabs = st.tabs(tab_names)


@st.fragment
def show_tasks_tab():
    single_task_col, bulk_upload_tasks_col, _ = st.columns([1, 3, 2])
    add_task = single_task_col.button("Add a new task")
    bulk_upload_tasks = bulk_upload_tasks_col.button("Bulk upload tasks")

    if add_task:
        reset_tests()
        st.session_state.ai_answer = ""
        st.session_state.final_answer = ""
        show_task_form()

    if bulk_upload_tasks:
        show_bulk_upload_tasks_form()

    st.write(tasks_description)

    st.divider()

    if not st.session_state.tasks:
        st.error("No tasks added yet")
        st.stop()

    df = pd.DataFrame(st.session_state.tasks)
    df["coding_language"] = df["coding_language"].apply(
        lambda x: x.split(",") if isinstance(x, str) else x
    )
    df["num_tests"] = df["tests"].apply(lambda x: len(x) if isinstance(x, list) else 0)

    cols = st.columns(4)
    all_tags = np.unique(
        list(itertools.chain(*[tags for tags in df["tags"].tolist()]))
    ).tolist()
    filter_tags = cols[0].multiselect("Filter by tags", all_tags)

    if filter_tags:
        df = df[df["tags"].apply(lambda x: any(tag in x for tag in filter_tags))]

    verified_filter = cols[1].radio(
        "Filter by verification status",
        ["All", "Verified", "Unverified"],
        horizontal=True,
    )

    if verified_filter != "All":
        df = df[df["verified"] == (verified_filter == "Verified")]

    type_filter = cols[2].radio(
        "Filter by task type",
        ["All", "Coding", "Text"],
        horizontal=True,
    )

    if type_filter != "All":
        df = df[df["type"] == type_filter.lower()]

    coding_languages_filter = cols[3].multiselect(
        "Filter by coding language",
        coding_languages_supported,
        help="Select one or more coding languages to filter tasks",
    )

    if coding_languages_filter:
        df = df[
            df["coding_language"].apply(
                lambda x: (
                    any(lang in x for lang in coding_languages_filter)
                    if isinstance(x, list)
                    else False
                )
            )
        ]

    (
        edit_mode_col,
        _,
        save_col,
    ) = st.columns([1.25, 7.5, 1])

    is_edit_mode = edit_mode_col.checkbox(
        "Edit Mode",
        value=False,
        help="Select this to go through the unverified answers and verify them for learners to access them or make any other changes to the tasks.",
    )

    column_config = {
        # 'id': None
        "description": st.column_config.TextColumn(width="medium"),
        "answer": st.column_config.TextColumn(width="medium"),
    }

    column_order = [
        "id",
        "verified",
        "num_tests",
        "name",
        "description",
        "answer",
        "tags",
        "milestone",
        "type",
        "coding_language",
        "generation_model",
        "timestamp",
    ]

    def save_changes_in_edit_mode(edited_df):
        # identify the rows that have been changed
        # and update the db with the new values
        # import ipdb; ipdb.set_trace()
        changed_rows = edited_df[(df != edited_df).any(axis=1)]

        print(f"Changed rows: {len(changed_rows)}", flush=True)

        for _, row in changed_rows.iterrows():
            task_id = row["id"]
            # print(task_id)
            update_task_in_db(
                task_id,
                row["name"],
                row["description"],
                row["answer"],
                row["tags"],
                row["type"],
                row["coding_language"],
                row["generation_model"],
                row["verified"],
            )

        # Refresh the tasks in the session state
        refresh_tasks()
        st.toast("Changes saved successfully!")
        # st.rerun()

    if not is_edit_mode:
        delete_col, edit_col, add_tests_col, _ = st.columns([1.5, 2, 4, 7])

        event = st.dataframe(
            df,
            on_select="rerun",
            selection_mode="multi-row",
            hide_index=True,
            use_container_width=True,
            column_config=column_config,
            column_order=column_order,
        )

        if len(event.selection["rows"]):
            task_ids = df.iloc[event.selection["rows"]]["id"].tolist()
            if delete_col.button("Delete tasks"):
                # import ipdb; ipdb.set_trace()
                show_tasks_delete_confirmation(task_ids)

            if edit_col.button("Edit task attributes"):
                # import ipdb; ipdb.set_trace()
                show_task_edit_dialog(task_ids)

            if add_tests_col.button("Add/Edit tests"):
                if len(task_ids) == 1:
                    reset_tests()
                    edit_tests_for_task(df, task_ids[0])
                else:
                    st.error("Please select only one task to edit tests for.")

    else:
        edited_df = st.data_editor(
            df,
            hide_index=True,
            column_config=column_config,
            column_order=column_order,
            use_container_width=True,
            disabled=[
                "id",
                "num_tests",
                "type",
                "generation_model",
                "timestamp",
                "milestone",
            ],
        )

        if not df.equals(edited_df):
            save_col.button(
                "Save changes",
                type="primary",
                on_click=partial(save_changes_in_edit_mode, edited_df),
            )


with tabs[0]:
    show_tasks_tab()

if "cohort_uploader_key" not in st.session_state:
    st.session_state.cohort_uploader_key = 0


def update_cohort_uploader_key():
    st.session_state.cohort_uploader_key += 1


@st.dialog("Create Cohort")
def show_create_cohort_dialog():
    st.markdown("Hit `Enter` after entering the cohort name")
    cohort_name = st.text_input("Enter cohort name")

    columns = ["Group Name", "Learner Email", "Learner ID", "Mentor Email"]
    uploaded_file = st.file_uploader(
        f"Choose a CSV file with the following columns:\n\n{','.join([f'`{column}`' for column in columns])}",
        type="csv",
        key=f"cohort_uploader_{st.session_state.cohort_uploader_key}",
    )

    if uploaded_file:
        cohort_df = pd.read_csv(uploaded_file)
        if cohort_df.columns.tolist() != columns:
            st.error("The uploaded file does not have the correct columns.")
            st.stop()

        st.dataframe(cohort_df, use_container_width=True)

        is_create_disabled = not cohort_name
        if st.button(
            "Create",
            type="primary",
            disabled=is_create_disabled,
            help="Enter a cohort name" if is_create_disabled else None,
        ):
            create_cohort(cohort_name, cohort_df)
            refresh_cohorts()
            set_toast(f"Cohort `{cohort_name}` created successfully!")
            st.rerun()


@st.fragment
def show_cohorts_tab():
    create_cohort_col, _ = st.columns([2, 8])
    st.session_state.bulk_upload_cohort = None
    if create_cohort_col.button("Create Cohort"):
        update_cohort_uploader_key()
        show_create_cohort_dialog()

    if not len(st.session_state.cohorts):
        st.error("No cohorts added yet")
        st.stop()

    cols = st.columns(4)
    selected_cohort = cols[0].selectbox(
        "Select a cohort", st.session_state.cohorts, format_func=lambda row: row["name"]
    )

    cohort_info = get_cohort_by_id(selected_cohort["id"])
    cohort_groups = [{"name": "All", "id": None}] + cohort_info["groups"]

    selected_group = cols[1].selectbox(
        "Select a group", cohort_groups, format_func=lambda group: group["name"]
    )

    st.divider()

    if selected_group["name"] == "All":
        # Create a list to store all group data
        all_group_data = []

        # Iterate through all groups in the cohort
        for group in cohort_info["groups"]:
            # For each learner in the group, create a row
            for learner_email, learner_id in zip(
                group["learner_emails"], group["learner_ids"]
            ):
                all_group_data.append(
                    {
                        "Group Name": group["name"],
                        "Mentor Email": group["mentor_email"],
                        "Learner Email": learner_email,
                        "Learner ID": learner_id,
                    }
                )

        # Create DataFrame from the collected data
        df = pd.DataFrame(all_group_data)

        # Display the DataFrame
        st.subheader("Cohort Overview")
        st.dataframe(df, hide_index=True, use_container_width=True)

    else:
        # Display mentor email
        st.subheader("Mentor")
        st.text(selected_group["mentor_email"])

        # Create DataFrame of learner IDs and emails
        learners_data = {
            "Learner ID": selected_group["learner_ids"],
            "Learner Email": selected_group["learner_emails"],
        }
        learners_df = pd.DataFrame(learners_data)

        # Display the DataFrame
        st.subheader("Learners")
        st.dataframe(learners_df, hide_index=True, use_container_width=True)


with tabs[1]:
    show_cohorts_tab()


def add_milestone(new_milestone):
    if not new_milestone:
        st.toast("Enter a milestone name")
        return

    if new_milestone in [
        milestone["name"] for milestone in st.session_state.milestones
    ]:
        st.toast("Milestone already exists")
        return

    insert_milestone_to_db(new_milestone)
    st.toast("New milestone added")
    refresh_milestones()

    st.session_state.new_milestone = ""


def delete_milestone(milestone):
    delete_milestone_from_db(milestone["id"])
    set_toast("Milestone deleted")
    refresh_milestones()


@st.dialog("Delete Milestone")
def show_milestone_delete_confirmation_dialog(milestone):
    st.markdown(f"Are you sure you want to delete `{milestone['name']}`?")
    (
        confirm_col,
        cancel_col,
        _,
    ) = st.columns([1, 2, 4])

    if confirm_col.button("Yes", type="primary"):
        delete_milestone(milestone)
        st.rerun()

    if cancel_col.button("Cancel"):
        st.rerun()


def show_milestones_tab():
    cols = st.columns(4)
    new_milestone = cols[0].text_input("Enter Milestone", key="new_milestone")
    cols[1].container(height=10, border=False)
    cols[1].button(
        "Add",
        on_click=add_milestone,
        args=(new_milestone,),
        key="add_milestone",
    )

    if not st.session_state.milestones:
        st.info("No milestones added yet")
        st.stop()

    num_layout_cols = 3
    layout_cols = st.columns(num_layout_cols)
    for i, milestone in enumerate(st.session_state.milestones):
        with layout_cols[i % num_layout_cols].container(
            border=True,
        ):
            cols = st.columns([3, 1])
            cols[0].write(milestone["name"])
            cols[-1].button(
                "Delete",
                on_click=show_milestone_delete_confirmation_dialog,
                args=(milestone,),
                key=f"delete_milestone_{i}",
            )


with tabs[2]:
    show_milestones_tab()


def save_tags():
    # since we show the tags in reverse order, we need to save them in reverse order
    save_json(tags_list_path, st.session_state.tags[::-1])


def add_tag(new_tag):
    if not new_tag:
        st.toast("Enter a tag name")
        return

    if new_tag in st.session_state.tags:
        st.toast("Tag already exists")
        # st.stop()
        return

    # since we show the tags in reverse order, we need to save them in reverse order
    st.session_state.tags = [new_tag] + st.session_state.tags
    save_tags()
    st.toast("New tag added")
    refresh_tags()

    st.session_state.new_tag = ""


def delete_tag(tag):
    st.session_state.tags.remove(tag)
    save_tags()
    set_toast("Tag deleted")
    refresh_tags()


@st.dialog("Delete Tag")
def show_tag_delete_confirmation_dialog(tag):
    st.markdown(f"Are you sure you want to delete `{tag}`?")
    (
        confirm_col,
        cancel_col,
        _,
    ) = st.columns([1, 2, 4])

    if confirm_col.button("Yes", type="primary"):
        delete_tag(tag)
        st.rerun()

    if cancel_col.button("Cancel"):
        st.rerun()


def show_tags_tab():
    cols = st.columns(4)
    new_tag = cols[0].text_input("Enter Tag", key="new_tag")
    cols[1].container(height=10, border=False)
    cols[1].button(
        "Add",
        on_click=add_tag,
        args=(new_tag,),
        key="add_tag",
    )

    if not st.session_state.tags:
        st.info("No tags added yet")
        st.stop()

    num_layout_cols = 3
    layout_cols = st.columns(num_layout_cols)
    for i, tag in enumerate(st.session_state.tags):
        with layout_cols[i % num_layout_cols].container(
            border=True,
        ):
            cols = st.columns([3, 1])
            cols[0].write(tag)
            cols[-1].button(
                "Delete",
                on_click=show_tag_delete_confirmation_dialog,
                args=(tag,),
                key=f"delete_tag_{i}",
            )


with tabs[3]:
    show_tags_tab()
