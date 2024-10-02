from typing import List
from typing_extensions import TypedDict, Annotated
import os
import time
import json
from functools import partial
import asyncio
from pydantic import BaseModel, Field
from openai import OpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from langchain_core.output_parsers import JsonOutputParser

# from langchain_core.chat_history import (
#     InMemoryChatMessageHistory,
# )
from langchain.globals import set_verbose, set_debug
from langchain_core.messages import HumanMessage, AIMessage

# from langchain_core.runnables.history import RunnableWithMessageHistory

import streamlit as st

st.set_page_config(layout="wide")

from streamlit_ace import st_ace, THEMES

# from lib.llm  import get_llm_input_messages,call_llm_and_parse_output
from components.sticky_container import sticky_container
from lib.db import (
    get_task_by_id,
    store_message as store_message_to_db,
    get_task_chat_history_for_user,
    delete_message as delete_message_from_db,
)
from lib.init import init_env_vars, init_db
from lib.chat import MessageHistory
from components.code_execution import execute_code

init_env_vars()
init_db()

# set_verbose(True)
# set_debug(True)

st.markdown(
    """
<style>
        .block-container {
            padding-top: 3rem;
            padding-bottom: 2rem;
            padding-left: 5rem;
            padding-right: 5rem;
        }
</style>
""",
    unsafe_allow_html=True,
)


if "email" not in st.query_params:
    st.error("Not authorized. Redirecting to home page...")
    time.sleep(2)
    st.switch_page("./home.py")

st.session_state.email = st.query_params["email"]

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

task_id = st.query_params.get("id")

if not task_id:
    st.error("No task id provided")
    st.stop()

try:
    task_index = int(task_id)
except ValueError:
    st.error("Task index must be an integer")
    st.stop()

task = get_task_by_id(task_id)

if not task:
    st.error("No task found")
    st.stop()

if not task["verified"]:
    st.error(
        "Task not verified. Please ask your mentor/teacher to verify the task so that you can solve it."
    )
    st.stop()


if "chat_history" not in st.session_state:
    st.session_state.chat_history = get_task_chat_history_for_user(
        task_id, st.session_state.email
    )

if "is_solved" not in st.session_state:
    st.session_state.is_solved = (
        len(st.session_state.chat_history)
        and st.session_state.chat_history[-2]["is_solved"]
    )

task_name_container_background_color = None
task_name_container_text_color = None
if st.session_state.is_solved:
    task_name_container_background_color = "#62B670"
    task_name_container_text_color = "white"

with sticky_container(
    mode="top",
    border=True,
    background_color=task_name_container_background_color,
    text_color=task_name_container_text_color,
):
    # st.link_button('Open task list', '/task_list')

    heading = f"**{task['name']}**"
    if st.session_state.is_solved:
        heading += " ✅"
    st.write(heading)

    with st.expander("Task description", expanded=False):
        st.text(task["description"].replace("\n", "\n\n"))

# st.session_state
# st.session_state['code']

if task["type"] == "coding":
    chat_column, code_column = st.columns([5, 5])
    chat_container = chat_column.container(height=450)
    chat_input_container = chat_column.container(height=100, border=False)
else:
    # chat_column = st.columns(1)[0]
    chat_container = st.container()
    chat_input_container = None


def transform_user_message_for_ai_history(message: dict):
    # return {"role": message['role'], "content": f'''Student's response: ```\n{message['content']}\n```'''}
    return f"""Student's response: ```\n{message['content']}\n```"""


def transform_assistant_message_for_ai_history(message: dict):
    # return {"role": message['role'], "content": message['content']}
    return message["content"]


if "ai_chat_history" not in st.session_state:
    st.session_state.ai_chat_history = MessageHistory()
    st.session_state.ai_chat_history.add_user_message(
        f"""Task:\n```\n{task['description']}\n```\n\nSolution:\n```\n{task['answer']}\n```"""
    )

    # st.session_state.ai_chat_history = [{"role": "user", "content": f"""Task:\n```\n{task['description']}\n```\n\nSolution:\n```\n{task['answer']}\n```"""}]
    for message in st.session_state.chat_history:
        # import ipdb; ipdb.set_trace()
        if message["role"] == "user":
            # import ipdb; ipdb.set_trace()
            st.session_state.ai_chat_history.add_user_message(
                transform_user_message_for_ai_history(message)
            )
        else:
            st.session_state.ai_chat_history.add_ai_message(
                transform_assistant_message_for_ai_history(message)
            )

# st.session_state.ai_chat_history
# st.session_state.chat_history

# st.stop()


def delete_user_chat_message(index_to_delete: int):
    # delete both the user message and the AI assistant's response to it
    updated_chat_history = st.session_state.chat_history[:index_to_delete]
    current_ai_chat_history = st.session_state.ai_chat_history.messages
    # import ipdb; ipdb.set_trace()
    ai_chat_index_to_delete = (
        index_to_delete + 1
    )  # since we have an extra message in ai_chat_history at the start
    updated_ai_chat_history = current_ai_chat_history[:ai_chat_index_to_delete]

    delete_message_from_db(
        st.session_state.chat_history[index_to_delete]["id"]
    )  # delete user message
    delete_message_from_db(
        st.session_state.chat_history[index_to_delete + 1]["id"]
    )  # delete ai message

    if index_to_delete + 2 < len(st.session_state.chat_history):
        updated_chat_history += st.session_state.chat_history[index_to_delete + 2 :]
        updated_ai_chat_history += current_ai_chat_history[
            ai_chat_index_to_delete + 2 :
        ]

    st.session_state.chat_history = updated_chat_history
    st.session_state.ai_chat_history.clear()
    st.session_state.ai_chat_history.add_messages(updated_ai_chat_history)


def display_user_message(user_response: str, message_index: int):
    delete_button_key = f"message_{message_index}"
    # if delete_button_key in st.session_state:
    #     return

    with chat_container.chat_message("user"):
        user_answer_cols = st.columns([5, 1])
        user_answer_cols[0].markdown(user_response, unsafe_allow_html=True)
        user_answer_cols[1].button(
            "Delete",
            on_click=partial(delete_user_chat_message, index_to_delete=message_index),
            key=delete_button_key,
        )


# st.session_state.chat_history
# st.session_state.ai_chat_history

# Display chat messages from history on app rerun
for index, message in enumerate(st.session_state.chat_history):
    if message["role"] == "user":
        # import ipdb; ipdb.set_trace()
        display_user_message(message["content"], message_index=index)
    else:
        with chat_container.chat_message(message["role"]):
            st.markdown(message["content"], unsafe_allow_html=True)


def get_session_history():
    return st.session_state.ai_chat_history


async def _extract_feedback(input_stream):
    """A function that operates on input streams."""
    # feedback = ""
    async for input in input_stream:
        if not isinstance(input, dict):
            continue

        if "feedback" not in input:
            continue

        if "is_solved" in input:
            if not isinstance(input["is_solved"], bool):
                continue

            yield json.dumps({"is_solved": input["is_solved"]})

        feedback = input["feedback"]

        if not isinstance(feedback, str):
            continue

        # print(feedback)

        yield feedback


def get_ai_response(user_message: str):
    import instructor
    import openai

    client = instructor.from_openai(openai.OpenAI())

    # class Output(TypedDict):
    #     response: Annotated[str, "Your response to the student's message"]
    #     is_solved: Annotated[bool, "Whether the student's response correctly solves the task"]

    class Output(BaseModel):
        feedback: List[str] = Field(
            description="Feedback on the student's response; return each word as a separate element in the list; add newline characters to the feedback to make it more readable"
        )
        is_correct: bool = Field(
            description="Whether the student's response correctly solves the task given to the student"
        )

    parser = PydanticOutputParser(pydantic_object=Output)
    format_instructions = parser.get_format_instructions()

    system_prompt = f"""You are a Socratic tutor.\n\nYou will be given a task description, its solution and the conversation history between you and the student.\n\nUse the following principles for responding to the student:\n- Ask thought-provoking, open-ended questions that challenges the student's preconceptions and encourage them to engage in deeper reflection and critical thinking.\n- Facilitate open and respectful dialogue with the student, creating an environment where diverse viewpoints are valued and the student feels comfortable sharing their ideas.\n- Actively listen to the student's responses, paying careful attention to their underlying thought process and making a genuine effort to understand their perspective.\n- Guide the student in their exploration of topics by encouraging them to discover answers independently, rather than providing direct answers, to enhance their reasoning and analytical skills\n- Promote critical thinking by encouraging the student to question assumptions, evaluate evidence, and consider alternative viewpoints in order to arrive at well-reasoned conclusions\n- Demonstrate humility by acknowledging your own limitations and uncertainties, modeling a growth mindset and exemplifying the value of lifelong learning.\n- Avoid giving feedback using the same words in subsequent messages because that makes the feedback monotonic. Maintain diversity in your feedback and always keep the tone welcoming.\n- If the student's response is not relevant to the task, remain curious and empathetic while playfully nudging them back to the task in your feedback.\n- Include an emoji in every few feedback messages [refer to the history provided to decide if an emoji should be added].\n- If the task resolves around code, use backticks ("`", "```") to format sections of code or variable/function names in your feedback.\n- No matter how frustrated the student gets or how many times they ask you for the answer, you must never give away the entire answer in one go. Always provide them hints to let them discover the answer step by step on their own.\n\nImportant Instructions:\n- The student does not have access to the solution. The solution has only been given to you for evaluating the student's response. Keep this in mind while responding to the student.\n\n{format_instructions}"""

    model = "gpt-4o-2024-08-06"

    st.session_state.ai_chat_history.add_user_message(
        transform_user_message_for_ai_history(user_message)
    )

    messages = [
        {"role": "system", "content": system_prompt}
    ] + st.session_state.ai_chat_history.messages

    # import ipdb; ipdb.set_trace()

    return client.chat.completions.create_partial(
        model=model,
        messages=messages,
        response_model=Output,
        temperature=0,
        top_p=1,
        stream=True,
        frequency_penalty=0,
        presence_penalty=0,
    )


def display_waiting_indicator():
    st.markdown(
        """
        <style>
        .typing-indicator {
            display: flex;
            align-items: center;
            height: 20px;
        }
        .typing-indicator span {
            display: inline-block;
            width: 5px;
            height: 5px;
            margin: 0 2px;
            background: #999;
            border-radius: 50%;
            animation: bounce 1s infinite alternate;
        }
        .typing-indicator span:nth-child(2) {
            animation-delay: 0.2s;
        }
        .typing-indicator span:nth-child(3) {
            animation-delay: 0.4s;
        }
        @keyframes bounce {
            from { transform: translateY(0); }
            to { transform: translateY(-15px); }
        }
        </style>
        <div class="typing-indicator">
            <span></span><span></span><span></span>
        </div>
    """,
        unsafe_allow_html=True,
    )


def get_ai_feedback(user_response: str):
    # import ipdb; ipdb.set_trace()
    display_user_message(user_response, len(st.session_state.chat_history))

    user_message = {"role": "user", "content": user_response}
    st.session_state.chat_history.append(user_message)
    # st.session_state.ai_chat_history.add_user_message(transform_user_message_for_ai_history(user_message))

    # ipdb.set_trace()

    # Display assistant response in chat message container
    with chat_container.chat_message("assistant"):
        ai_response_container = st.empty()

        with ai_response_container:
            display_waiting_indicator()

        for extraction in get_ai_response(user_message):
            if json_dump := extraction.model_dump():
                # print(json_dump)
                ai_response_list = json_dump["feedback"]
                if ai_response_list:
                    ai_response = " ".join(ai_response_list)
                    ai_response = ai_response.replace("\n", "\n\n")
                    ai_response_container.markdown(ai_response, unsafe_allow_html=True)

                is_solved = (
                    json_dump["is_correct"]
                    if json_dump["is_correct"] is not None
                    else False
                )

                if not st.session_state.is_solved and is_solved:
                    st.balloons()
                    st.session_state.is_solved = True
                    time.sleep(2)

        # st.write(ai_response)

    st.session_state.ai_chat_history.add_ai_message(ai_response)

    # st.session_state.chat_history.append(ai_response)
    # Add user message to chat history [store to db only if ai response has been completely fetched]
    new_user_message = store_message_to_db(
        st.session_state.email,
        task_id,
        "user",
        user_response,
        st.session_state.is_solved,
    )
    st.session_state.chat_history[-1] = new_user_message

    # Add assistant response to chat history
    new_ai_message = store_message_to_db(
        st.session_state.email, task_id, "assistant", ai_response
    )
    st.session_state.chat_history.append(new_ai_message)

    # retain_code()

    st.rerun()


# st.session_state.ai_chat_history
# st.session_state.is_solved

supported_language_keys = [
    "html_code",
    "css_code",
    "js_code",
    "nodejs_code",
    "python_code",
]


def retain_code():
    for key in supported_language_keys:
        if key in st.session_state and st.session_state[key]:
            st.session_state[key] = st.session_state[key]


def is_any_code_present():
    return bool(
        st.session_state.get("html_code", "")
        or st.session_state.get("css_code", "")
        or st.session_state.get("js_code", "")
        or st.session_state.get("nodejs_code", "")
        or st.session_state.get("python_code", "")
    )


def get_preview_code():
    if not is_any_code_present():
        return ""

    combined_code = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            {css_code}  <!-- Insert the CSS code here -->
        </style>
    </head>
    <body>
        {html_code}  <!-- Insert the HTML code here -->
        <script>
            {js_code}  <!-- Insert the JavaScript code here -->
        </script>
    </body>
    </html>
    """

    return combined_code.format(
        html_code=st.session_state.html_code,
        css_code=st.session_state.css_code,
        js_code=st.session_state.js_code,
    )


def clean_code(code: str):
    return code.strip()


def get_code_for_ai_feedback():
    combined_code = []

    if st.session_state.get("html_code"):
        combined_code.append(f"```html\n{clean_code(st.session_state.html_code)}\n```")

    if st.session_state.get("css_code"):
        combined_code.append(f"```css\n{clean_code(st.session_state.css_code)}\n```")

    if st.session_state.get("js_code"):
        combined_code.append(f"```js\n{clean_code(st.session_state.js_code)}\n```")

    if st.session_state.nodejs_code:
        combined_code.append(f"```js\n{clean_code(st.session_state.nodejs_code)}\n```")

    if st.session_state.python_code:
        combined_code.append(
            f"```python\n{clean_code(st.session_state.python_code)}\n```"
        )

    # st.session_state.js_code

    # combined_code = combined_code.replace('`', '\`').replace('{', '\{').replace('}', '\}').replace('$', '\$')
    # combined_code = f'`{combined_code}`'
    return "\n\n".join(combined_code)


def get_ai_feedback_on_code():
    toggle_show_code_output()
    get_ai_feedback(get_code_for_ai_feedback())


if "show_code_output" not in st.session_state:
    st.session_state.show_code_output = False


def toggle_show_code_output():
    # submit_button_col.write(is_any_code_present())
    if not is_any_code_present():
        return

    st.session_state.show_code_output = not st.session_state.show_code_output
    retain_code()


if task["type"] == "coding":
    with code_column:
        for lang in supported_language_keys:
            if lang not in st.session_state:
                st.session_state[lang] = ""

        close_preview_button_col, _, _, submit_button_col = st.columns([2, 1, 1, 1])

        # st.session_state.show_code_output

        if not st.session_state.show_code_output:
            lang_name_to_tab_name = {
                "HTML": "HTML",
                "CSS": "CSS",
                "Javascript": "JS",
                "NodeJS": "NodeJS",
                "Python": "Python",
            }
            tab_name_to_language = {
                "HTML": "html",
                "CSS": "css",
                "JS": "javascript",
                "NodeJS": "javascript",
                "Python": "python",
            }
            tab_names = []
            for lang in task["coding_language"]:
                tab_names.append(lang_name_to_tab_name[lang])

            with st.form("Code"):
                st.form_submit_button("Run Code", on_click=toggle_show_code_output)

                tabs = st.tabs(tab_names)
                for index, tab in enumerate(tabs):
                    with tab:
                        tab_name = tab_names[index].lower()
                        language = tab_name_to_language[tab_names[index]]
                        st_ace(
                            min_lines=15,
                            theme="monokai",
                            language=language,
                            tab_size=2,
                            key=f"{tab_name}_code",
                            auto_update=True,
                            value=st.session_state[f"{tab_name}_code"],
                            placeholder=f"Write your {language} code here...",
                        )

        else:
            import streamlit.components.v1 as components

            if any(
                lang in task["coding_language"]
                for lang in ["HTML", "CSS", "Javascript"]
            ):
                with st.expander("Configuration"):
                    dim_cols = st.columns(2)
                    height = dim_cols[0].slider(
                        "Preview Height",
                        min_value=100,
                        max_value=1000,
                        value=300,
                        on_change=retain_code,
                    )
                    width = dim_cols[1].slider(
                        "Preview Width",
                        min_value=100,
                        max_value=600,
                        value=600,
                        on_change=retain_code,
                    )

            try:
                with st.container(border=True):
                    if "HTML" in task["coding_language"]:
                        components.html(
                            get_preview_code(),
                            width=width,
                            height=height,
                            scrolling=True,
                        )
                    elif "Javascript" in task["coding_language"]:
                        execute_code(st.session_state.js_code, "Javascript")
                    elif "NodeJS" in task["coding_language"]:
                        execute_code(st.session_state.nodejs_code, "NodeJS")
                    elif "Python" in task["coding_language"]:
                        execute_code(st.session_state.python_code, "Python")
                    else:
                        st.write("**No output to show**")
                    # TODO: support for only JS
                    # TODO: support for other languages
            except Exception as e:
                st.error(f"Error: {e}")

            close_preview_button_col.button(
                "Back to Editor", on_click=toggle_show_code_output
            )

            if submit_button_col.button("Submit Code", type="primary"):
                get_ai_feedback_on_code()

user_response_placeholder = "Your response"

if task["type"] == "coding":
    user_response_placeholder = (
        "Use the code editor for submitting code and ask/tell anything else here"
    )
else:
    user_response_placeholder = "Write your response here"

# st.session_state.chat_history
# st.session_state.ai_chat_history.messages


def show_and_handle_chat_input():
    if user_response := st.chat_input(user_response_placeholder):
        get_ai_feedback(user_response)


if chat_input_container:
    with chat_input_container:
        show_and_handle_chat_input()
else:
    show_and_handle_chat_input()
