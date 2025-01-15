from typing import List, Dict, Literal
import itertools
import os
import math
from datetime import datetime
import asyncio
from functools import partial
import numpy as np
import streamlit as st
import json
from email_validator import validate_email, EmailNotValidError

st.set_page_config(
    page_title="Admin | SensAI", layout="wide", initial_sidebar_state="collapsed"
)

from copy import deepcopy
import pandas as pd
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from lib.prompts import generate_answer_for_task, generate_tests_for_task_from_llm
from lib.llm import (
    validate_openai_api_key,
)
from lib.ui import show_singular_or_plural
from lib.config import (
    group_role_learner,
    group_role_mentor,
    all_ai_response_types,
    all_input_types,
    all_task_types,
    task_type_mapping,
    allowed_ai_response_types,
    response_type_help_text,
    task_type_to_label,
)
from lib.init import init_app
from lib.cache import (
    clear_course_cache_for_cohorts,
    clear_cohort_cache_for_courses,
    clear_cache_for_mentor_groups,
)
from lib.db import (
    get_all_tasks_for_org_or_course,
    store_task as store_task_to_db,
    delete_tasks as delete_tasks_from_db,
    update_task as update_task_in_db,
    update_column_for_task_ids,
    update_tests_for_task,
    create_cohort,
    get_all_cohorts_for_org,
    get_cohort_by_id,
    get_all_milestones_for_org,
    get_all_tags_for_org,
    create_bulk_tags,
    create_tag as create_tag_in_db,
    delete_tag as delete_tag_from_db,
    insert_milestone as insert_milestone_to_db,
    delete_milestone as delete_milestone_from_db,
    update_milestone as update_milestone_in_db,
    get_all_cv_review_usage,
    get_org_users,
    add_user_to_org_by_email,
    remove_members_from_org,
    add_members_to_cohort,
    create_cohort_group,
    delete_cohort_group_from_db,
    delete_cohort,
    remove_members_from_cohort,
    update_cohort_group_name,
    add_members_to_cohort_group,
    remove_members_from_cohort_group,
    get_courses_for_tasks,
    add_tasks_to_courses,
    remove_tasks_from_courses,
    add_scoring_criteria_to_task,
    add_scoring_criteria_to_tasks,
    remove_scoring_criteria_from_task,
    create_course,
    get_all_courses_for_org,
    add_course_to_cohorts,
    add_courses_to_cohort,
    remove_course_from_cohorts,
    remove_courses_from_cohort,
    delete_course,
    get_courses_for_cohort,
    get_cohorts_for_course,
    get_tasks_for_course,
    update_course_name as update_course_name_in_db,
    update_cohort_name as update_cohort_name_in_db,
    update_task_orders as update_task_orders_in_db,
    get_scoring_criteria_for_task,
    get_scoring_criteria_for_tasks,
    get_hva_org_id,
    add_tags_to_task,
    remove_tags_from_task,
    get_cohort_group_ids_for_users,
    update_org,
    update_org_openai_api_key,
    get_org_by_id,
    get_cohort_metrics_for_milestone,
)
from lib.utils import generate_random_color
from lib.utils.encryption import decrypt_openai_api_key, encrypt_openai_api_key
from lib.config import coding_languages_supported
from lib.profile import show_placeholder_icon
from lib.toast import set_toast, show_toast
from auth import (
    unauthorized_redirect_to_home,
    login_or_signup_user,
    is_empty_openai_api_key,
)
from components.buttons import back_to_home_button

init_app()

login_or_signup_user()

if "org_id" not in st.query_params:
    unauthorized_redirect_to_home(
        "`org_id` not present in the URL. Redirecting to home page..."
    )

st.session_state.org_id = int(st.query_params["org_id"])
st.session_state.org = get_org_by_id(st.session_state.org_id)

back_to_home_button(params={"org_id": st.session_state.org_id})

def reset_ai_running():
    st.session_state.is_ai_running = False


def set_ai_running():
    st.session_state.is_ai_running = True


if "is_ai_running" not in st.session_state:
    reset_ai_running()


def show_logo():
    show_placeholder_icon(
        st.session_state.org["name"],
        st.session_state.org["logo_color"],
        dim=100,
        font_size=56,
    )
    st.container(height=10, border=False)


def show_profile_header():
    cols = st.columns([1, 4, 3])

    with cols[0]:
        show_logo()

    with cols[1]:
        st.subheader(st.session_state.org["name"])

        if is_empty_openai_api_key():
            st.error(
                """No OpenAI API key found. Please set an API key in the `"Settings"` section. Otherwise, AI will not work, neither for generating tasks nor for providing feedback."""
            )


show_profile_header()


def refresh_cohorts():
    st.session_state.cohorts = get_all_cohorts_for_org(st.session_state.org_id)


def refresh_courses():
    st.session_state.courses = get_all_courses_for_org(st.session_state.org_id)


def refresh_tasks():
    st.session_state.tasks = get_all_tasks_for_org_or_course(st.session_state.org_id)


def refresh_milestones():
    st.session_state.milestones = get_all_milestones_for_org(st.session_state.org_id)


def refresh_tags():
    st.session_state.tags = get_all_tags_for_org(st.session_state.org_id)


if "cohorts" not in st.session_state:
    refresh_cohorts()

if "courses" not in st.session_state:
    refresh_courses()

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


def reset_scoring_criteria():
    st.session_state.scoring_criteria = []
    st.session_state.updated_scoring_criteria = None


if "scoring_criteria" not in st.session_state:
    reset_scoring_criteria()

if "task_uploader_key" not in st.session_state:
    st.session_state.task_uploader_key = 0


def update_task_uploader_key():
    st.session_state.task_uploader_key += 1


if "cohort_uploader_key" not in st.session_state:
    st.session_state.cohort_uploader_key = 0


def update_cohort_uploader_key():
    st.session_state.cohort_uploader_key += 1


def reset_task_form():
    st.session_state.task_type = None
    st.session_state.task_name = ""
    st.session_state.task_description = ""
    st.session_state.task_milestone = None
    st.session_state.task_ai_response_type = None
    st.session_state.task_input_type = None
    st.session_state.task_tags = []
    st.session_state.task_courses = []
    st.session_state.task_answer = ""
    st.session_state.coding_languages = None
    st.session_state.final_answer = ""
    st.session_state.ai_answer = ""
    st.session_state.ai_answers = None
    reset_ai_running()
    reset_tests()
    reset_scoring_criteria()


def set_task_type_vars(task_type: str):
    st.session_state.is_task_type_reading = task_type == "reading_material"
    st.session_state.is_task_type_question = task_type == "question"


show_toast()

model = {"label": "gpt-4o", "version": "gpt-4o-2024-08-06"}


def get_task_context():
    if st.session_state.is_task_type_question and st.session_state.task_has_context:
        return st.session_state.task_context

    return None


@st.spinner("Generating answer...")
def generate_answer_for_form_task():
    st.session_state.ai_answer = asyncio.run(
        generate_answer_for_task(
            st.session_state.task_name,
            st.session_state.task_description,
            get_task_context(),
            model["version"],
            decrypt_openai_api_key(st.session_state.org["openai_api_key"]),
        )
    )


async def generate_tests_for_task(
    task_name: str, task_description: str, num_test_inputs: int, tests: List[Dict]
):
    with st.spinner("Generating tests..."):
        generated_tests = await generate_tests_for_task_from_llm(
            task_name,
            task_description,
            get_task_context(),
            num_test_inputs,
            tests,
            model["version"],
            decrypt_openai_api_key(st.session_state.org["openai_api_key"]),
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


def get_task_tests():
    if (
        st.session_state.is_task_type_question
        and st.session_state.task_input_type == "coding"
        and st.session_state.task_has_tests
    ):
        return st.session_state.tests

    return []


def get_model_version():
    return None if st.session_state.is_task_type_reading else model["version"]


def get_task_scoring_criteria():
    if (
        st.session_state.is_task_type_question
        and st.session_state.task_ai_response_type == "report"
    ):
        return st.session_state.scoring_criteria

    return []


def validate_task_metadata_params():
    if st.session_state.is_task_type_reading:
        return

    if not st.session_state.task_ai_response_type:
        return "Please select the AI response type"
    if not st.session_state.task_input_type:
        return "Please select a task input type"
    if (
        st.session_state.task_input_type == "coding"
        and not st.session_state.coding_languages
    ):
        return "Please select at least one coding language"
    if (
        st.session_state.task_ai_response_type == "report"
        and not st.session_state.scoring_criteria
    ):
        return "Please add at least one scoring criterion for the report"


def check_task_form_errors():
    if not st.session_state.task_name:
        return "Please enter a task name"

    if not st.session_state.task_description:
        return "Please enter a task description"

    if st.session_state.is_task_type_question:
        if (
            st.session_state.task_ai_response_type in ["chat", "exam"]
            and not st.session_state.task_answer
        ):
            return "Please enter an answer"

        return validate_task_metadata_params()


def add_new_task():
    error_text = check_task_form_errors()
    if error_text:
        st.error(error_text)
        return

    task_id = store_task_to_db(
        st.session_state.task_name,
        st.session_state.task_description,
        st.session_state.task_answer,
        st.session_state.task_tags,
        st.session_state.task_input_type,
        st.session_state.task_ai_response_type,
        st.session_state.coding_languages,
        get_model_version(),
        True,
        get_task_tests(),
        (
            st.session_state.task_milestone["id"]
            if st.session_state.task_milestone
            else None
        ),
        st.session_state.org_id,
        get_task_context(),
        st.session_state["task_type"]["value"],
    )

    if st.session_state.selected_task_courses:
        add_tasks_to_courses(
            [
                [task_id, course["id"]]
                for course in st.session_state.selected_task_courses
            ]
        )

    if st.session_state.scoring_criteria:
        add_scoring_criteria_to_task(task_id, st.session_state.scoring_criteria)

    refresh_tasks()
    st.rerun()


def update_task_courses(task_details: Dict):
    task_id = task_details["id"]

    if st.session_state.selected_task_courses != task_details["courses"]:
        # Get current course IDs for this task
        current_course_ids = [course["id"] for course in task_details["courses"]]
        # Get selected course IDs
        selected_course_ids = [
            course["id"] for course in st.session_state.selected_task_courses
        ]

        # Find courses to add and remove
        courses_to_add = [
            [task_id, course_id]
            for course_id in selected_course_ids
            if course_id not in current_course_ids
        ]
        courses_to_remove = [
            [task_id, course_id]
            for course_id in current_course_ids
            if course_id not in selected_course_ids
        ]

        # Add task to new courses
        if courses_to_add:
            add_tasks_to_courses(courses_to_add)

        # Remove task from unselected courses
        if courses_to_remove:
            remove_tasks_from_courses(courses_to_remove)


def is_scoring_criteria_changed(new_task_scoring_criteria, old_task_scoring_criteria):
    for index, criterion in enumerate(new_task_scoring_criteria):
        for key in new_task_scoring_criteria[0].keys():
            if criterion[key] != old_task_scoring_criteria[index][key]:
                return True

    return False


def update_task_scoring_criteria(task_details: Dict):
    task_id = task_details["id"]
    new_task_scoring_criteria = get_task_scoring_criteria()
    old_task_scoring_criteria = task_details.get("scoring_criteria", [])

    if is_scoring_criteria_changed(
        new_task_scoring_criteria, old_task_scoring_criteria
    ):
        scoring_criteria_to_add = [
            criterion
            for criterion in new_task_scoring_criteria
            if criterion not in old_task_scoring_criteria
        ]

        scoring_criteria_to_remove = [
            criterion["id"]
            for criterion in old_task_scoring_criteria
            if criterion not in new_task_scoring_criteria
        ]

        if scoring_criteria_to_add:
            add_scoring_criteria_to_task(task_id, scoring_criteria_to_add)

        if scoring_criteria_to_remove:
            remove_scoring_criteria_from_task(scoring_criteria_to_remove)


def edit_task(task_details):
    error_text = check_task_form_errors()

    if error_text:
        st.error(error_text)
        return True

    task_id = task_details["id"]

    update_task_in_db(
        task_id,
        st.session_state.task_name,
        st.session_state.task_description,
        st.session_state.task_answer,
        st.session_state.task_input_type,
        st.session_state.task_ai_response_type,
        st.session_state.coding_languages,
        (
            st.session_state.task_milestone["id"]
            if st.session_state.task_milestone
            else None
        ),
        get_task_context(),
    )

    update_task_courses(task_details)
    update_task_scoring_criteria(task_details)

    if st.session_state.task_tags != task_details["tags"]:
        # Get current tag IDs for this task
        current_tag_ids = [tag["id"] for tag in task_details["tags"]]
        # Get selected tag IDs
        selected_tag_ids = [tag["id"] for tag in st.session_state.task_tags]

        # Find tags to add and remove
        tags_to_add = [
            tag_id for tag_id in selected_tag_ids if tag_id not in current_tag_ids
        ]
        tags_to_remove = [
            tag_id for tag_id in current_tag_ids if tag_id not in selected_tag_ids
        ]

        # Add new tag associations
        if tags_to_add:
            add_tags_to_task(task_id, tags_to_add)

        # Remove unselected tag associations
        if tags_to_remove:
            remove_tags_from_task(task_id, tags_to_remove)

    task_tests = get_task_tests()
    if task_tests != task_details["tests"]:
        update_tests_for_task(task_id, task_tests)

    refresh_tasks()
    set_toast("Task updated")
    st.rerun()


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

    header_container.subheader("Add tests")
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

    with st.form("add_test", clear_on_submit=True):

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

            set_toast("Added test!")

        st.text("Inputs")
        for i in range(num_test_inputs):
            st.text_area(
                f"Input {i + 1}",
                key=f"new_test_input_{i}",
                label_visibility="collapsed",
            )

        st.text("Output")
        st.text_area("Output", key="test_output", label_visibility="collapsed")
        st.text("Description (optional)")
        st.text_area(
            "Description", key="test_description", label_visibility="collapsed"
        )

        st.form_submit_button("Add Test", on_click=add_test)


def context_addition_form():
    if st.checkbox(
        "I want to add supporting material for AI to use as reference",
        False,
        key="task_has_context",
    ):
        st.text_area(
            "Supporting material",
            key="task_context",
            placeholder="e.g. any information that is proprietary or not available in the public domain but is required to answer the task",
            help="AI will use this supporting material to assess the student's response and give feedback",
        )


def milestone_selector():
    return st.selectbox(
        "Milestone",
        st.session_state.milestones,
        key="task_milestone",
        format_func=lambda row: row["name"],
        index=None,
        help="If you don't see the milestone you want, you can create a new one from the `Milestones` tab",
    )


def cohort_selector(key_suffix: str, default=None):
    return st.multiselect(
        "Cohorts",
        st.session_state.cohorts,
        key=f"course_cohorts_{key_suffix}",
        default=default,
        format_func=lambda row: row["name"],
        help="If you don't see the cohort you want, you can create a new one from the `Cohorts` tab",
    )


def course_selector(key_prefix: str, default=None):
    return st.multiselect(
        "Courses",
        st.session_state.courses,
        default=default,
        key=f"selected_{key_prefix}_courses",
        format_func=lambda row: row["name"],
        help="If you don't see the course you want, you can create a new one from the `Courses` tab",
    )


def task_input_type_selector():
    return st.selectbox(
        "Select input type",
        all_input_types,
        key="task_input_type",
        index=None,
        on_change=clear_task_ai_response_type,
    )


def clear_task_input_type():
    if "task_input_type" in st.session_state:
        st.session_state.task_input_type = None


def clear_task_ai_response_type():
    if "task_ai_response_type" in st.session_state:
        st.session_state.task_ai_response_type = None


def ai_response_type_selector():
    if not st.session_state.task_input_type:
        return

    options = allowed_ai_response_types[st.session_state.task_input_type]

    disabled = False
    if len(options) == 1:
        disabled = True
        st.session_state.task_ai_response_type = options[0]

    return st.selectbox(
        "Select AI response type",
        options,
        key="task_ai_response_type",
        help=response_type_help_text,
        disabled=disabled,
    )


def task_type_selector(disabled: bool = False):
    return st.selectbox(
        "Select task type",
        task_type_mapping,
        key="task_type",
        format_func=lambda value: value["label"],
        on_change=clear_task_input_type,
        disabled=disabled,
    )


def coding_language_selector():
    if (
        "coding_languages" in st.session_state
        and st.session_state.coding_languages is None
    ):
        st.session_state.coding_languages = []

    return st.multiselect(
        "Code editor language (s)",
        coding_languages_supported,
        help="Choose or more languages to show in the code editor",
        key="coding_languages",
    )


def add_scoring_criterion(scoring_criteria):
    scoring_criteria.append(
        {
            "category": st.session_state.new_scoring_criterion_category,
            "description": st.session_state.new_scoring_criterion_description,
            "range": [
                st.session_state.new_scoring_criterion_range_start,
                st.session_state.new_scoring_criterion_range_end,
            ],
        }
    )

    st.session_state.new_scoring_criterion_category = ""
    st.session_state.new_scoring_criterion_description = ""
    st.session_state.new_scoring_criterion_range_start = 0
    st.session_state.new_scoring_criterion_range_end = 1


def update_scoring_criterion(index: int):
    st.session_state.scoring_criteria[index] = {
        "category": st.session_state[f"scoring_criterion_category_{index}"],
        "description": st.session_state[f"scoring_criterion_description_{index}"],
        "range": [
            st.session_state[f"scoring_criterion_range_start_{index}"],
            st.session_state[f"scoring_criterion_range_end_{index}"],
        ],
    }


def delete_scoring_criterion(scoring_criteria, index_to_delete: int):
    scoring_criteria.pop(index_to_delete)


def show_scoring_criteria_addition_form(scoring_criteria):
    st.subheader("Scoring Criterion")
    for index, scoring_criterion in enumerate(scoring_criteria):
        with st.expander(
            f"{scoring_criterion['category']} ({scoring_criterion['range'][0]} - {scoring_criterion['range'][1]})"
        ):
            cols = st.columns([2, 0.5, 1])
            cols[-1].button(
                "Delete",
                icon="🗑️",
                key=f"delete_scoring_criterion_{index}",
                on_click=delete_scoring_criterion,
                args=(scoring_criteria, index),
                help="Delete",
                type="primary",
            )

            updated_category = st.text_input(
                "Category",
                value=scoring_criterion["category"],
                key=f"scoring_criterion_category_{index}",
                autocomplete="off",
            )
            updated_description = st.text_input(
                "Description",
                value=scoring_criterion["description"],
                key=f"scoring_criterion_description_{index}",
                autocomplete="off",
            )
            cols = st.columns(2)
            updated_range_start = cols[0].number_input(
                "Min Score",
                min_value=0,
                step=1,
                value=scoring_criterion["range"][0],
                key=f"scoring_criterion_range_start_{index}",
            )
            range_end_min_value = updated_range_start + 1
            range_end_default_value = (
                scoring_criterion["range"][1]
                if scoring_criterion["range"][1] >= range_end_min_value
                else range_end_min_value
            )
            updated_range_end = cols[1].number_input(
                "Max Score",
                min_value=range_end_min_value,
                step=1,
                value=range_end_default_value,
                key=f"scoring_criterion_range_end_{index}",
            )

            if (
                updated_category != scoring_criterion["category"]
                or updated_description != scoring_criterion["description"]
                or updated_range_start != scoring_criterion["range"][0]
                or updated_range_end != scoring_criterion["range"][1]
            ):
                st.button(
                    "Update Criterion",
                    type="primary",
                    use_container_width=True,
                    on_click=update_scoring_criterion,
                    args=(index,),
                )

    with st.form("add_scoring_criterion"):
        st.text_input(
            "Add a new category to the scoring criterion",
            placeholder="e.g. Correctness",
            key="new_scoring_criterion_category",
            autocomplete="off",
        )
        st.text_area(
            "Add a description for the new category",
            placeholder="e.g. The answer provided is correct",
            key="new_scoring_criterion_description",
        )
        cols = st.columns(2)
        range_start = cols[0].number_input(
            "Lowest possible score for this category",
            min_value=0,
            step=1,
            key="new_scoring_criterion_range_start",
        )
        cols[1].number_input(
            "Highest possible score for this category",
            min_value=range_start + 1,
            step=1,
            key="new_scoring_criterion_range_end",
        )
        st.form_submit_button(
            "Add criterion",
            use_container_width=True,
            on_click=add_scoring_criterion,
            args=(scoring_criteria,),
        )


def task_add_edit_form(mode: Literal["add", "edit"], **kwargs):
    task_type_selector(disabled=mode == "edit")

    if not st.session_state.task_type:
        return

    set_task_type_vars(st.session_state.task_type["value"])

    st.text_input(
        "Name", key="task_name", placeholder="e.g. Purrfect Tales", autocomplete="off"
    )
    st.text_area(
        "Description",
        key="task_description",
        placeholder="e.g. Write a short story about a cat",
    )

    task_answer = None
    if st.session_state.is_task_type_question:
        context_addition_form()
        cols = st.columns(2)

        with cols[0]:
            input_type = task_input_type_selector()

        if not input_type:
            return

        with cols[1]:
            ai_response_type = ai_response_type_selector()

        if not ai_response_type:
            return

        if input_type == "coding":
            coding_language_selector()

            # test cases
            if st.checkbox("I want to add tests", False, key="task_has_tests"):
                add_tests_to_task(
                    st.session_state.task_name,
                    st.session_state.task_description,
                    mode="add",
                )

        if ai_response_type in ["chat", "exam"]:
            cols = st.columns([3.5, 1])

            cols[-1].container(height=10, border=False)
            is_task_details_missing = (
                not st.session_state.task_description or not st.session_state.task_name
            )
            is_generate_answer_disabled = (
                is_task_details_missing or st.session_state.final_answer != ""
            )
            generate_help_text = (
                "Task name or description is missing"
                if is_task_details_missing
                else "Answer already added" if is_generate_answer_disabled else ""
            )
            if cols[-1].button(
                "Generate",
                disabled=is_generate_answer_disabled,
                key="generate_answer",
                help=generate_help_text,
            ):
                with cols[0]:
                    generate_answer_for_form_task()

            task_answer = cols[0].text_area(
                "Answer",
                key="final_answer",
                placeholder="If your task has a correct answer, write it here",
                value=st.session_state.ai_answer,
            )
            if not task_answer and st.session_state.ai_answer:
                task_answer = st.session_state.ai_answer

        elif ai_response_type == "report":
            show_scoring_criteria_addition_form(st.session_state.scoring_criteria)
            st.divider()

    st.multiselect(
        "Tags",
        st.session_state.tags,
        key="task_tags",
        default=None,
        format_func=lambda tag: tag["name"],
        help="If you don't see the tag you want, you can create a new one from the `Tags` tab",
    )

    cols = st.columns(2)
    with cols[0]:
        milestone_selector()

    with cols[1]:
        course_selector("task")

    st.session_state.task_answer = task_answer

    if mode == "add":
        if st.button(
            "Add task",
            use_container_width=True,
            type="primary",
        ):
            add_new_task()

    if mode == "edit":
        if st.button(
            "Update task",
            use_container_width=True,
            type="primary",
        ):
            edit_task(**kwargs)


@st.dialog("Add a new task")
def show_task_addition_form():
    task_add_edit_form("add")


@st.dialog("Edit a task")
def show_task_edit_form(task_details):
    task_add_edit_form("edit", task_details=task_details)


async def generate_answer_for_bulk_task(task_row_index, task_name, task_description):
    answer = await generate_answer_for_task(
        task_name,
        task_description,
        get_task_context(),
        model["version"],
        decrypt_openai_api_key(st.session_state.org["openai_api_key"]),
    )
    return task_row_index, answer


def update_progress_bar(progress_bar, count, num_tasks, message):
    progress_bar.progress(count / num_tasks, text=f"{message} ({count}/{num_tasks})")


async def generate_answers_for_tasks(tasks_df):
    set_ai_running()
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

    answers = [None] * num_tasks

    for completed_task in asyncio.as_completed(coroutines):
        task_row_index, answer = await completed_task

        answers[task_row_index] = answer
        count += 1

        update_progress_bar(
            progress_bar, count, num_tasks, "Generating answers for tasks..."
        )

    progress_bar.empty()
    reset_ai_running()

    return answers


def bulk_upload_tasks_to_db(tasks_df: pd.DataFrame):
    error_text = validate_task_metadata_params()
    if error_text:
        st.error(error_text)
        return

    # all tasks are verified for now, the verified/non-verified flow is confusing
    # verified = True

    has_tags = "Tags" in tasks_df.columns

    if has_tags:
        unique_tags = list(
            set(
                list(
                    itertools.chain(
                        *tasks_df["Tags"]
                        .apply(
                            lambda val: (
                                [tag.strip() for tag in val.split(",")]
                                if not isinstance(val, float)
                                else []
                            )
                        )
                        .tolist()
                    )
                )
            )
        )
        has_new_tags = create_bulk_tags(unique_tags, st.session_state.org_id)
        if has_new_tags:
            refresh_tags()

    new_task_ids = []
    for _, row in tasks_df.iterrows():
        task_tags = []
        if has_tags:
            task_tag_names = (
                [tag.strip() for tag in row["Tags"].split(",")]
                if not isinstance(row["Tags"], float)
                else []
            )
            if task_tag_names:
                task_tags = [
                    tag
                    for tag in st.session_state.tags
                    if tag["name"] in task_tag_names
                ]

        if (
            st.session_state.is_task_type_question
            and st.session_state.task_ai_response_type in ["chat", "exam"]
        ):
            answer = row["Answer"]
        else:
            answer = None

        context = get_task_context()
        task_id = store_task_to_db(
            row["Name"],
            row["Description"],
            answer,
            task_tags,
            st.session_state.task_input_type,
            st.session_state.task_ai_response_type,
            st.session_state.coding_languages,
            model["version"],
            True,
            [],
            (
                st.session_state.task_milestone["id"]
                if st.session_state.task_milestone is not None
                else None
            ),
            st.session_state.org_id,
            context,
            st.session_state.task_type["value"],
        )
        new_task_ids.append(task_id)

    if st.session_state.selected_task_courses:
        course_tasks_to_add = list(
            itertools.chain(
                *[
                    [(task_id, course["id"]) for task_id in new_task_ids]
                    for course in st.session_state.selected_task_courses
                ]
            )
        )
        add_tasks_to_courses(course_tasks_to_add)

    if st.session_state.scoring_criteria:
        add_scoring_criteria_to_tasks(new_task_ids, st.session_state.scoring_criteria)

    refresh_tasks()
    st.rerun()


def complete_bulk_update_tasks():
    refresh_tasks()
    set_toast("Tasks updated")
    st.rerun()


def show_bulk_update_milestone_tab(all_tasks):
    with st.form("bulk_update_tasks_milestone_form", border=False):
        milestone_selector()

        if st.form_submit_button(
            "Update all tasks", type="primary", use_container_width=True
        ):
            task_ids = [task["id"] for task in all_tasks]
            update_column_for_task_ids(
                task_ids, "milestone_id", st.session_state.task_milestone["id"]
            )

            complete_bulk_update_tasks()


def show_bulk_update_courses_tab(all_tasks):
    with st.form("bulk_update_tasks_courses_form", border=False):
        course_selector("task")

        if st.form_submit_button(
            "Update all tasks", type="primary", use_container_width=True
        ):
            for task in all_tasks:
                update_task_courses(task)

            complete_bulk_update_tasks()


def show_bulk_update_scoring_criteria_tab(all_tasks):
    show_scoring_criteria_addition_form(st.session_state.scoring_criteria)

    if st.button("Update all tasks", type="primary", use_container_width=True):
        for task in all_tasks:
            update_task_scoring_criteria(task)

        complete_bulk_update_tasks()


@st.dialog("Bulk edit tasks")
def show_bulk_edit_tasks_form(all_tasks):
    # is_incomplete = show_bulk_tasks_metadata_form(mode="edit")
    unique_task_response_types = list(
        set([task["response_type"] for task in all_tasks])
    )

    update_type_tabs = ["Milestone", "Courses"]

    if (
        len(unique_task_response_types) == 1
        and unique_task_response_types[0] == "report"
    ):
        st.session_state.task_ai_response_type = "report"
        update_type_tabs.append("Scoring criteria")

    tabs = st.tabs(update_type_tabs)

    with tabs[0]:
        show_bulk_update_milestone_tab(all_tasks)

    with tabs[1]:
        show_bulk_update_courses_tab(all_tasks)

    if len(tabs) == 3:
        with tabs[2]:
            show_bulk_update_scoring_criteria_tab(all_tasks)


@st.dialog("Bulk upload tasks")
def show_bulk_upload_tasks_form():
    task_type_selector()

    if not st.session_state.task_type:
        return

    set_task_type_vars(st.session_state.task_type["value"])
    context_addition_form()

    if st.session_state.is_task_type_question:
        cols = st.columns(2)

        with cols[0]:
            input_type = task_input_type_selector()

        if not input_type:
            return

        with cols[1]:
            ai_response_type = ai_response_type_selector()

        if not ai_response_type:
            return

        if input_type == "coding":
            coding_language_selector()

        if ai_response_type == "report":
            show_scoring_criteria_addition_form(st.session_state.scoring_criteria)
            st.divider()

    cols = st.columns(2)
    with cols[0]:
        milestone_selector()

    with cols[1]:
        course_selector("task", default=None)

    file_uploader_label = "Choose a CSV file with the columns:\n\n`Name`, `Description`, `Tags` (Optional)"
    if (
        st.session_state.is_task_type_question
        and st.session_state.task_ai_response_type in ["chat", "exam"]
    ):
        file_uploader_label += ", `Answer` (optional)"

    uploaded_file = st.file_uploader(
        file_uploader_label,
        type="csv",
        key=f"bulk_upload_tasks_{st.session_state.task_uploader_key}",
    )

    if uploaded_file:
        display_container = st.empty()
        tasks_df = pd.read_csv(uploaded_file)

        column_config = {
            "Name": st.column_config.TextColumn(width="small"),
            "Description": st.column_config.TextColumn(width="medium"),
        }

        display_container.dataframe(
            tasks_df, hide_index=True, column_config=column_config
        )

        error_message = None
        for index, row in tasks_df.iterrows():
            if not row["Name"] or (
                isinstance(row["Name"], float) and math.isnan(row["Name"])
            ):
                error_message = f"Task name missing for row {index + 1}"
                break
            if not row["Description"] or (
                isinstance(row["Description"], float) and math.isnan(row["Description"])
            ):
                error_message = f"Task description missing for row {index + 1}"
                break

        if error_message:
            st.error(error_message)
            return

        if (
            st.session_state.is_task_type_question
            and st.session_state.task_ai_response_type in ["chat", "exam"]
            and "Answer" not in tasks_df.columns
        ):
            if st.session_state.ai_answers is None:
                st.session_state.ai_answers = asyncio.run(
                    generate_answers_for_tasks(tasks_df)
                )
                tasks_df["Answer"] = st.session_state.ai_answers
                st.toast("Added AI generated answers")
            else:
                tasks_df["Answer"] = st.session_state.ai_answers

            # verified = False
            display_container.dataframe(
                tasks_df, hide_index=True, column_config=column_config
            )

        if st.button(
            "Add tasks",
            use_container_width=True,
            type="primary",
            disabled=st.session_state.is_ai_running,
        ):
            bulk_upload_tasks_to_db(tasks_df)


def delete_tasks_from_list(task_ids):
    delete_tasks_from_db(task_ids)
    refresh_tasks()
    st.rerun()


@st.dialog("Delete tasks")
def show_tasks_delete_confirmation(
    task_ids,
):
    st.write("Are you sure you want to delete the selected tasks?")

    confirm_col, cancel_col, _, _ = st.columns([1, 1, 2, 2])
    if confirm_col.button("Yes", use_container_width=True):
        delete_tasks_from_list(
            task_ids,
        )
        st.rerun()

    if cancel_col.button("No", use_container_width=True, type="primary"):
        st.rerun()


def update_tasks_with_new_value(
    task_ids: List[int],
    column_to_update: str,
    new_value: str,
):
    update_column_for_task_ids(task_ids, column_to_update, new_value)
    refresh_tasks()
    st.rerun()


layout_cols = st.columns([1, 0.2, 6])

if "selected_section_index" not in st.session_state:
    st.session_state.selected_section_index = 0


def change_selected_section(section_index: int):
    st.session_state.selected_section_index = section_index


with layout_cols[0]:
    sections = ["Dashboard", "Analytics", "Settings"]
    st.markdown(
        "<hr style='margin: 0px; margin-bottom: 10px; margin-top: 20px;'>",
        unsafe_allow_html=True,
    )

    for section_index, section in enumerate(sections):
        st.button(
            section,
            key=f"section_{section_index}",
            type="tertiary",
            disabled=st.session_state.selected_section_index == section_index,
            on_click=change_selected_section,
            args=(section_index,),
        )
        st.markdown("<hr style='margin: 0px;'>", unsafe_allow_html=True)

    # Add custom CSS to style the disabled button
    st.markdown(
        """
        <style>
            div[class*="st-key-section_"] .stButton button:disabled {
                color: #FC4A4A;
                background-color: transparent !important;
                border-color: transparent !important;
            }
        </style>
    """,
        unsafe_allow_html=True,
    )


def show_vertical_divider(height: int = 320):
    st.html(
        f"""
                <div class="divider-vertical-line" style="height: {height}px;"></div>
                <style>
                    .divider-vertical-line {{
                        border-left: 2px solid rgba(60, 64, 68, 0.8);
                        height: {height}px;
                        margin: auto;
                        margin-top: 20px;
                    }}
                </style>
            """
    )


with layout_cols[1]:
    show_vertical_divider()

if st.session_state.selected_section_index == 0:
    tab_names = ["Cohorts", "Courses", "Tasks", "Milestones", "Tags"]

    with layout_cols[-1]:
        tabs = st.tabs(tab_names)

    def set_task_form_with_task_details(task_details: dict):
        st.session_state.task_name = task_details["name"]
        st.session_state.task_description = task_details["description"]

        _all_task_types = [task_type["value"] for task_type in task_type_mapping]
        st.session_state["task_type"] = task_type_mapping[
            _all_task_types.index(task_details["type"])
        ]

        st.session_state.task_has_context = bool(task_details["context"])
        st.session_state.task_context = task_details["context"]

        if task_details["milestone_id"]:
            all_milestone_ids = [
                milestone["id"] for milestone in st.session_state.milestones
            ]
            selected_milestone_index = all_milestone_ids.index(
                task_details["milestone_id"]
            )
            st.session_state["task_milestone"] = st.session_state.milestones[
                selected_milestone_index
            ]

        all_tag_ids = [tag["id"] for tag in st.session_state.tags]
        task_tag_ids = [tag["id"] for tag in task_details["tags"]]
        selected_tag_indices = [
            index for index, tag_id in enumerate(all_tag_ids) if tag_id in task_tag_ids
        ]
        st.session_state["task_tags"] = [
            st.session_state.tags[index] for index in selected_tag_indices
        ]

        all_course_ids = [course["id"] for course in st.session_state.courses]
        task_course_ids = [course["id"] for course in task_details["courses"]]
        selected_course_indices = [
            index
            for index, course_id in enumerate(all_course_ids)
            if course_id in task_course_ids
        ]
        st.session_state["selected_task_courses"] = [
            st.session_state.courses[index] for index in selected_course_indices
        ]

        if task_details["type"] == "reading_material":
            return

        st.session_state["task_ai_response_type"] = task_details["response_type"]
        st.session_state["task_input_type"] = task_details["input_type"]

        if task_details["response_type"] in ["exam", "chat"]:
            st.session_state.final_answer = task_details["answer"]
        elif task_details["response_type"] == "report":
            # response_type = report
            task_details["scoring_criteria"] = get_scoring_criteria_for_task(
                task_details["id"]
            )
            st.session_state.scoring_criteria = deepcopy(
                task_details["scoring_criteria"]
            )
            for scoring_criterion in st.session_state.scoring_criteria:
                scoring_criterion.pop("id")
        else:
            raise NotImplementedError()

        if task_details["input_type"] == "coding":
            st.session_state.coding_languages = task_details["coding_language"]

        if task_details["tests"]:
            st.session_state.task_has_tests = True
            st.session_state.tests = task_details["tests"]

    def set_bulk_task_form_with_task_details(all_tasks: List[dict]):
        set_task_type_vars(all_tasks[0]["type"])

        # all_task_contexts = [task["context"] for task in all_tasks]
        # all_task_contexts = list(set(all_task_contexts))
        # if len(all_task_contexts) == 1 and all_task_contexts[0]:
        #     st.session_state.task_has_context = True
        #     st.session_state.task_context = all_task_contexts[0]

        all_task_ai_response_types = [task["response_type"] for task in all_tasks]
        all_task_ai_response_types = list(set(all_task_ai_response_types))
        if len(all_task_ai_response_types) == 1:
            default_task_ai_response_type = all_task_ai_response_types[0]
            # st.session_state["task_ai_response_type"] = default_task_ai_response_type

            if default_task_ai_response_type == "report":
                scoring_criteria_all_tasks = get_scoring_criteria_for_tasks(
                    [task["id"] for task in all_tasks]
                )
                for task, task_scoring_criteria in zip(
                    all_tasks, scoring_criteria_all_tasks
                ):
                    task["scoring_criteria"] = task_scoring_criteria

                combined_scoring_criteria = list(
                    itertools.chain.from_iterable(scoring_criteria_all_tasks)
                )

                if len(combined_scoring_criteria):
                    sc_df = pd.DataFrame(combined_scoring_criteria)

                    sc_df = sc_df.drop(columns=["id"])
                    sc_df["range"] = sc_df["range"].apply(lambda x: f"{x[0]}-{x[1]}")

                    sc_df = sc_df.drop_duplicates()

                    if len(sc_df) == len(scoring_criteria_all_tasks[0]):
                        st.session_state.scoring_criteria = deepcopy(
                            scoring_criteria_all_tasks[0]
                        )
                        for scoring_criterion in st.session_state.scoring_criteria:
                            scoring_criterion.pop("id")

        # all_task_input_types = [task["input_type"] for task in all_tasks]
        # all_task_input_types = list(set(all_task_input_types))
        # if len(all_task_input_types) == 1:
        #     default_task_input_type = all_task_input_types[0]
        #     st.session_state["task_input_type"] = default_task_input_type

        #     if default_task_input_type == "coding":
        #         all_task_coding_languages = [task["coding_language"] for task in all_tasks]
        #         all_task_coding_languages = list(set(all_task_coding_languages))
        #         if len(all_task_coding_languages) == 1:
        #             st.session_state.coding_languages = all_task_coding_languages[0]

        all_task_milestone_ids = [task["milestone_id"] for task in all_tasks]
        all_task_milestone_ids = list(set(all_task_milestone_ids))
        if len(all_task_milestone_ids) == 1 and all_task_milestone_ids[0]:
            all_milestone_ids = [
                milestone["id"] for milestone in st.session_state.milestones
            ]
            selected_milestone_index = all_milestone_ids.index(
                all_task_milestone_ids[0]
            )
            st.session_state.task_milestone = st.session_state.milestones[
                selected_milestone_index
            ]

        all_task_course_ids = [
            [course["id"] for course in task["courses"]] for task in all_tasks
        ]

        has_same_courses = False
        try:
            all_task_course_ids = np.unique(all_task_course_ids, axis=0)
            if len(all_task_course_ids) == 1:
                has_same_courses = True
        except:
            # list of lists is not convertible to numpy array
            # as all the sublists don't have the same length
            pass

        if has_same_courses:
            default_course_ids = all_task_course_ids[0]
            all_course_ids = [course["id"] for course in st.session_state.courses]
            selected_course_indices = [
                index
                for index, course_id in enumerate(all_course_ids)
                if course_id in default_course_ids
            ]
            st.session_state["selected_task_courses"] = [
                st.session_state.courses[index] for index in selected_course_indices
            ]

    def show_tasks_tab():
        if is_empty_openai_api_key():
            st.error(
                """No OpenAI API key found. Please set an API key in the `"Settings"` section."""
            )
            return

        cols = st.columns([1, 6])

        add_task = cols[0].button("Add a new task", type="primary")

        bulk_upload_tasks = cols[1].button("Bulk upload tasks")

        if add_task:
            reset_task_form()
            show_task_addition_form()

        if bulk_upload_tasks:
            reset_task_form()
            update_task_uploader_key()
            show_bulk_upload_tasks_form()

        refresh_tasks()

        if not st.session_state.tasks:
            st.error("No tasks added yet")
            return

        df = pd.DataFrame(st.session_state.tasks)
        df = df.replace({np.nan: None})

        df["coding_language"] = df["coding_language"].apply(
            lambda x: x.split(",") if isinstance(x, str) else x
        )
        df["num_tests"] = df["tests"].apply(
            lambda x: len(x) if isinstance(x, list) else 0
        )

        cols = st.columns([1, 1, 1, 1])

        filtered_response_types = cols[0].pills(
            "Filter by response type",
            all_ai_response_types,
        )

        if filtered_response_types:
            df = df[
                df["response_type"].apply(
                    lambda x: x in filtered_response_types if x is not None else False
                )
            ]

        filtered_input_types = cols[1].pills(
            "Filter by input type",
            all_input_types,
        )

        if filtered_input_types:
            df = df[
                df["input_type"].apply(
                    lambda x: x in filtered_input_types if x is not None else False
                )
            ]

        filtered_types = cols[2].pills(
            "Filter by type",
            task_type_mapping,
            format_func=lambda x: x["label"],
            selection_mode="multi",
        )

        if filtered_types:
            filtered_type_values = [x["value"] for x in filtered_types]
            df = df[df["type"].apply(lambda x: x in filtered_type_values)]

        filtered_milestones = cols[3].multiselect(
            "Filter by milestone",
            st.session_state.milestones,
            format_func=lambda x: x["name"],
        )

        if filtered_milestones:
            filtered_milestone_ids = [
                milestone["id"] for milestone in filtered_milestones
            ]
            df = df[df["milestone_id"].apply(lambda x: x in filtered_milestone_ids)]

        if not len(df):
            st.error("No tasks matching the filters")
            return

        column_config = {
            # 'id': None
            # "verified": st.column_config.CheckboxColumn(label="Is task verified?"),
            "name": st.column_config.TextColumn(label="Name"),
            "description": st.column_config.TextColumn(
                width="medium", label="Description"
            ),
            "answer": st.column_config.TextColumn(width="medium", label="Answer"),
            "milestone_name": st.column_config.TextColumn(label="Milestone"),
            "response_type": st.column_config.TextColumn(label="AI response type"),
            "input_type": st.column_config.TextColumn(label="User input type"),
        }

        task_id_to_courses = get_courses_for_tasks(df["id"].tolist())
        df["courses"] = df["id"].apply(lambda x: task_id_to_courses[x])

        df["Courses"] = df["courses"].apply(lambda x: [course["name"] for course in x])
        df["Tags"] = df["tags"].apply(lambda x: [tag["name"] for tag in x])
        df["Task Type"] = df["type"].apply(lambda x: task_type_to_label[x])

        column_order = [
            "id",
            # "verified",
            # "num_tests",
            "Task Type",
            "name",
            "description",
            # "answer",
            "Tags",
            "milestone_name",
            "Courses",
            "input_type",
            "response_type",
            # "coding_language",
            # "generation_model",
            # "timestamp",
        ]

        delete_col, edit_task_col = st.columns([1, 6])

        error_container = st.container()

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

            if delete_col.button("Delete tasks", icon="🗑️"):
                # import ipdb; ipdb.set_trace()
                show_tasks_delete_confirmation(
                    task_ids,
                )

            all_tasks = [
                row.to_dict() for _, row in df.iloc[event.selection["rows"]].iterrows()
            ]

            if len(task_ids) == 1:
                task_details = all_tasks[0]
                if edit_task_col.button("Edit task", icon="🖊️"):
                    reset_task_form()
                    set_task_form_with_task_details(task_details)
                    show_task_edit_form(task_details=task_details)
            else:
                if edit_task_col.button("Bulk edit tasks", icon="🖊️"):
                    task_types = set([task["type"] for task in all_tasks])
                    if len(task_types) > 1:
                        error_container.error(
                            """All tasks must be of the same type (i.e. either all tasks are `"Reading Material"` or all tasks are `"Question"`) for bulk editing"""
                        )
                        return

                    reset_task_form()
                    set_bulk_task_form_with_task_details(all_tasks)
                    show_bulk_edit_tasks_form(all_tasks)

    with tabs[2]:
        show_tasks_tab()

    @st.dialog("Create Cohort")
    def show_create_cohort_dialog():
        with st.form("create_cohort_form", border=False):
            cohort_name = st.text_input("Enter cohort name", autocomplete="off")

            if st.form_submit_button(
                "Create",
                type="primary",
                use_container_width=True,
            ):
                if not cohort_name:
                    st.error("Enter a cohort name")
                    return

                create_cohort(cohort_name, st.session_state.org_id)
                refresh_cohorts()
                if "tasks" in st.session_state and st.session_state.tasks:
                    refresh_tasks()

                st.session_state.current_cohort_index = (
                    len(st.session_state.cohorts) - 1
                )
                set_toast(f"Cohort `{cohort_name}` created successfully!")
                st.rerun()

    @st.dialog("Add Members to Cohort")
    def show_add_members_to_cohort_dialog(cohort_id: int, cohort_info: dict, role: str):
        existing_members = set([member["email"] for member in cohort_info["members"]])

        tabs = st.tabs(["Add Members", "Bulk Upload Members"])

        with tabs[0]:
            with st.form("add_cohort_member_form", border=False):
                member_email = st.text_input(
                    "Enter email", key="cohort_member_email", autocomplete="off"
                )

                submit_button = st.form_submit_button(
                    "Add Member",
                    use_container_width=True,
                    type="primary",
                )
                if submit_button:
                    try:
                        # Check that the email address is valid
                        member_email = validate_email(member_email)

                        if member_email.normalized in existing_members:
                            st.error(
                                f"Member {member_email.normalized} already exists in cohort"
                            )
                            return

                        add_members_to_cohort(
                            cohort_id, [member_email.normalized], [role]
                        )
                        refresh_cohorts()
                        set_toast("Member added successfully")
                        st.rerun()
                    except EmailNotValidError as e:
                        # The exception message is human-readable explanation of why it's
                        # not a valid (or deliverable) email address.
                        st.error("Invalid email")

        with tabs[1]:
            columns = [
                "Email",
            ]
            uploaded_file = st.file_uploader(
                f"Choose a CSV file with a column named `Email`",
                type="csv",
                key=f"cohort_uploader_{st.session_state.cohort_uploader_key}",
            )

            if not uploaded_file:
                return

            cohort_df = pd.read_csv(uploaded_file)
            if cohort_df.columns.tolist() != columns:
                st.error("The uploaded file does not have the correct columns.")
                return

            for email in cohort_df["Email"].tolist():
                try:
                    validate_email(email)
                except EmailNotValidError as e:
                    st.error(f"Invalid email: {email}")
                    return

                if email in existing_members:
                    st.error(f"Member {email} already exists in cohort")
                    return

            st.dataframe(cohort_df, hide_index=True, use_container_width=True)

            if st.button(
                "Add Members",
                use_container_width=True,
                key="bulk_upload_cohort_members",
                type="primary",
            ):
                add_members_to_cohort(
                    cohort_id,
                    cohort_df["Email"].tolist(),
                    [role] * len(cohort_df),
                )
                refresh_cohorts()
                set_toast(f"Members added to cohort successfully!")
                update_cohort_uploader_key()
                st.rerun()

    def group_create_edit_form(
        key: str,
        cohort_id: int,
        cohort_info: dict,
        mode: Literal["create", "edit"] = "create",
        group_id: int = None,
        group_name: str = "",
        learners: List[Dict] = [],
        mentors: List[Dict] = [],
    ):
        with st.form(key, border=False):
            new_group_name = st.text_input(
                "Enter group name",
                key="cohort_group_name",
                value=group_name,
                autocomplete="off",
            )

            learner_options = [
                member
                for member in cohort_info["members"]
                if member["role"] == group_role_learner
            ]
            default_learners = [learner["id"] for learner in learners]
            default_learners_selected = [
                learner
                for learner in learner_options
                if learner["id"] in default_learners
            ]

            selected_learners = st.multiselect(
                "Select learners",
                learner_options,
                key="cohort_group_learners",
                format_func=lambda x: x["email"],
                default=default_learners_selected,
            )

            mentor_options = [
                member
                for member in cohort_info["members"]
                if member["role"] == group_role_mentor
            ]
            all_mentor_ids = [mentor["id"] for mentor in mentors]
            default_mentors = [mentor["id"] for mentor in mentors]
            default_mentors_selected = [
                mentor for mentor in mentor_options if mentor["id"] in default_mentors
            ]

            selected_mentors = st.multiselect(
                "Select mentors",
                mentor_options,
                key="cohort_group_mentors",
                format_func=lambda x: x["email"],
                default=default_mentors_selected,
            )

            form_submit_button_text = (
                "Create Group" if mode == "create" else "Save Changes"
            )

            if st.form_submit_button(
                form_submit_button_text,
                use_container_width=True,
                type="primary",
            ):
                if not new_group_name:
                    st.error("Enter a group name")
                    return

                if not selected_learners:
                    st.error("Select at least one learner")
                    return

                if not selected_mentors:
                    st.error("Select at least one mentor")
                    return

                if mode == "create":
                    create_cohort_group(
                        new_group_name,
                        cohort_id,
                        [
                            member["id"]
                            for member in selected_learners + selected_mentors
                        ],
                    )
                    for mentor in selected_mentors:
                        clear_cache_for_mentor_groups(mentor["id"], cohort_id)

                    set_toast(f"Cohort group created successfully!")
                else:
                    if new_group_name != group_name:
                        update_cohort_group_name(group_id, new_group_name)

                    if selected_learners != learners or selected_mentors != mentors:
                        existing_member_ids = [
                            learner["id"] for learner in learners
                        ] + [mentor["id"] for mentor in mentors]

                        new_member_ids = [
                            learner["id"] for learner in selected_learners
                        ] + [mentor["id"] for mentor in selected_mentors]

                        member_ids_to_add = [
                            member_id
                            for member_id in new_member_ids
                            if member_id not in existing_member_ids
                        ]
                        add_members_to_cohort_group(group_id, member_ids_to_add)

                        member_ids_to_remove = [
                            member_id
                            for member_id in existing_member_ids
                            if member_id not in new_member_ids
                        ]
                        remove_members_from_cohort_group(group_id, member_ids_to_remove)

                        for mentor_id in member_ids_to_add + member_ids_to_remove:
                            if mentor_id not in all_mentor_ids:
                                continue

                            clear_cache_for_mentor_groups(mentor_id, cohort_id)

                    set_toast(f"Cohort group updated successfully!")

                refresh_cohorts()
                st.rerun()

    @st.dialog("Create Cohort Group")
    def show_create_group_dialog(cohort_id: int, cohort_info: dict):
        group_create_edit_form(
            "create_group_form",
            cohort_id,
            cohort_info,
        )

    @st.dialog("Edit Cohort Group")
    def show_edit_cohort_group_dialog(
        cohort_id: int,
        cohort_info: dict,
        group: Dict,
        learners: List[Dict],
        mentors: List[Dict],
    ):
        group_create_edit_form(
            "edit_groups_form",
            cohort_id,
            cohort_info,
            mode="edit",
            group_id=group["id"],
            group_name=group["name"],
            learners=learners,
            mentors=mentors,
        )

    @st.dialog("Delete Cohort Group Confirmation")
    def show_delete_cohort_group_confirmation_dialog(group, cohort_id):
        st.markdown(f"Are you sure you want to delete the group: `{group['name']}`?")
        (
            confirm_col,
            cancel_col,
        ) = st.columns([1.5, 6])

        if confirm_col.button("Confirm", type="primary"):
            delete_cohort_group_from_db(group["id"])

            mentor_ids = [mentor["id"] for mentor in group["members"]]
            for mentor_id in mentor_ids:
                clear_cache_for_mentor_groups(mentor_id, cohort_id)

            refresh_cohorts()
            set_toast("Cohort group deleted successfully!")
            st.rerun()

        if cancel_col.button("Cancel"):
            st.rerun()

    @st.dialog("Remove Members from Cohort Confirmation")
    def show_cohort_members_delete_confirmation_dialog(
        cohort_id: int, members: List[Dict]
    ):
        st.markdown(
            f"Are you sure you want to delete the following members from cohort: {', '.join([member['email'] for member in members])}?"
        )
        (
            confirm_col,
            cancel_col,
        ) = st.columns([1.5, 6])

        if confirm_col.button("Confirm", type="primary"):
            remove_members_from_cohort(cohort_id, [member["id"] for member in members])
            refresh_cohorts()
            set_toast("Members removed from cohort successfully!")
            st.rerun()

        if cancel_col.button("Cancel"):
            st.rerun()

    @st.dialog("Delete Cohort Confirmation")
    def show_delete_cohort_confirmation_dialog(cohort_id: int, cohort_info: Dict):
        st.markdown(
            f"Are you sure you want to delete the cohort: `{cohort_info['name']}`?"
        )
        (
            confirm_col,
            cancel_col,
        ) = st.columns([1.5, 6])

        if confirm_col.button("Confirm", type="primary"):
            delete_cohort(cohort_id)
            refresh_cohorts()

            # invalidate cache
            clear_cohort_cache_for_courses(cohort_info["courses"])

            del st.session_state.current_cohort_index

            set_toast("Cohort deleted successfully!")
            st.rerun()

        if cancel_col.button("Cancel"):
            st.rerun()

    @st.dialog("Update Cohort Courses")
    def show_update_cohort_courses_dialog(cohort_id: int, cohort_courses: List[Dict]):
        with st.form("update_cohort_courses_form", border=False):
            selected_courses = course_selector("cohort", default=cohort_courses)

            st.container(height=10, border=False)

            has_changes = selected_courses != cohort_courses

            if st.form_submit_button(
                "Update",
                type="primary",
                use_container_width=True,
            ):
                if not has_changes:
                    st.error("No changes made")
                    return

                courses_to_delete = [
                    course
                    for course in cohort_courses
                    if course not in selected_courses
                ]
                courses_to_add = [
                    course
                    for course in selected_courses
                    if course not in cohort_courses
                ]
                if courses_to_add:
                    add_courses_to_cohort(
                        cohort_id, [course["id"] for course in courses_to_add]
                    )
                if courses_to_delete:
                    remove_courses_from_cohort(
                        cohort_id, [course["id"] for course in courses_to_delete]
                    )

                refresh_cohorts()

                # invalidate cache
                clear_course_cache_for_cohorts([cohort_id])
                clear_cohort_cache_for_courses(courses_to_add + courses_to_delete)

                set_toast("Cohort updated successfully!")
                st.rerun()

    def show_cohort_overview(selected_cohort: Dict):
        cohort_info = get_cohort_by_id(selected_cohort["id"])

        cols = st.columns([1, 10])

        if cols[0].button("Edit", icon="🖊️", key="edit_cohort"):
            show_edit_cohort_form(selected_cohort)
        if cols[1].button("Delete", icon="🗑️", key="delete_cohort"):
            show_delete_cohort_confirmation_dialog(
                selected_cohort["id"], selected_cohort
            )

        learners = []
        mentors = []

        # Iterate through all groups in the cohort
        for member in cohort_info["members"]:
            if member["role"] == group_role_learner:
                learners.append(member)
            elif member["role"] == group_role_mentor:
                mentors.append(member)

        tab_names = ["Learners", "Mentors", "Groups", "Courses Assigned"]

        selected_tab = st.segmented_control(
            "Cohort Tabs", tab_names, label_visibility="hidden", default=tab_names[0]
        )

        def _show_courses_tab():
            if st.button("Add/Remove Courses"):
                show_update_cohort_courses_dialog(
                    selected_cohort["id"], selected_cohort["courses"]
                )

            if not selected_cohort["courses"]:
                st.info("No courses in this cohort")
            else:
                st.pills(
                    "Courses",
                    selected_cohort["courses"],
                    format_func=lambda x: x["name"],
                    disabled=True,
                    key="cohort_courses",
                    label_visibility="collapsed",
                )

        def _show_users_tab(users: List[Dict], key: str):
            action_cols = st.columns([1, 7])
            if action_cols[0].button("Add Members", key=f"add_member_{key}"):
                show_add_members_to_cohort_dialog(
                    selected_cohort["id"],
                    cohort_info,
                    group_role_learner if key == "learners" else group_role_mentor,
                )

            if not users:
                st.info(f"No {key} in this cohort")
                return

            action_error_container = st.container()

            event = st.dataframe(
                pd.DataFrame(users, columns=["email"]),
                on_select="rerun",
                selection_mode="multi-row",
                hide_index=True,
                use_container_width=True,
            )

            if len(event.selection["rows"]):
                if action_cols[1].button(
                    "Remove members", key=f"remove_cohort_members_{key}"
                ):
                    members_to_remove = [users[i] for i in event.selection["rows"]]
                    user_ids = [member["id"] for member in members_to_remove]
                    group_ids_for_members = get_cohort_group_ids_for_users(
                        user_ids, selected_cohort["id"]
                    )
                    if group_ids_for_members:
                        action_error_container.error(
                            "One or more selected members are part of a group. Please remove them from the group (s) first."
                        )
                        return

                    show_cohort_members_delete_confirmation_dialog(
                        selected_cohort["id"],
                        members_to_remove,
                    )

        def show_learners_tab():
            _show_users_tab(learners, "learners")

        def show_mentors_tab():
            _show_users_tab(mentors, "mentors")

        def show_groups_tab(cohort_info):
            if st.button("Create Group"):
                show_create_group_dialog(selected_cohort["id"], cohort_info)

            if not cohort_info["groups"]:
                st.info("No groups in this cohort")
                return

            cols = st.columns([1, 0.4, 1.8])

            # NOTE: DO NOT REMOVE THIS FORMATTING FOR THE DROPDOWN
            # OTHERWISE CHANGES IN THE COHORT LIKE ADDING/REMOVING MEMBERS
            # FROM THE WHOLE COHORT OR FROM A GROUP WILL NOT REFLECT IN THE DROPDOWN
            # WITHOUT AN EXPLICIT RERUN
            # FOR SOME REASON, ALTHOUGH cohort_info['groups'] IS UPDATED,
            # THE GROUP VIEW DOES NOT UPDATE UNLESS THE MEMBER INFO OF THE GROUP IS
            # USED IN THE FORMATTING OF THE DROPDOWN OPTIONS
            def format_group(group):
                group_mentors = [
                    member
                    for member in group["members"]
                    if member["role"] == group_role_mentor
                ]
                group_learners = [
                    member
                    for member in group["members"]
                    if member["role"] == group_role_learner
                ]
                return f'{group["name"]} ({show_singular_or_plural(len(group_learners), "learner")}, {show_singular_or_plural(len(group_mentors), "mentor")})'

            selected_group = cols[0].selectbox(
                "Select a group",
                cohort_info["groups"],
                format_func=format_group,
            )

            learners = [
                member
                for member in selected_group["members"]
                if member["role"] == group_role_learner
            ]

            mentors = [
                member
                for member in selected_group["members"]
                if member["role"] == group_role_mentor
            ]

            cols[1].container(height=10, border=False)
            cols[1].button(
                "Edit Group",
                on_click=show_edit_cohort_group_dialog,
                args=(
                    selected_cohort["id"],
                    cohort_info,
                    selected_group,
                    learners,
                    mentors,
                ),
            )
            cols[2].container(height=10, border=False)
            cols[2].button(
                "Delete Group",
                type="primary",
                on_click=show_delete_cohort_group_confirmation_dialog,
                args=(selected_group, selected_cohort["id"]),
            )

            cols = st.columns([2, 0.2, 1])

            with cols[0]:
                learners_df = pd.DataFrame(learners)

                st.subheader("Learners")
                st.dataframe(
                    learners_df,
                    hide_index=True,
                    use_container_width=True,
                    column_order=["email"],
                )

            with cols[-1]:
                st.subheader("Mentors")
                mentors_df = pd.DataFrame(mentors)
                st.dataframe(
                    mentors_df,
                    hide_index=True,
                    use_container_width=True,
                    column_order=["email"],
                )

        if selected_tab == tab_names[0]:
            show_learners_tab()

        if selected_tab == tab_names[1]:
            show_mentors_tab()

        if selected_tab == tab_names[2]:
            show_groups_tab(cohort_info)

        if selected_tab == tab_names[3]:
            _show_courses_tab()

    def update_cohort_name(cohort, new_name):
        update_cohort_name_in_db(cohort["id"], new_name)
        refresh_cohorts()

        # invalidate cache
        clear_cohort_cache_for_courses(cohort["courses"])

        set_toast("Cohort name updated successfully!")
        st.rerun()

    @st.dialog("Edit Cohort")
    def show_edit_cohort_form(selected_cohort):
        with st.form("update_cohort_name_form", border=False):
            cols = st.columns([1, 0.4])
            updated_cohort_name = cols[0].text_input(
                "Cohort Name", value=selected_cohort["name"], autocomplete="off"
            )
            cols[1].container(height=10, border=False)
            if cols[1].form_submit_button("Update"):
                if not updated_cohort_name:
                    st.error("Enter a cohort name")
                    return

                if updated_cohort_name == selected_cohort["name"]:
                    st.error("No changes made")
                    return

                update_cohort_name(selected_cohort, updated_cohort_name)

    def show_cohorts_tab():
        cols = st.columns([1.2, 0.5, 2])

        if (
            "current_cohort" in st.session_state
            and st.session_state.current_cohort not in st.session_state.cohorts
            and "current_cohort_index" in st.session_state
        ):
            st.session_state.current_cohort = st.session_state.cohorts[
                st.session_state.current_cohort_index
            ]

        selected_cohort = cols[0].selectbox(
            "Select a cohort",
            st.session_state.cohorts,
            format_func=lambda cohort: cohort["name"],
            key="current_cohort",
        )

        if selected_cohort:
            st.session_state.current_cohort_index = st.session_state.cohorts.index(
                selected_cohort
            )

        cols[1].container(height=10, border=False)
        if cols[1].button("Create Cohort", type="primary"):
            show_create_cohort_dialog()

        if not len(st.session_state.cohorts):
            st.error("No cohorts added yet")
            return

        if not selected_cohort:
            return

        selected_cohort["courses"] = get_courses_for_cohort(selected_cohort["id"])
        show_cohort_overview(selected_cohort)

    with tabs[0]:
        show_cohorts_tab()

    @st.dialog("Create Course")
    def show_create_course_dialog():
        with st.form("create_course_form", border=False):
            course_name = st.text_input("Enter course name", autocomplete="off")

            cohort_selector("create_course")

            if st.form_submit_button(
                "Create",
                type="primary",
                use_container_width=True,
            ):
                if not course_name:
                    st.error("Enter a course name")
                    return

                new_course_id = create_course(course_name, st.session_state.org_id)

                if st.session_state.course_cohorts_create_course:
                    add_course_to_cohorts(
                        new_course_id,
                        [
                            cohort["id"]
                            for cohort in st.session_state.course_cohorts_create_course
                        ],
                    )
                    # invalidate cache
                    clear_course_cache_for_cohorts(
                        st.session_state.course_cohorts_create_course
                    )

                refresh_courses()
                st.session_state.current_course_index = (
                    len(st.session_state.courses) - 1
                )
                set_toast(f"Course `{course_name}` created successfully!")
                st.rerun()

    @st.dialog("Update Course Cohorts")
    def show_update_course_cohorts_dialog(course_id: int, course_cohorts: List[Dict]):
        with st.form("update_course_cohorts_form", border=False):
            selected_cohorts = cohort_selector("update_course", default=course_cohorts)

            st.container(height=10, border=False)

            has_changes = selected_cohorts != course_cohorts

            if st.form_submit_button(
                "Update",
                type="primary",
                use_container_width=True,
            ):
                if not has_changes:
                    st.error("No changes made")
                    return

                cohorts_to_delete_from = [
                    cohort
                    for cohort in course_cohorts
                    if cohort not in selected_cohorts
                ]
                cohorts_to_add_to = [
                    cohort
                    for cohort in selected_cohorts
                    if cohort not in course_cohorts
                ]
                if cohorts_to_add_to:
                    add_course_to_cohorts(
                        course_id, [cohort["id"] for cohort in cohorts_to_add_to]
                    )
                if cohorts_to_delete_from:
                    remove_course_from_cohorts(
                        course_id, [cohort["id"] for cohort in cohorts_to_delete_from]
                    )

                refresh_courses()

                # invalidate cache
                clear_cohort_cache_for_courses([course_id])
                clear_course_cache_for_cohorts(
                    cohorts_to_add_to + cohorts_to_delete_from
                )

                set_toast("Cohorts updated successfully!")
                st.rerun()

    @st.dialog("Delete Course Confirmation")
    def show_delete_course_confirmation_dialog(course):
        st.markdown(f"Are you sure you want to delete the course: `{course['name']}`?")
        (
            confirm_col,
            cancel_col,
        ) = st.columns([1.5, 6])

        if confirm_col.button("Confirm", type="primary"):
            delete_course(course["id"])
            refresh_courses()

            # invalidate cache
            clear_course_cache_for_cohorts(course["cohorts"])

            del st.session_state.current_course_index

            set_toast("Course deleted successfully!")
            st.rerun()

        if cancel_col.button("Cancel"):
            st.rerun()

    def update_task_order(current_order, updated_order, milestone_tasks):
        selected_task = milestone_tasks[current_order]

        # task ordering in milestones are likely to not be in a sequence
        # so, to update the ordering, instead of adding/subtracting 1 from the ordering of all tasks,
        # for each task between the current and updated order, we assign the ordering values
        if current_order < updated_order:
            task_indices_to_update = range(current_order + 1, updated_order + 1)
            update_value = -1
        else:
            task_indices_to_update = range(updated_order, current_order)
            update_value = 1

        task_orders_to_update = [
            (
                milestone_tasks[task_index + update_value]["ordering"],
                milestone_tasks[task_index]["course_task_id"],
            )
            for task_index in task_indices_to_update
        ]
        task_orders_to_update.append(
            (
                milestone_tasks[updated_order]["ordering"],
                selected_task["course_task_id"],
            )
        )
        update_task_orders_in_db(task_orders_to_update)

    @st.dialog("Update Task Order")
    def show_update_task_order_dialog(current_order: int, milestone_tasks: List[Dict]):
        st.write(f"Current Order: `{current_order + 1}`")

        with st.form("update_task_order_form", border=False):
            updated_order = st.selectbox(
                "Enter new order",
                options=list(range(1, len(milestone_tasks) + 1)),
                index=current_order,
            )
            if st.form_submit_button(
                "Update", type="primary", use_container_width=True
            ):
                if updated_order == current_order + 1:
                    st.error("No changes made")
                    return

                update_task_order(current_order, updated_order - 1, milestone_tasks)
                set_toast("Task order updated successfully!")
                st.rerun()

    def update_course_name(course, new_name):
        update_course_name_in_db(course["id"], new_name)
        refresh_courses()

        # invalidate cache
        clear_course_cache_for_cohorts(course["cohorts"])

        set_toast("Course name updated successfully!")
        st.rerun()

    @st.dialog("Edit Course")
    def show_edit_course_form(selected_course):
        with st.form("update_course_name_form", border=False):
            cols = st.columns([1, 0.4])
            updated_course_name = cols[0].text_input(
                "Course Name", value=selected_course["name"], autocomplete="off"
            )
            cols[1].container(height=10, border=False)
            if cols[1].form_submit_button("Update"):
                if not updated_course_name:
                    st.error("Enter a course name")
                    return

                if updated_course_name == selected_course["name"]:
                    st.error("No changes made")
                    return

                update_course_name(selected_course, updated_course_name)

    def show_course_overview(selected_course):
        cols = st.columns([1, 10])

        with cols[0]:
            if st.button("Edit", icon="🖊️", key="edit_course"):
                show_edit_course_form(selected_course)

        with cols[1]:
            if st.button("Delete", icon="🗑️", key="delete_course"):
                show_delete_course_confirmation_dialog(selected_course)

        tab_names = ["Tasks", "Cohorts Assigned to"]

        selected_tab = st.segmented_control(
            "Course Tabs", tab_names, label_visibility="hidden", default=tab_names[0]
        )

        def _show_tasks_tab():
            if not selected_course["tasks"]:
                st.info("This course has no tasks yet")
                return

            task_tab_cols = st.columns([1, 2])
            with task_tab_cols[0]:
                milestone = st.selectbox(
                    "Filter by milestone",
                    set([task["milestone"] for task in selected_course["tasks"]]),
                    key="course_task_milestone_filter",
                )

            filtered_tasks = [
                task
                for task in selected_course["tasks"]
                if task["milestone"] == milestone
            ]

            filtered_df = pd.DataFrame(
                filtered_tasks,
                columns=[
                    "id",
                    # "verified",
                    "name",
                    "type",
                    "input_type",
                    "response_type",
                    "coding_language",
                ],
            )

            action_container = st.container()

            filtered_df["Task Type"] = filtered_df["type"].apply(
                lambda x: task_type_to_label[x]
            )

            column_order = [
                "name",
                "Task Type",
                "input_type",
                "response_type",
                # "coding_language",
            ]

            event = st.dataframe(
                filtered_df,
                on_select="rerun",
                selection_mode="single-row",
                hide_index=True,
                use_container_width=True,
                column_config={
                    "id": None,
                    # "verified": st.column_config.CheckboxColumn(
                    #     default=False,
                    #     width="small",
                    # ),
                    "name": st.column_config.TextColumn(width="large"),
                    "response_type": st.column_config.TextColumn(
                        label="AI response type"
                    ),
                    "input_type": st.column_config.TextColumn(label="User input type"),
                },
                column_order=column_order,
            )

            if len(event.selection["rows"]):
                index = event.selection["rows"][0]
                action_container.button(
                    "Update order",
                    on_click=show_update_task_order_dialog,
                    args=(index, filtered_tasks),
                )

        def _show_assigned_cohorts_tab():
            if st.button("Add/Remove Cohorts", key="update_course_cohorts"):
                show_update_course_cohorts_dialog(
                    selected_course["id"], selected_course["cohorts"]
                )

            if not selected_course["cohorts"]:
                st.info("This course has not been added to any cohort yet")
            else:
                st.pills(
                    "Cohorts",
                    selected_course["cohorts"],
                    format_func=lambda x: x["name"],
                    disabled=True,
                    key="course_cohorts",
                    label_visibility="collapsed",
                )

        if selected_tab == tab_names[0]:
            _show_tasks_tab()

        if selected_tab == tab_names[1]:
            _show_assigned_cohorts_tab()

    def show_courses_tab():
        cols = st.columns([1.2, 0.5, 2])

        if (
            "current_course" in st.session_state
            and st.session_state.current_course not in st.session_state.courses
            and "current_course_index" in st.session_state
        ):
            st.session_state.current_course = st.session_state.courses[
                st.session_state.current_course_index
            ]

        selected_course = cols[0].selectbox(
            "Select a course",
            st.session_state.courses,
            format_func=lambda course: course["name"],
            key="current_course",
        )

        if selected_course:
            st.session_state.current_course_index = st.session_state.courses.index(
                selected_course
            )

        cols[1].container(height=10, border=False)
        if cols[1].button("Create Course", type="primary"):
            show_create_course_dialog()

        if not len(st.session_state.courses):
            st.error("No courses added yet")
            return

        if not selected_course:
            return

        selected_course["tasks"] = get_tasks_for_course(selected_course["id"])
        selected_course["cohorts"] = get_cohorts_for_course(selected_course["id"])

        show_course_overview(selected_course)

    with tabs[1]:
        show_courses_tab()

    def add_milestone(new_milestone, milestone_color):
        if not new_milestone:
            st.toast("Enter a milestone name")
            return

        if new_milestone in [
            milestone["name"] for milestone in st.session_state.milestones
        ]:
            st.toast("Milestone already exists")
            return

        insert_milestone_to_db(new_milestone, milestone_color, st.session_state.org_id)
        st.toast("New milestone added")
        refresh_milestones()
        st.rerun()

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

    def update_milestone(milestone_id, milestone_name, milestone_color):
        update_milestone_in_db(milestone_id, milestone_name, milestone_color)
        st.toast("Milestone updated")
        refresh_milestones()

    @st.dialog("Edit Milestone")
    def show_milestone_edit_form(milestone):
        with st.form("milestone_edit_form", border=False):
            cols = st.columns([6, 1])
            new_milestone_name = cols[0].text_input(
                "Enter new milestone name", value=milestone["name"], autocomplete="off"
            )
            new_milestone_color = cols[1].color_picker(
                "Select",
                value=milestone["color"],
                key="milestone_edit_color_picker",
            )

            if st.form_submit_button(
                "Update", use_container_width=True, type="primary"
            ):
                if not new_milestone_name:
                    st.error("Enter a milestone name")
                    return

                if (
                    new_milestone_color == milestone["color"]
                    and new_milestone_name == milestone["name"]
                ):
                    st.error("No changes made")
                    return

                update_milestone(
                    milestone["id"], new_milestone_name, new_milestone_color
                )
                st.toast("Milestone updated")
                st.rerun()

    def show_milestones_tab():
        with st.form(
            "new_milestone_form",
            border=False,
            clear_on_submit=True,
        ):
            cols = st.columns([1, 0.15, 1, 1])
            new_milestone = cols[0].text_input(
                "Enter milestone",
                key="new_milestone",
                autocomplete="off",
            )

            if (
                "new_milestone_init_color" not in st.session_state
                or st.session_state["new_milestone_init_color"] == "#000000"
            ):
                st.session_state.new_milestone_init_color = generate_random_color()

            cols[1].container(height=10, border=False)

            milestone_color = cols[1].color_picker(
                "Pick A Color",
                key="new_milestone_color",
                label_visibility="collapsed",
                value=st.session_state.new_milestone_init_color,
            )

            cols[2].container(height=10, border=False)
            if cols[2].form_submit_button("Add Milestone"):
                del st.session_state.new_milestone_init_color
                add_milestone(new_milestone, milestone_color)

        if not st.session_state.milestones:
            st.info("No milestones added yet")
            return

        num_layout_cols = 3
        layout_cols = st.columns(num_layout_cols)

        css = ""
        for i, milestone in enumerate(st.session_state.milestones):
            css += f"""
            div[data-testid="stExpander"]:has(.st-key-edit_milestone_{i}) {{
                background-color: {milestone['color']}; 
                border: 1px solid {milestone['color']};
                border-radius: 4px;
                padding: 10px;
                color: black
            }}

            div[data-testid="stExpander"]:has(.st-key-edit_milestone_{i}) > [class^="st-emotion-cache-"] {{
                border-color: {milestone['color']} !important;
            }}

            div[data-testid="stExpander"]:has(.st-key-edit_milestone_{i}) [data-testid="stBaseButton-secondary"] {{
                background-color: white !important;
            }}
            """

        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

        for i, milestone in enumerate(st.session_state.milestones):
            with layout_cols[i % num_layout_cols].container(
                border=False,
            ):
                with st.expander(milestone["name"]):
                    st.button(
                        "Edit",
                        on_click=show_milestone_edit_form,
                        args=(milestone,),
                        key=f"edit_milestone_{i}",
                        use_container_width=True,
                    )

                    st.button(
                        "Delete",
                        on_click=show_milestone_delete_confirmation_dialog,
                        args=(milestone,),
                        key=f"delete_milestone_{i}",
                        use_container_width=True,
                        type="primary",
                    )

    with tabs[3]:
        show_milestones_tab()

    def add_tag(new_tag):
        if not new_tag:
            st.toast("Enter a tag name")
            return

        if new_tag in [tag["name"] for tag in st.session_state.tags]:
            st.toast("Tag already exists")
            return

        # since we show the tags in reverse order, we need to save them in reverse order
        create_tag_in_db(new_tag, st.session_state.org_id)
        st.toast("New tag added")
        refresh_tags()
        st.rerun()

    def delete_tag(tag):
        delete_tag_from_db(tag["id"])
        set_toast("Tag deleted")
        refresh_tags()

    @st.dialog("Delete Tag")
    def show_tag_delete_confirmation_dialog(tag):
        st.markdown(f"Are you sure you want to delete `{tag['name']}`?")
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
        with st.form("new_tag_form", clear_on_submit=True, border=False):
            cols = st.columns(4)
            new_tag = cols[0].text_input("Enter Tag", key="new_tag", autocomplete="off")

            cols[1].container(height=10, border=False)
            if cols[1].form_submit_button("Add"):
                add_tag(new_tag)

        if not st.session_state.tags:
            st.info("No tags added yet")
            return

        num_layout_cols = 3
        layout_cols = st.columns(num_layout_cols)

        for i, tag in enumerate(st.session_state.tags[::-1]):
            with layout_cols[i % num_layout_cols].container(
                border=False,
            ):
                with st.expander(tag["name"]):
                    st.button(
                        "Delete",
                        on_click=show_tag_delete_confirmation_dialog,
                        args=(tag,),
                        key=f"delete_tag_{i}",
                        use_container_width=True,
                    )

    with tabs[4]:
        show_tags_tab()


elif st.session_state.selected_section_index == 1:
    is_hva_org = get_hva_org_id() == st.session_state.org_id

    with layout_cols[-1]:
        tab_names = ["Metrics"]

        if is_hva_org:
            tab_names.append("CV review")

        tabs = st.tabs(tab_names)

    @st.dialog("Select task")
    def show_task_picker_dialog_for_task_history_inspection(
        user_id: int, task_list: List[Dict], cohort_id: int, course_id: int
    ):
        selected_task = st.selectbox(
            "Select the task you want to inspect the history for",
            task_list,
            format_func=lambda val: val["name"],
        )

        task_review_url = f"/task?id={selected_task['id']}&course={course_id}&cohort={cohort_id}&learner={user_id}&mode=review"

        st.link_button(
            "Open", task_review_url, type="primary", use_container_width=True
        )

    def show_metrics_tab():
        if not st.session_state.cohorts:
            st.info(
                "No cohorts found. Create a cohort and add members to it. You will see their usage metrics here!"
            )
            return

        cols = st.columns(3)

        selected_cohort = cols[0].selectbox(
            "Select a cohort",
            st.session_state.cohorts,
            format_func=lambda cohort: cohort["name"],
            key="selected_cohort",
        )

        cohort_courses = get_courses_for_cohort(selected_cohort["id"])

        if not cohort_courses:
            st.error(
                "No courses found for this. Add courses to this cohort to see the usage metrics here!"
            )
            return

        selected_course = cols[1].selectbox(
            "Select a course",
            st.session_state.courses,
            format_func=lambda course: course["name"],
            key="selected_course",
        )

        course_tasks = get_tasks_for_course(selected_course["id"])

        if not course_tasks:
            st.error(
                "No tasks found. The course must have at least one task added to it!"
            )
            return

        milestone = cols[2].selectbox(
            "Filter by milestone",
            set([task["milestone"] for task in course_tasks]),
            key="metrics_course_task_milestone_filter",
        )

        filtered_tasks = [
            task for task in course_tasks if task["milestone"] == milestone
        ]

        metrics = get_cohort_metrics_for_milestone(
            [task["id"] for task in filtered_tasks], selected_cohort["id"]
        )

        if not metrics:
            st.error("No usage data yet!")
            return

        column_order = ["email", "num_completed"]

        column_config = {
            "email": st.column_config.TextColumn("Email", width="medium"),
            "num_completed": st.column_config.NumberColumn(
                "Tasks Completed", width="small"
            ),
        }

        metrics = pd.DataFrame(metrics)

        for task in filtered_tasks:
            column_order.append(f'task_{task["id"]}')
            column_config[f'task_{task["id"]}'] = st.column_config.TextColumn(
                task["name"],
                width="small",
            )
            metrics[f'task_{task["id"]}'] = metrics[f'task_{task["id"]}'].apply(
                lambda val: "✅" if val else "❌"
            )

        action_container = st.container()

        event = st.dataframe(
            metrics,
            column_order=column_order,
            column_config=column_config,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )
        if len(event.selection["rows"]):
            user_id = metrics.iloc[event.selection["rows"]]["user_id"].tolist()[0]
            if action_container.button("Inspect task history"):
                show_task_picker_dialog_for_task_history_inspection(
                    user_id,
                    filtered_tasks,
                    selected_cohort["id"],
                    selected_course["id"],
                )

    with tabs[0]:
        show_metrics_tab()

    def show_cv_review_usage():
        all_cv_review_usage = get_all_cv_review_usage()
        df = pd.DataFrame(all_cv_review_usage)

        if not len(df):
            st.info("No usage data yet!")
            return

        # Get unique emails for filtering
        unique_emails = df["user_email"].unique().tolist()
        selected_email = st.selectbox("Select specific user", unique_emails, index=None)

        # Filter usage counts for selected email if one is chosen
        if selected_email:
            user_entries = df[df["user_email"] == selected_email].reset_index(drop=True)

            st.markdown("#### Submissions")
            # Convert ai_review string to dict and extract timestamp
            user_entries = user_entries.sort_values("created_at", ascending=False)

            for index, entry in user_entries.iterrows():
                with st.expander(
                    f"#{index + 1} - {entry['role']} ({datetime.fromisoformat(entry['created_at']).strftime('%B %d, %Y - %I:%M %p')})"
                ):
                    df = pd.DataFrame(
                        json.loads(entry["ai_review"]), columns=["Category", "Feedback"]
                    )
                    st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.markdown("#### Overview")
            # Group by user email and get counts
            # Get submission counts
            usage_counts = (
                df.groupby("user_email")
                .size()
                .reset_index(name="number of submissions")
            )

            # Get unique roles per user
            roles_by_user = (
                df.groupby("user_email")["role"]
                .agg(lambda x: ", ".join(sorted(set(x))))
                .reset_index(name="rolesr")
            )

            # Merge the two dataframes
            usage_stats = usage_counts.merge(roles_by_user, on="user_email")
            st.dataframe(usage_stats, use_container_width=True, hide_index=True)

    if is_hva_org:
        with tabs[-1]:
            show_cv_review_usage()
else:
    with layout_cols[-1]:
        tabs = st.tabs(["Account", "Members"])

    def show_account_tab():
        with st.form("edit_org_details_form", border=False):
            cols = st.columns([4, 1])
            new_org_name = cols[0].text_input(
                "Organization Name",
                value=st.session_state.org["name"],
                autocomplete="off",
            )

            cols[1].container(height=10, border=False)
            if cols[1].form_submit_button(
                "Update",
                disabled=new_org_name == st.session_state.org["name"],
            ):
                if not new_org_name:
                    st.error("Empty name not allowed")
                    return

                if new_org_name == st.session_state.org["name"]:
                    st.error("No changes made")
                else:
                    update_org(st.session_state.org_id, new_org_name)
                    set_toast("Organization name updated")
                    st.rerun()

        with st.form("edit_org_openai_api_key_form", border=False):
            st.markdown("#### Link your OpenAI account")
            st.write(
                """We use AI models from [OpenAI](https://platform.openai.com/) which costs money for each use. To make sure that you are charged proportional to your usage of SensAI, we need to connect with your OpenAI account and all your usage will be billed to your OpenAI account. You can find your OpenAI API key on the [API key page](https://platform.openai.com/api-keys). Create a new API key from the same page if you don't have one."""
            )

            cols = st.columns([4, 1])
            if not is_empty_openai_api_key():
                api_key_to_display = decrypt_openai_api_key(
                    st.session_state.org["openai_api_key"]
                )
            else:
                api_key_to_display = ""

            new_openai_api_key = cols[0].text_input(
                "OpenAI API Key",
                value=api_key_to_display,
                type="password",
                autocomplete="off",
            )

            cols[1].container(height=10, border=False)

            if cols[1].form_submit_button(
                "Update",
            ):
                if not new_openai_api_key:
                    st.error("API key cannot be empty")
                    return

                if api_key_to_display and new_openai_api_key == api_key_to_display:
                    st.error("No changes made")
                    return

                if not validate_openai_api_key(new_openai_api_key):
                    st.error("Invalid key")
                    return

                update_org_openai_api_key(st.session_state.org_id, new_openai_api_key)
                set_toast("OpenAI API key updated")
                st.rerun()

    with tabs[0]:
        show_account_tab()

    @st.dialog("Add Member")
    def show_add_member_dialog(org_users):
        with st.form("add_member_form", border=False):
            member_email = st.text_input("Enter email", autocomplete="off")
            role = st.selectbox("Select role", ["admin"], disabled=True)

            submit_button = st.form_submit_button(
                "Add Member",
                use_container_width=True,
                type="primary",
            )
            if submit_button:
                try:
                    # Check that the email address is valid
                    member_email = validate_email(member_email)
                    if member_email.normalized in [user["email"] for user in org_users]:
                        st.error("Member already exists")
                        return

                    add_user_to_org_by_email(
                        member_email.normalized, st.session_state.org_id, role
                    )
                    set_toast("Member added successfully")
                    st.rerun()
                except EmailNotValidError as e:
                    # The exception message is human-readable explanation of why it's
                    # not a valid (or deliverable) email address.
                    st.error("Invalid email")

    @st.dialog("Remove members")
    def show_remove_members_confirmation_dialog(
        user_ids,
    ):
        st.write("Are you sure you want to remove the selected members?")

        confirm_col, cancel_col, _, _ = st.columns([1, 1, 2, 2])
        if confirm_col.button("Yes", use_container_width=True):
            remove_members_from_org(
                st.session_state.org_id,
                user_ids,
            )
            st.rerun()

        if cancel_col.button("No", use_container_width=True, type="primary"):
            st.rerun()

    def show_members_tab():
        org_users = get_org_users(st.session_state.org_id)

        df = pd.DataFrame(org_users)

        action_container = st.container()
        add_member_col, remove_members_col = action_container.columns([1, 7])

        add_member_col.button(
            "Add Member", on_click=show_add_member_dialog, args=(org_users,)
        )

        error_container = st.container()

        event = st.dataframe(
            df,
            on_select="rerun",
            selection_mode="multi-row",
            use_container_width=True,
            hide_index=True,
            column_order=["email", "role"],
        )

        if len(event.selection["rows"]):
            user_ids = df.iloc[event.selection["rows"]]["id"].tolist()
            user_roles = set(df.iloc[event.selection["rows"]]["role"].tolist())

            if remove_members_col.button("Remove members", icon="🗑️"):
                if "owner" in user_roles:
                    error_container.error("Cannot remove the owner")
                    return

                # import ipdb; ipdb.set_trace()
                show_remove_members_confirmation_dialog(
                    user_ids,
                )

    with tabs[1]:
        show_members_tab()


# with tabs[-1]:
#     show_settings_tab()
