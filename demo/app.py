import requests
import json
import os
from collections import defaultdict
from functools import partial
from dotenv import load_dotenv
import streamlit as st

from models import Node

load_dotenv()

if os.path.exists("/demo"):
    # instance
    BASE_API_URL = "http://app:8001"
else:
    BASE_API_URL = "http://127.0.0.1:8001"


topic_col, sub_topic_col, concept_col = st.columns(3)

if "is_training_started" not in st.session_state:
    st.session_state.is_training_started = False


# @st.cache_resource()
def fetch_topic_list():
    fetch_topics_response = requests.get(
        f"{os.environ['BACKEND_URL']}/api/roadmaps/list",
    )
    if fetch_topics_response.status_code != 200:
        st.error("Something went wrong. Please reload the page")
        st.stop()

    topics = fetch_topics_response.json()["topics"]

    return topics


# @st.cache_data
def fetch_topic_tree(topic: Node):
    fetch_topic_tree_response = requests.get(
        f"{os.environ['BACKEND_URL']}/api/roadmaps/load",
        params={"parentId": topic["id"]},
    )
    if fetch_topic_tree_response.status_code != 200:
        st.error("Something went wrong. Please reload the page")
        st.stop()

    return fetch_topic_tree_response.json()


# @st.cache_resource()
def fetch_learning_outcomes(concept: Node):
    import urllib

    fetch_learning_outcome_response = requests.get(
        f"{os.environ['BACKEND_URL']}/api/learning_outcome/lo/",
        params={"nodeId": concept["id"]},
    )
    if fetch_learning_outcome_response.status_code != 200:
        st.error("Something went wrong. Please reload the page")
        st.stop()

    learning_outcomes = fetch_learning_outcome_response.json()
    blooms_level_to_learning_outcomes_map = defaultdict(list)

    valid_blooms_levels = {
        "Remembering",
        "Analyzing",
        "Applying",
        "Creating",
    }

    for learning_outcome in learning_outcomes:
        if learning_outcome["blooms_level"] not in valid_blooms_levels:
            continue

        blooms_level_to_learning_outcomes_map[learning_outcome["blooms_level"]].append(
            learning_outcome["value"]
        )
    return dict(blooms_level_to_learning_outcomes_map)


topics = fetch_topic_list()

selected_topic_index = 0

with topic_col:
    topic = st.selectbox(
        "Choose topic",
        topics,
        key="topic",
        index=selected_topic_index,
        format_func=lambda val: val["name"],
        disabled=st.session_state.is_training_started,
    )

topic_tree = fetch_topic_tree(topic)

with sub_topic_col:
    sub_topic = st.selectbox(
        "Choose Sub-Topic",
        topic_tree.keys(),
        key="sub_topic",
        disabled=st.session_state.is_training_started,
    )

with concept_col:
    concept = st.selectbox(
        "Choose Concept",
        topic_tree[sub_topic],
        key="concept",
        format_func=lambda val: val["name"],
        disabled=st.session_state.is_training_started,
    )

learning_outcomes_dict = fetch_learning_outcomes(concept)

if not learning_outcomes_dict:
    st.warning("No learning outcomes available for this concept")
    st.stop()


blooms_level_col, learning_outcome_col = st.columns(2)

with blooms_level_col:
    blooms_level = st.selectbox(
        "Choose Bloom's Level",
        learning_outcomes_dict.keys(),
        key="blooms_level",
        disabled=st.session_state.is_training_started,
    )

with learning_outcome_col:
    learning_outcome = st.selectbox(
        "Choose Learning Outcome",
        learning_outcomes_dict[blooms_level],
        key="learning_outcome",
        disabled=st.session_state.is_training_started,
    )

# st.stop()

if not learning_outcome:
    st.warning("Please choose a learning outcome")
    st.stop()


def on_start_training_click():
    st.session_state.is_training_started = True


def on_reset_training_click():
    st.session_state.is_training_started = False
    st.session_state.chat_history = []
    st.session_state.ai_chat_history = []


if not st.session_state.is_training_started:
    st.button("Start Training", on_click=on_start_training_click)
else:
    st.button("Reset Training", on_click=on_reset_training_click)

is_training_started = st.session_state.is_training_started

with st.expander("See variables"):
    st.session_state


def delete_user_chat_message(index_to_delete: int):
    # delete both the user message and the AI assistant's response to it
    updated_chat_history = st.session_state.chat_history[:index_to_delete]
    updated_ai_chat_history = st.session_state.ai_chat_history[:index_to_delete]

    if index_to_delete + 2 < len(st.session_state.chat_history):
        updated_chat_history += st.session_state.chat_history[index_to_delete + 2 :]
        updated_ai_chat_history += st.session_state.ai_chat_history[
            index_to_delete + 2 :
        ]

    st.session_state.chat_history = updated_chat_history
    st.session_state.ai_chat_history = updated_ai_chat_history


if is_training_started:
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    if "ai_chat_history" not in st.session_state:
        st.session_state.ai_chat_history = []

    chat_history = st.session_state.chat_history
    ai_chat_history = st.session_state.ai_chat_history

    if not chat_history:
        with st.chat_message("assistant"):
            question_generation_response = requests.post(
                f"{BASE_API_URL}/training/question",
                data=json.dumps(
                    {
                        "topic": topic["name"],
                        "sub_topic": sub_topic,
                        "concept": concept["name"],
                        "blooms_level": blooms_level,
                        "learning_outcome": learning_outcome,
                    }
                ),
                stream=True,
            )

            # refer: https://docs.streamlit.io/knowledge-base/tutorials/build-conversational-apps
            question_placeholder = st.empty()
            generated_question = ""

            question_placeholder.write("▌")
            for line in question_generation_response.iter_content(chunk_size=20):
                generated_question += line.decode()
                question_placeholder.write(generated_question + "▌")

            # with st.chat_message("assistant"):
            #     question_placeholder = st.empty()
            #     generated_question = """Imagine you are designing a webpage and you want to position a specific element, say a navigation bar, at a fixed position on the top of the webpage. How would you apply the CSS positioning properties to achieve this? Please write the CSS code snippet for the same.\n\nRemember, your answer should include the CSS selector for the navigation bar and the appropriate positioning properties."""

            question_placeholder.write(generated_question)

            st.session_state.chat_history.append(
                {"role": "assistant", "content": generated_question}
            )
            st.session_state.ai_chat_history.append(
                {
                    "role": "assistant",
                    "content": f"Topic - {topic['name']}\nSub-Topic - {sub_topic}\nConcept - {concept['name']}\nBlooms level - {blooms_level}\nLearning outcome - {learning_outcome}\nQuestion - {generated_question}",
                    "type": "question",
                }
            )

    else:
        for index, message in enumerate(chat_history):
            with st.chat_message(message["role"]):
                if message["role"] == "assistant":
                    st.write(message["content"])
                else:
                    user_answer_cols = st.columns([7, 1])
                    user_answer_cols[0].write(message["content"])
                    user_answer_cols[1].button(
                        "Delete",
                        on_click=partial(
                            delete_user_chat_message, index_to_delete=index
                        ),
                        key=index,
                    )

    # reset AI response state
    if "ai_response_in_progress" not in st.session_state:
        st.session_state.ai_response_in_progress = False

    def toggle_ai_response_state():
        st.session_state.ai_response_in_progress = (
            not st.session_state.ai_response_in_progress
        )

    # toggle_ai_response_state()

    user_answer = st.chat_input(
        "Your answer",
        on_submit=toggle_ai_response_state,
        disabled=st.session_state.ai_response_in_progress,
    )

    if user_answer:
        with st.chat_message("user"):
            user_answer_cols = st.columns([7, 1])
            user_answer_cols[0].write(user_answer)
            user_answer_cols[1].button(
                "Delete",
                on_click=partial(
                    delete_user_chat_message, index_to_delete=len(chat_history)
                ),
                key=len(chat_history),
            )

        with st.chat_message("assistant"):
            ai_chat_history.append({"role": "user", "content": user_answer})

            with st.spinner("Fetching AI response..."):
                training_chat_response = requests.post(
                    f"{BASE_API_URL}/training/chat",
                    data=json.dumps({"messages": ai_chat_history}),
                    stream=True,
                )

            ai_response_placeholder = st.empty()
            ai_response = ""
            ai_feedback = ""
            user_answer_type = None

            chunk_history = ""
            user_answer_score = None
            user_answer_feedback = None
            special_character_count = defaultdict(int)

            ai_response_placeholder.write("▌")
            for line in training_chat_response.iter_content(chunk_size=20):
                # first chunk is the user answer type
                if user_answer_type is None:
                    user_answer_type = line.decode()
                    print(user_answer_type)
                    continue

                chunk = line.decode()
                chunk_history += chunk

                if user_answer_type in ["clarification", "miscellaneous"]:
                    ai_response += chunk
                    ai_response_placeholder.write(ai_response + "▌")

                elif user_answer_type == "answer":
                    if "```" in chunk and not special_character_count["{"]:
                        continue

                    if "{" in chunk:
                        special_character_count["{"] += 1

                    if "}" in chunk:
                        special_character_count["{"] -= 1
                        if not special_character_count["{"]:
                            continue

                    if "answer_evaluation" not in chunk_history:
                        continue

                    if 'feedback": "' not in chunk_history:
                        if user_answer_score is not None:
                            continue
                        try:
                            user_answer_score = int(chunk)
                            if user_answer_score == 2:
                                result = "Proficient :rocket:"
                            elif user_answer_score == 1:
                                result = "Almost there :runner:"
                            elif user_answer_score == 0:
                                result = "You can do better :hugging_face:"
                            ai_response += f"Result - {result} \nFeedback - "
                            ai_response_placeholder.write(ai_response + "▌")
                        except:
                            continue
                    else:
                        ai_response += chunk
                        ai_feedback += chunk
                        ai_response_placeholder.write(ai_response + "▌")

            toggle_ai_response_state()

            if user_answer_type == "irrelevant":
                ai_response = "Irrelevant response"

            ai_response_placeholder.write(ai_response)

        # save last user message only if there is a assistant response as well
        st.session_state.chat_history += [
            {"role": "user", "content": user_answer},
            {"role": "assistant", "content": ai_response},
        ]

        # update type of user message
        ai_chat_history[-1]["type"] = user_answer_type

        ai_chat_history.append(
            {
                "role": "assistant",
                "content": ai_feedback if user_answer_type == "answer" else ai_response,
                "type": "response",
            },
        )
        st.session_state.ai_chat_history = ai_chat_history
        st.experimental_rerun()
